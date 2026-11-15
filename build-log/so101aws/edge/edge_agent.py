"""エッジエージェント（CLAUDE.md §4.4）。

- 指令（cmd）を §4.4 の処理順で評価し、Runner を動かして結果（result）を返す
- 状態（status）は retain 付きで、変化したときと定期的に送る
- 停止・安全はエッジが持つ。クラウドの max_run_s はエッジの上限を超えられない

段階 1 では MQTT につながず、publish は差し替え可能な関数として受け取る（LocalTransport は画面に出すだけ）。
段階 2 で AWS IoT Device SDK v2 の MQTT5 クライアントをつなぐ。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import sys
import threading
import time
import unicodedata
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

import protocol as P
from runner import FakeRunnerFactory, PolicyRunner, PolicyRunnerFactory, Runner

ROLLOUT_SCRIPT = str(Path(__file__).resolve().parents[1] / "scripts" / "rollout_smolvla.sh")

# エッジ側の実行時間の上限（秒）。クラウドがこれより長い max_run_s を送っても切り詰める（§4.3）
EDGE_MAX_RUN_S = 120.0

Publish = Callable[[str, dict, bool], None]  # (topic, payload, retain)


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Current:
    cmd: P.Command
    runner: Runner
    received_at: datetime
    started_at: datetime
    max_run_s: float
    deadline: float  # time.monotonic() の値
    stop_reason: str | None = None


class EdgeAgent:
    def __init__(
        self,
        thing: str,
        publish: Publish,
        runner_factory: Callable[[], Runner],
        *,
        clock: Callable[[], datetime] = utcnow,
        allowed_tasks: frozenset[str] = P.ALLOWED_TASKS,
        edge_max_run_s: float = EDGE_MAX_RUN_S,
        dedup_size: int = 100,
        poll_s: float = 0.05,
        label_provider: Callable[[P.Command], str] | None = None,
    ):
        self.topics = P.topics(thing)
        self._publish = publish
        self._runner_factory = runner_factory
        self._clock = clock
        self._allowed_tasks = allowed_tasks
        self._edge_max_run_s = edge_max_run_s
        self._dedup_size = dedup_size
        self._poll_s = poll_s
        self._label_provider = label_provider

        self._lock = threading.RLock()
        self.state = P.IDLE
        self._current: _Current | None = None
        # cmd_id -> 送った result（実行中・停止指令は None）。メモリ上だけ。再起動すると忘れる（§4.4 の既知の制限）
        self._seen: OrderedDict[str, dict | None] = OrderedDict()
        self._worker: threading.Thread | None = None
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None

    # ---- 指令の受け付け（§4.4 の処理順。上から評価し、最初に該当したもので終わる） ----

    def handle_payload(self, payload: bytes | str) -> str:
        """cmd を1件処理する。戻り値は何が起きたか（テストとログ用）。"""
        received_at = self._clock()
        with self._lock:
            # 1. スキーマ不正・v 不一致
            try:
                cmd = P.parse_command(payload)
            except P.InvalidCommand as e:
                res = P.make_result(
                    cmd_id=e.cmd_id, state=P.REJECTED, reason=P.R_INVALID,
                    issued_at=e.issued_at_raw, received_at=received_at, finished_at=received_at,
                )
                self._publish(self.topics["result"], res, False)
                return "rejected:invalid"

            # 2. 既知の cmd_id は再実行しない。完了済みなら前回の result を再送、実行中なら何もしない
            if cmd.cmd_id in self._seen:
                prev = self._seen[cmd.cmd_id]
                if prev is not None:
                    self._publish(self.topics["result"], prev, False)
                    return "duplicate:resent"
                return "duplicate:ignored"

            # 3. 停止指令
            if cmd.type == P.CMD_STOP:
                self._remember(cmd.cmd_id, None)
                if self.state == P.RUNNING:
                    self._request_stop_locked(P.R_CLOUD_STOP)
                    return "stop:requested"
                return "stop:ignored"

            # 4. 期限切れ
            if received_at - cmd.issued_at > timedelta(seconds=cmd.ttl_s):
                return self._reject(cmd, P.R_EXPIRED, received_at)

            # 5. 許可リストにないタスク
            if cmd.task not in self._allowed_tasks:
                return self._reject(cmd, P.R_UNKNOWN_TASK, received_at)

            # 6. 実行中・停止中
            if self.state != P.IDLE:
                return self._reject(cmd, P.R_BUSY, received_at)

            # 7. 実行開始
            return self._start(cmd, received_at)

    def _reject(self, cmd: P.Command, reason: str, received_at: datetime) -> str:
        res = P.make_result(
            cmd_id=cmd.cmd_id, state=P.REJECTED, reason=reason,
            issued_at=cmd.issued_at_raw, received_at=received_at, finished_at=received_at,
        )
        self._remember(cmd.cmd_id, res)
        self._publish(self.topics["result"], res, False)
        return f"rejected:{reason}"

    def _remember(self, cmd_id: str, result: dict | None) -> None:
        self._seen[cmd_id] = result
        self._seen.move_to_end(cmd_id)
        while len(self._seen) > self._dedup_size:
            oldest = next(iter(self._seen))
            if self._current is not None and oldest == self._current.cmd.cmd_id:
                self._seen.move_to_end(oldest)  # 実行中の指令は忘れない
                if len(self._seen) <= 1:
                    break
                continue
            self._seen.popitem(last=False)

    # ---- 実行 ----

    def _start(self, cmd: P.Command, received_at: datetime) -> str:
        max_run_s = min(cmd.max_run_s, self._edge_max_run_s)
        runner = self._runner_factory()
        started_at = self._clock()
        self._current = _Current(
            cmd=cmd, runner=runner, received_at=received_at, started_at=started_at,
            max_run_s=max_run_s, deadline=time.monotonic() + max_run_s,
        )
        self._remember(cmd.cmd_id, None)
        self.state = P.RUNNING
        self._publish_status_locked()
        try:
            runner.start(cmd.task)
        except Exception as e:  # noqa: BLE001  どんな失敗でも IDLE に戻し、result で知らせる（止まったまま RUNNING にしない）
            print(f"[edge] runner の起動に失敗: {e!r}", file=sys.stderr)
            self._finish_locked(exit_code=None, error=True)
            return "aborted:runner_error"
        self._worker = threading.Thread(target=self._run_loop, name=f"run-{cmd.cmd_id}", daemon=True)
        self._worker.start()
        return "started"

    def _run_loop(self) -> None:
        cur = self._current
        assert cur is not None
        exit_code: int | None = None
        while True:
            exit_code = cur.runner.wait(self._poll_s)
            with self._lock:
                if cur.stop_reason is None and exit_code is None and time.monotonic() >= cur.deadline:
                    self._request_stop_locked(P.R_TIMEOUT)
                if cur.stop_reason is not None or exit_code is not None:
                    break
        if cur.stop_reason is not None:
            # 停止は数秒かかりうる（PolicyRunner は SIGINT → SIGTERM → SIGKILL）。ロックの外で待つ
            exit_code = cur.runner.stop()
        finished_at = self._clock()  # ラベル入力を待つ前に記録する（入力の時間を含めない）

        label = "none"
        if self._label_provider is not None:
            label = self._label_provider(cur.cmd)  # オペレーターの y/n を待つ。ロックの外で
        with self._lock:
            self._finish_locked(exit_code=exit_code, label=label, finished_at=finished_at)

    def _finish_locked(self, exit_code: int | None, *, error: bool = False, label: str = "none",
                       finished_at: datetime | None = None) -> None:
        cur = self._current
        assert cur is not None
        if cur.stop_reason is not None:
            state, reason = P.ABORTED, cur.stop_reason
        elif error or exit_code != 0:
            state, reason = P.ABORTED, P.R_RUNNER_ERROR
        else:
            state, reason = P.COMPLETED, P.R_OK
        res = P.make_result(
            cmd_id=cur.cmd.cmd_id, state=state, reason=reason, issued_at=cur.cmd.issued_at_raw,
            received_at=cur.received_at, started_at=cur.started_at, finished_at=finished_at or self._clock(),
            operator_label=label,
        )
        self._remember(cur.cmd.cmd_id, res)
        self._publish(self.topics["result"], res, False)
        self._current = None
        self.state = P.IDLE
        self._publish_status_locked()

    # ---- 停止 ----

    def request_stop(self, reason: str) -> bool:
        """ローカル停止キーなどから呼ぶ。RUNNING のときだけ効く。"""
        with self._lock:
            return self._request_stop_locked(reason)

    def _request_stop_locked(self, reason: str) -> bool:
        if self.state != P.RUNNING or self._current is None:
            return False
        self._current.stop_reason = reason
        self.state = P.STOPPING
        self._publish_status_locked()
        return True

    # ---- 状態 ----

    def _publish_status_locked(self) -> None:
        cmd_id = self._current.cmd.cmd_id if self._current else None
        self._publish(self.topics["status"], P.make_status(self.state, cmd_id, self._clock()), True)

    def publish_status(self) -> None:
        with self._lock:
            self._publish_status_locked()

    def start_heartbeat(self, interval_s: float = 10.0) -> None:
        """接続時に1回と、interval_s ごとに status を送る（§4.3）。"""
        def loop() -> None:
            self.publish_status()
            while not self._hb_stop.wait(interval_s):
                self.publish_status()
        self._hb_thread = threading.Thread(target=loop, name="heartbeat", daemon=True)
        self._hb_thread.start()

    def wait_idle(self, timeout: float = 5.0) -> bool:
        w = self._worker
        if w is not None:
            w.join(timeout)
        return self.state == P.IDLE

    def close(self) -> None:
        self._hb_stop.set()
        if self._hb_thread is not None:
            self._hb_thread.join(1.0)


class KeyController:
    """標準入力を1つのスレッドで読む（§4.4）。

    - ふだん：`s` で停止（operator_stop）
    - `--label` の実行が終わったあと：y/n の入力に切り替わる
    """

    def __init__(self, agent: EdgeAgent, out: TextIO = sys.stderr):
        self.agent = agent
        self.out = out
        self._awaiting_label = threading.Event()
        self._labels: queue.Queue[str] = queue.Queue()

    def feed_line(self, line: str) -> None:
        # 日本語入力のまま打った全角（ｓ・ｙ・ｎ）も受け付ける。止めたいときに止まらないのは危ない（Build Log #022 節8-6）
        s = unicodedata.normalize("NFKC", line).strip().lower()
        if self._awaiting_label.is_set():
            self._labels.put(s)
        elif s == "s":
            ok = self.agent.request_stop(P.R_OPERATOR_STOP)
            print("[edge] 停止を要求しました" if ok else "[edge] 実行中ではありません", file=self.out)

    def run(self, stream: TextIO) -> None:
        for line in stream:
            self.feed_line(line)

    def ask_label(self, cmd: P.Command) -> str:
        """実行後にオペレーターが成否を入力する（M1 の実機実行のときだけ使う）。"""
        self._awaiting_label.set()
        try:
            while True:
                print(f"[edge] {cmd.cmd_id} は成功しましたか？ [y/n]", file=self.out, flush=True)
                s = self._labels.get()
                if s in ("y", "yes"):
                    return "success"
                if s in ("n", "no"):
                    return "fail"
        finally:
            self._awaiting_label.clear()


class LocalTransport:
    """段階 1 用：publish を画面に出すだけ。"""

    def __init__(self, out: TextIO = sys.stdout):
        self.out = out
        self._lock = threading.Lock()

    def publish(self, topic: str, payload: dict, retain: bool) -> None:
        with self._lock:
            flag = " (retain)" if retain else ""
            print(f"PUB {topic}{flag} {json.dumps(payload, ensure_ascii=False)}", file=self.out, flush=True)


def make_demo_cmd(task: str = "pick_yellow_block", ttl_s: float = 60, max_run_s: float = 90) -> str:
    return json.dumps({
        "v": P.VERSION, "cmd_id": str(uuid.uuid4()), "type": P.CMD_RUN_TASK, "task": task,
        "issued_at": P.iso(utcnow()), "ttl_s": ttl_s, "max_run_s": max_run_s,
    })


CERT_DIR = str(Path(__file__).resolve().parents[1] / "certs")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SO-101 edge agent")
    ap.add_argument("--transport", choices=["local", "mqtt"], default="local",
                    help="local は画面に出すだけ。mqtt は AWS IoT Core につなぐ（段階 2）")
    ap.add_argument("--endpoint", default=os.environ.get("IOT_ENDPOINT"),
                    help="mqtt：Data-ATS エンドポイント（terraform output -raw iot_endpoint）")
    ap.add_argument("--cert-dir", default=CERT_DIR, help="mqtt：edge.crt / edge.key / AmazonRootCA1.pem の場所")
    ap.add_argument("--runner", choices=["fake", "policy"], default="fake",
                    help="policy は実機（scripts/rollout_smolvla.sh）を動かす")
    ap.add_argument("--run-s", type=float, default=20.0, help="policy：lerobot-rollout --duration に渡す秒数")
    ap.add_argument("--grace-s", type=float, default=10.0, help="policy：SIGINT のあと SIGTERM まで待つ秒数")
    ap.add_argument("--log-dir", default="/mnt/data/lerobot-outputs/logs")
    ap.add_argument("--thing", default="so101-edge-01")
    ap.add_argument("--fake-duration", type=float, default=10.0, help="FakeRunner が実行中でいる秒数")
    ap.add_argument("--fake-exit-code", type=int, default=0)
    ap.add_argument("--demo-run", action="store_true", help="起動直後に run_task を1件流し込む（動作確認用）")
    ap.add_argument("--max-run-s", type=float, default=None,
                    help="demo の指令の max_run_s。省略時は fake=90、policy=run_s+起動+後始末+10")
    ap.add_argument("--label", action="store_true", help="実行後に y/n で成否を入力する")
    ap.add_argument("--heartbeat-s", type=float, default=10.0)
    ap.add_argument("--no-keys", action="store_true",
                    help="標準入力を読まない（バックグラウンド実行用）。SIGINT / SIGTERM で終了する")
    args = ap.parse_args(argv)
    if args.label and args.no_keys:
        ap.error("--label には標準入力が要る（--no-keys と同時に使えない）")

    holder: dict = {}
    if args.runner == "policy":
        factory = PolicyRunnerFactory([ROLLOUT_SCRIPT], run_s=args.run_s, grace_s=args.grace_s, log_dir=args.log_dir)
        default_max = args.run_s + PolicyRunner.STARTUP_S + PolicyRunner.TEARDOWN_S + 10
    else:
        factory = FakeRunnerFactory(args.fake_duration, args.fake_exit_code)
        default_max = 90.0
    max_run_s = args.max_run_s if args.max_run_s is not None else default_max

    def publish(topic: str, payload: dict, retain: bool) -> None:
        holder["transport"].publish(topic, payload, retain)

    agent = EdgeAgent(
        args.thing, publish, factory,
        label_provider=(lambda c: holder["keys"].ask_label(c)) if args.label else None,
    )
    if args.transport == "mqtt":
        if not args.endpoint:
            ap.error("--endpoint（または環境変数 IOT_ENDPOINT）が要る")
        from mqtt_transport import MqttTransport
        transport = MqttTransport(
            endpoint=args.endpoint,
            cert=f"{args.cert_dir}/edge.crt", key=f"{args.cert_dir}/edge.key", ca=f"{args.cert_dir}/AmazonRootCA1.pem",
            client_id=args.thing, cmd_topic=agent.topics["cmd"], on_cmd=agent.handle_payload,
        )
        holder["transport"] = transport
        transport.connect()
    else:
        transport = LocalTransport()
        holder["transport"] = transport

    keys = KeyController(agent)
    holder["keys"] = keys
    agent.start_heartbeat(args.heartbeat_s)  # 接続できてから送り始める（§4.3：接続時と定期的に）
    print(f"[edge] 起動（transport={args.transport}, runner={args.runner}）。"
          f"{'SIGINT / SIGTERM で終了' if args.no_keys else 's + Enter で停止、Ctrl+C で終了'}", file=sys.stderr, flush=True)
    if args.demo_run:
        print(f"[edge] demo: {agent.handle_payload(make_demo_cmd(max_run_s=max_run_s))}", file=sys.stderr)

    quit_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: quit_event.set())
    try:
        if args.no_keys:
            signal.signal(signal.SIGINT, lambda *_: quit_event.set())
            quit_event.wait()
        else:
            reader = threading.Thread(target=keys.run, args=(sys.stdin,), daemon=True)
            reader.start()
            while reader.is_alive() and not quit_event.wait(0.2):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        print("[edge] 終了します（実行中なら止めてから）", file=sys.stderr, flush=True)
        agent.request_stop(P.R_OPERATOR_STOP)
        # PolicyRunner の停止は最大 SIGINT→grace→SIGTERM→grace→SIGKILL。実測 5.6 秒（節8-5）
        agent.wait_idle(args.grace_s * 2 + 5)
        agent.close()
        time.sleep(0.5)  # 最後の status / result の送信を待つ
        transport_close = getattr(holder.get("transport"), "close", None)
        if transport_close:
            transport_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

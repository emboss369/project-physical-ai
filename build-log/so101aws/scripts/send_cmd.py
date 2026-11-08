"""クラウド側から手で指令を送る（CLAUDE.md §4.9、段階 2）。

  python send_cmd.py status                 # status の retained を読む
  python send_cmd.py send [--task ...]      # run_task を送る（cmd_id を表示）
  python send_cmd.py stop                   # 停止の指令
  python send_cmd.py result CMD_ID [--wait 60]
  python send_cmd.py e1 --n 20              # 実験 E1：配送遅延（received_at - issued_at）
  python send_cmd.py e2 --n 5               # 実験 E2：同じ cmd_id を2回送っても1回しか動かない

エンドポイントとバケットは、環境変数 IOT_ENDPOINT / RESULTS_BUCKET か、infra/ の terraform output から取る。
boto3 の API は botocore のサービス定義で確認した：iot-data publish(topic, qos, retain, payload)、
get_retained_message(topic) → payload / lastModifiedTime。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THING = os.environ.get("THING", "so101-edge-01")
TOPIC = {k: f"so101/{THING}/{k}" for k in ("cmd", "status", "result")}
STATUS_STALE_S = 30  # これより古い status は「不明」扱い（§4.3）


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def make_cmd(*, task: str = "pick_yellow_block", ttl_s: float = 60, max_run_s: float = 90,
             cmd_id: str | None = None, type_: str = "run_task") -> dict:
    d = {"v": 1, "cmd_id": cmd_id or str(uuid.uuid4()), "type": type_, "issued_at": iso_now()}
    if type_ == "run_task":
        d.update(task=task, ttl_s=ttl_s, max_run_s=max_run_s)
    return d


def latency_ms(result: dict) -> float:
    return (parse_iso(result["received_at"]) - parse_iso(result["issued_at"])).total_seconds() * 1000


def summarize(values: list[float]) -> dict:
    v = sorted(values)
    return {
        "n": len(v),
        "min": v[0],
        "median": statistics.median(v),
        "p90": v[min(len(v) - 1, round(0.9 * (len(v) - 1)))],
        "max": v[-1],
        "mean": statistics.fmean(v),
    }


def tf_output(name: str) -> str:
    return subprocess.run(["terraform", "output", "-raw", name], cwd=ROOT / "infra",
                          check=True, capture_output=True, text=True).stdout.strip()


class Cloud:
    def __init__(self):
        import boto3
        endpoint = os.environ.get("IOT_ENDPOINT") or tf_output("iot_endpoint")
        self.bucket = os.environ.get("RESULTS_BUCKET") or tf_output("results_bucket")
        self.iot = boto3.client("iot-data", endpoint_url=f"https://{endpoint}")
        self.s3 = boto3.client("s3")

    def publish_cmd(self, cmd: dict) -> None:
        self.iot.publish(topic=TOPIC["cmd"], qos=1, payload=json.dumps(cmd).encode())

    def status(self) -> dict | None:
        try:
            r = self.iot.get_retained_message(topic=TOPIC["status"])
        except self.iot.exceptions.ResourceNotFoundException:
            return None
        st = json.loads(r["payload"])
        age = (datetime.now(UTC) - parse_iso(st["ts"])).total_seconds()
        st["_age_s"] = round(age, 1)
        st["_stale"] = age > STATUS_STALE_S
        return st

    def result(self, cmd_id: str) -> tuple[dict, dict] | None:
        key = f"results/{THING}/{cmd_id}.json"
        try:
            o = self.s3.get_object(Bucket=self.bucket, Key=key)
        except self.s3.exceptions.NoSuchKey:
            return None
        return json.loads(o["Body"].read()), {"etag": o["ETag"], "last_modified": o["LastModified"]}

    def wait_result(self, cmd_id: str, timeout: float = 60, after=None) -> tuple[dict, dict]:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            r = self.result(cmd_id)
            if r is not None and (after is None or r[1]["last_modified"] > after):
                return r
            time.sleep(0.5)
        raise TimeoutError(f"{timeout} 秒以内に result が来なかった: {cmd_id}")

    def wait_idle(self, timeout: float = 60) -> dict:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            st = self.status()
            if st and st["state"] == "IDLE" and not st["_stale"]:
                return st
            time.sleep(0.5)
        raise TimeoutError("エッジが IDLE にならない（または status が古い）")


def append_numbers(title: str, lines: list[str]) -> Path:
    p = ROOT / "docs" / "lt-numbers.md"
    p.parent.mkdir(exist_ok=True)
    if not p.exists():
        p.write_text("# LT の数字（実験の記録）\n\nCLAUDE.md §6 の実験の結果。新しいものを下に足す。\n")
    with p.open("a") as f:
        f.write(f"\n## {title}\n\n" + "\n".join(lines) + "\n")
    return p


def cmd_e1(c: Cloud, n: int, interval: float, note: str) -> int:
    lat = []
    print(f"E1: {n} 回。エッジは FakeRunner で起動しておくこと（--fake-duration 1 くらい）")
    for i in range(n):
        c.wait_idle()
        cmd = make_cmd(max_run_s=30)
        c.publish_cmd(cmd)
        res, _ = c.wait_result(cmd["cmd_id"])
        ms = latency_ms(res)
        lat.append(ms)
        print(f"  {i + 1:2d}/{n} {res['state']}/{res['reason']} {ms:7.1f} ms")
        if res["state"] != "completed":
            print("  ※ completed ではない", file=sys.stderr)
        time.sleep(interval)
    s = summarize(lat)
    print("E1:", {k: round(v, 1) if isinstance(v, float) else v for k, v in s.items()})
    p = append_numbers(f"E1 配送遅延（{datetime.now().strftime('%Y-%m-%d %H:%M')} JST）", [
        f"- 条件: {note}",
        ("- 測ったもの: `received_at - issued_at`。issued_at は send_cmd.py（boto3 iot-data publish の直前）、"
        "received_at はエッジの受信時。**送信側とエッジが同じ PC** なので、時計のずれは入らない。"
        "経路は PC → IoT Core（東京）→ PC で、一方向ではない"),
        "",
        "| n | 最小 | 中央値 | p90 | 最大 | 平均 |",
        "|---|---|---|---|---|---|",
        f"| {s['n']} | {s['min']:.1f} ms | {s['median']:.1f} ms | {s['p90']:.1f} ms | {s['max']:.1f} ms | {s['mean']:.1f} ms |",
        "",
        "生データ（ms）: " + ", ".join(f"{x:.1f}" for x in lat),
    ])
    print(f"記録した: {p}")
    return 0


def cmd_e2(c: Cloud, n: int, run_s_hint: float) -> int:
    """同じ cmd_id を「実行中」と「完了後」に送り直す。

    「実行中に送れたか」は、重複を送った時刻が 1 回目の result の started_at〜finished_at に入っているかで判定する。
    最初は retained の status で判定していたが、送ってから 0.8 秒後でも IDLE が返ることがあった（節9-4）。
    """
    ok = 0
    rows = []
    print("E2: 同じ cmd_id を「実行中」と「完了後」に送り直す。エッジは FakeRunner（--fake-duration 3 くらい）で")
    for i in range(n):
        c.wait_idle()
        cmd = make_cmd(max_run_s=30)
        c.publish_cmd(cmd)
        time.sleep(0.8)
        dup_at = parse_iso(iso_now())
        c.publish_cmd(cmd)  # 1. 実行中の重複 → 無視されるはず
        first, meta1 = c.wait_result(cmd["cmd_id"], timeout=run_s_hint + 30)
        time.sleep(1.0)
        c.publish_cmd(cmd)  # 2. 完了後の重複 → 前回の result を再送するはず
        second, _meta2 = c.wait_result(cmd["cmd_id"], timeout=30, after=meta1["last_modified"])
        during_run = parse_iso(first["started_at"]) < dup_at < parse_iso(first["finished_at"])
        same = first == second
        ran_once = first["state"] == "completed" and first["reason"] == "ok"  # busy で拒否されていない＝1回だけ動いた
        passed = during_run and same and ran_once
        ok += passed
        rows.append(f"| {i + 1} | {'はい' if during_run else 'いいえ'} | {first['state']}/{first['reason']} | "
                    f"{'同じ' if same else '違う'} | {'OK' if passed else 'NG'} |")
        print(f"  {i + 1}/{n} 実行中に重複を送れた={during_run} 1回目={first['reason']} 再送が同一={same} "
              f"→ {'OK' if passed else 'NG'}")
    p = append_numbers(f"E2 重複指令（{datetime.now().strftime('%Y-%m-%d %H:%M')} JST）", [
        "- 手順: run_task を送る → 0.8 秒後（実行中）に同じ cmd_id を送る → 完了後にもう一度同じ cmd_id を送る",
        "- 「実行中に送れたか」は、重複を送った時刻が 1 回目の result の started_at〜finished_at に入っているかで判定",
        ("- 合格: 実行中の重複は無視され（result は reason=ok の1件。busy にならない）、完了後の重複には"
         "前回とまったく同じ result が再送される（S3 のオブジェクトの LastModified だけが新しくなる）"),
        "",
        "| # | 実行中に重複を送れたか | 1回目の result | 再送された result | 判定 |",
        "|---|---|---|---|---|",
        *rows,
        "",
        f"**{ok}/{n} 合格**",
    ])
    print(f"E2: {ok}/{n} 合格。記録した: {p}")
    return 0 if ok == n else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("send")
    s.add_argument("--task", default="pick_yellow_block")
    s.add_argument("--ttl", type=float, default=60)
    s.add_argument("--max-run", type=float, default=90)
    s.add_argument("--wait", action="store_true", help="result が S3 に来るまで待つ")
    sub.add_parser("stop")
    r = sub.add_parser("result")
    r.add_argument("cmd_id")
    r.add_argument("--wait", type=float, default=0)
    e1 = sub.add_parser("e1")
    e1.add_argument("--n", type=int, default=20)
    e1.add_argument("--interval", type=float, default=1.0)
    e1.add_argument("--note", default="エッジ: Ubuntu PC（愛媛）、Wi-Fi 2.4GHz・IPv6 無効、FakeRunner")
    e2 = sub.add_parser("e2")
    e2.add_argument("--n", type=int, default=5)
    e2.add_argument("--run-s", type=float, default=3)
    a = ap.parse_args(argv)

    c = Cloud()
    if a.cmd == "status":
        print(json.dumps(c.status(), ensure_ascii=False, indent=2))
    elif a.cmd == "send":
        st = c.status()
        if not st or st["_stale"] or st["state"] != "IDLE":
            print(f"エッジが IDLE ではない（または status が古い）: {st}", file=sys.stderr)
            return 1
        cmd = make_cmd(task=a.task, ttl_s=a.ttl, max_run_s=a.max_run)
        c.publish_cmd(cmd)
        print(cmd["cmd_id"])
        if a.wait:
            res, _ = c.wait_result(cmd["cmd_id"], timeout=a.max_run + 30)
            print(json.dumps(res, ensure_ascii=False, indent=2))
    elif a.cmd == "stop":
        c.publish_cmd(make_cmd(type_="stop"))
        print("stop を送った")
    elif a.cmd == "result":
        r = c.wait_result(a.cmd_id, timeout=a.wait) if a.wait else c.result(a.cmd_id)
        print(json.dumps(r[0] if r else None, ensure_ascii=False, indent=2))
    elif a.cmd == "e1":
        return cmd_e1(c, a.n, a.interval, a.note)
    elif a.cmd == "e2":
        return cmd_e2(c, a.n, a.run_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

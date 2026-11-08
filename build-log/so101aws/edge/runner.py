"""Runner：ポリシーを実際に動かす部分（CLAUDE.md §4.4）。

edge_agent からは次の 3 つだけを使う。
- start(task)        ：実行を始める（すぐ戻る）
- wait(timeout)      ：最大 timeout 秒待つ。終わっていれば終了コード、まだなら None
- stop()             ：止めて、止まるまで待ち、終了コードを返す

段階 1 は FakeRunner だけ。PolicyRunner（lerobot-rollout をサブプロセスで動かす）は、
実機の立ち会いで終了のしかたと停止時の挙動を確かめてから作る。
"""

from __future__ import annotations

import threading
import time
from typing import Protocol


class Runner(Protocol):
    def start(self, task: str) -> None: ...
    def wait(self, timeout: float) -> int | None: ...
    def stop(self) -> int: ...


class FakeRunner:
    """指定秒だけ「実行中」のふりをして、exit_code で終わる。実機なしの開発・テスト用。"""

    STOPPED_EXIT_CODE = 130  # SIGINT で止めたときの慣習的な値

    def __init__(self, duration_s: float = 3.0, exit_code: int = 0):
        self.duration_s = duration_s
        self.exit_code = exit_code
        self._stop = threading.Event()
        self._t0: float | None = None
        self.started_tasks: list[str] = []
        self.stop_calls = 0

    def start(self, task: str) -> None:
        if self._t0 is not None:
            raise RuntimeError("FakeRunner is single-use")
        self.started_tasks.append(task)
        self._t0 = time.monotonic()

    def _remaining(self) -> float:
        assert self._t0 is not None
        return self.duration_s - (time.monotonic() - self._t0)

    def wait(self, timeout: float) -> int | None:
        if self._stop.is_set():
            return self.STOPPED_EXIT_CODE
        rem = self._remaining()
        if rem <= 0:
            return self.exit_code
        if self._stop.wait(min(timeout, rem)):
            return self.STOPPED_EXIT_CODE
        return self.exit_code if self._remaining() <= 0 else None

    def stop(self) -> int:
        self.stop_calls += 1
        self._stop.set()
        return self.STOPPED_EXIT_CODE


class PolicyRunner:
    """ポリシーの実行（scripts/rollout_smolvla.sh → lerobot-rollout）をサブプロセスで動かす。

    実測（Build Log #022 節8-5）：
    - 起動から制御ループ開始まで 約 15 秒
    - --duration で時間になる / SIGINT を受けると、開始時の姿勢に 3 秒で戻り、切断して脱力する。終了コード 0
    - SIGINT から終了まで 5.6 秒

    停止：SIGINT → grace_s 待つ → SIGTERM → grace_s 待つ → SIGKILL。
    SIGINT/SIGTERM は lerobot-rollout 本体（スクリプトが exec するので proc.pid）にだけ送る。
    グループ全体に送ると、ログを書いている tee まで止まりうるため。SIGKILL だけはグループ全体に送る。
    """

    STARTUP_S = 15.0   # 実測。max_run_s を決めるときに足す
    TEARDOWN_S = 6.0   # 実測 5.6 秒

    def __init__(self, cmd: list[str], *, run_s: float, grace_s: float = 10.0, env: dict | None = None,
                 log_dir: str | None = None):
        self.cmd = cmd
        self.run_s = run_s
        self.grace_s = grace_s
        self.env = env
        self.log_dir = log_dir
        self.proc = None
        self.signals_sent: list[str] = []

    def start(self, task: str) -> None:
        import os
        import subprocess
        if self.proc is not None:
            raise RuntimeError("PolicyRunner is single-use")
        env = dict(os.environ if self.env is None else self.env)
        env["DURATION"] = str(self.run_s)
        if self.log_dir:
            env["LOG"] = f"{self.log_dir}/rollout_{task}_{time.strftime('%Y%m%d_%H%M%S')}.log"
        # 新しいプロセスグループ（セッション）で起動する。edge_agent への Ctrl+C が直接届かないように
        self.proc = subprocess.Popen(self.cmd, env=env, start_new_session=True)

    def wait(self, timeout: float) -> int | None:
        import subprocess
        assert self.proc is not None
        try:
            return self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def stop(self) -> int:
        import os
        import signal
        import subprocess
        assert self.proc is not None
        if self.proc.poll() is not None:
            return self.proc.returncode
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.signals_sent.append(sig.name)
            try:
                os.kill(self.proc.pid, sig)
            except ProcessLookupError:
                pass
            try:
                return self.proc.wait(self.grace_s)
            except subprocess.TimeoutExpired:
                continue
        self.signals_sent.append("SIGKILL")
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return self.proc.wait()


class PolicyRunnerFactory:
    def __init__(self, cmd: list[str], *, run_s: float, grace_s: float = 10.0, log_dir: str | None = None):
        self.cmd = cmd
        self.run_s = run_s
        self.grace_s = grace_s
        self.log_dir = log_dir
        self.created: list[PolicyRunner] = []

    def __call__(self) -> PolicyRunner:
        r = PolicyRunner(self.cmd, run_s=self.run_s, grace_s=self.grace_s, log_dir=self.log_dir)
        self.created.append(r)
        return r


class FakeRunnerFactory:
    """1 回の実行ごとに新しい FakeRunner を作る。テストで作られた Runner を後から調べられる。"""

    def __init__(self, duration_s: float = 3.0, exit_code: int = 0):
        self.duration_s = duration_s
        self.exit_code = exit_code
        self.created: list[FakeRunner] = []

    def __call__(self) -> FakeRunner:
        r = FakeRunner(self.duration_s, self.exit_code)
        self.created.append(r)
        return r

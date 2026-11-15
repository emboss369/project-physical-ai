"""PolicyRunner のテスト。実機の代わりに tests/fake_rollout.py を動かす。"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protocol as P
from edge_agent import EdgeAgent
from runner import PolicyRunner, PolicyRunnerFactory

FAKE = [sys.executable, str(Path(__file__).with_name("fake_rollout.py"))]


def runner(mode="graceful", run_s=5.0, grace_s=0.5, teardown=0.2):
    r = PolicyRunner(FAKE, run_s=run_s, grace_s=grace_s,
                     env={**os.environ, "FAKE_MODE": mode, "FAKE_TEARDOWN": str(teardown)})
    return r


def test_natural_end_exit_0():
    r = runner(run_s=0.3)
    r.start("pick_yellow_block")
    code = None
    t0 = time.monotonic()
    while code is None and time.monotonic() - t0 < 5:
        code = r.wait(0.1)
    assert code == 0
    assert r.signals_sent == []


def test_wait_returns_none_while_running():
    r = runner(run_s=5)
    r.start("pick_yellow_block")
    assert r.wait(0.1) is None
    r.stop()


def test_sigint_is_enough_for_graceful_process():
    r = runner(mode="graceful", run_s=30)
    r.start("pick_yellow_block")
    time.sleep(0.3)  # シグナルハンドラが入るのを待つ
    assert r.stop() == 0
    assert r.signals_sent == ["SIGINT"]


def test_escalates_to_sigterm():
    r = runner(mode="ignore_int", run_s=30, grace_s=0.3)
    r.start("pick_yellow_block")
    time.sleep(0.3)
    assert r.stop() == 0
    assert r.signals_sent == ["SIGINT", "SIGTERM"]


def test_escalates_to_sigkill():
    r = runner(mode="ignore_all", run_s=30, grace_s=0.3)
    r.start("pick_yellow_block")
    time.sleep(0.3)
    code = r.stop()
    assert code == -9
    assert r.signals_sent == ["SIGINT", "SIGTERM", "SIGKILL"]


def test_new_process_group():
    r = runner(run_s=5)
    r.start("pick_yellow_block")
    try:
        assert os.getpgid(r.proc.pid) == r.proc.pid != os.getpgid(0)
    finally:
        r.stop()


def test_duration_is_passed_via_env(tmp_path):
    r = PolicyRunner([sys.executable, "-c", "import os,sys; print(os.environ['DURATION'], os.environ.get('LOG',''))"],
                     run_s=12.5, log_dir=str(tmp_path))
    r.start("pick_yellow_block")
    assert r.wait(5) == 0


def test_agent_with_policy_runner_timeout():
    # max_run_s を超えたら、エッジが SIGINT で止めて aborted/timeout
    msgs = []
    fac = PolicyRunnerFactory(FAKE, run_s=30, grace_s=0.5)
    agent = EdgeAgent("t", lambda t, p, r: msgs.append((t, p)), fac, poll_s=0.02)
    c = json.dumps({"v": 1, "cmd_id": str(uuid.uuid4()), "type": "run_task", "task": "pick_yellow_block",
                    "issued_at": P.iso(datetime.now(UTC)), "ttl_s": 60, "max_run_s": 0.5})
    assert agent.handle_payload(c) == "started"
    assert agent.wait_idle(5)
    res = next(p for t, p in msgs if t.endswith("/result"))
    assert res["state"] == "aborted" and res["reason"] == "timeout"
    assert fac.created[0].signals_sent == ["SIGINT"]

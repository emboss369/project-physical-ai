"""段階 1 の受け入れテスト（CLAUDE.md §7）。

§4.4 の処理順・状態遷移の全パターン、重複排除、ローカル停止キーを確かめる。実機・AWS は使わない。
"""

from __future__ import annotations

import io
import json
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protocol as P
from edge_agent import EdgeAgent, KeyController
from runner import FakeRunnerFactory

THING = "so101-edge-01"
T = P.topics(THING)


class Recorder:
    def __init__(self):
        self.msgs: list[tuple[str, dict, bool]] = []
        self._lock = threading.Lock()

    def __call__(self, topic: str, payload: dict, retain: bool) -> None:
        with self._lock:
            self.msgs.append((topic, json.loads(json.dumps(payload)), retain))

    def results(self) -> list[dict]:
        with self._lock:
            return [p for t, p, _ in self.msgs if t == T["result"]]

    def statuses(self) -> list[dict]:
        with self._lock:
            return [p for t, p, _ in self.msgs if t == T["status"]]

    def status_states(self) -> list[str]:
        return [s["state"] for s in self.statuses()]


def now() -> datetime:
    return datetime.now(UTC)


def cmd(**over) -> str:
    d = {
        "v": 1, "cmd_id": str(uuid.uuid4()), "type": "run_task", "task": "pick_yellow_block",
        "issued_at": P.iso(now()), "ttl_s": 60, "max_run_s": 90,
    }
    d.update(over)
    return json.dumps({k: v for k, v in d.items() if v is not ...})


def stop_cmd(**over) -> str:
    d = {"v": 1, "cmd_id": str(uuid.uuid4()), "type": "stop", "issued_at": P.iso(now())}
    d.update(over)
    return json.dumps(d)


def make_agent(duration_s=0.3, exit_code=0, **kw):
    rec = Recorder()
    fac = FakeRunnerFactory(duration_s, exit_code)
    agent = EdgeAgent(THING, rec, fac, poll_s=0.01, **kw)
    return agent, rec, fac


def wait_until(pred, timeout=2.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.005)
    return False


# ---------------------------------------------------------------------------
# 7. 正常系：IDLE → RUNNING → IDLE、completed/ok
# ---------------------------------------------------------------------------

def test_run_completes_ok():
    agent, rec, fac = make_agent(duration_s=0.1)
    c = cmd()
    assert agent.handle_payload(c) == "started"
    assert agent.state == P.RUNNING
    assert agent.wait_idle()
    (res,) = rec.results()
    assert res["state"] == "completed" and res["reason"] == "ok"
    assert res["cmd_id"] == json.loads(c)["cmd_id"]
    assert res["issued_at"] == json.loads(c)["issued_at"]
    for k in ("received_at", "started_at", "finished_at"):
        assert res[k] and res[k].endswith("Z")
    assert res["operator_label"] == "none"
    assert rec.status_states() == ["RUNNING", "IDLE"]
    assert all(r for _, _, r in rec.msgs if _ == T["status"])  # status は retain
    assert [r for t, _, r in rec.msgs if t == T["result"]] == [False]  # result は retain なし
    assert fac.created[0].started_tasks == ["pick_yellow_block"]


def test_status_carries_cmd_id_while_running():
    agent, rec, _ = make_agent(duration_s=0.1)
    c = cmd()
    agent.handle_payload(c)
    agent.wait_idle()
    running, idle = rec.statuses()
    assert running["cmd_id"] == json.loads(c)["cmd_id"]
    assert idle["cmd_id"] is None


# ---------------------------------------------------------------------------
# 1. スキーマ不正・v 不一致 → rejected/invalid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload, has_cmd_id", [
    (b"not json", False),
    ("[1,2,3]", False),
    (cmd(v=2), True),
    (cmd(cmd_id=...), False),
    (cmd(cmd_id=""), False),
    (cmd(issued_at=...), True),
    (cmd(issued_at="yesterday"), True),
    (cmd(issued_at="2026-11-08T07:30:00"), True),  # タイムゾーンなし
    (cmd(type="dance"), True),
    (cmd(task=...), True),
    (cmd(ttl_s=0), True),
    (cmd(ttl_s="60"), True),
    (cmd(max_run_s=-1), True),
    (cmd(max_run_s=True), True),
])
def test_invalid_is_rejected(payload, has_cmd_id):
    agent, rec, fac = make_agent()
    assert agent.handle_payload(payload) == "rejected:invalid"
    (res,) = rec.results()
    assert res["state"] == "rejected" and res["reason"] == "invalid"
    assert (res["cmd_id"] is not None) == has_cmd_id
    assert fac.created == []
    assert agent.state == P.IDLE


# ---------------------------------------------------------------------------
# 2. 重複排除
# ---------------------------------------------------------------------------

def test_duplicate_after_completion_resends_previous_result():
    agent, rec, fac = make_agent(duration_s=0.05)
    c = cmd()
    agent.handle_payload(c)
    agent.wait_idle()
    assert agent.handle_payload(c) == "duplicate:resent"
    r1, r2 = rec.results()
    assert r1 == r2
    assert len(fac.created) == 1  # 2回目は動かない


def test_duplicate_while_running_is_ignored():
    agent, rec, fac = make_agent(duration_s=0.3)
    c = cmd()
    agent.handle_payload(c)
    assert agent.handle_payload(c) == "duplicate:ignored"
    assert rec.results() == []
    agent.wait_idle()
    assert len(fac.created) == 1
    assert len(rec.results()) == 1


def test_duplicate_of_rejected_resends_rejection():
    agent, rec, fac = make_agent()
    c = cmd(task="make_coffee")
    agent.handle_payload(c)
    assert agent.handle_payload(c) == "duplicate:resent"
    r1, r2 = rec.results()
    assert r1 == r2 and r1["reason"] == "unknown_task"
    assert fac.created == []


def test_duplicate_wins_over_expiry():
    # 処理順：2（既知）は 4（期限切れ）より先。完了済みの指令が遅れて再送されても、前回の結果を返す
    t = [now()]
    agent, rec, _ = make_agent(duration_s=0.05, clock=lambda: t[0])
    c = cmd(issued_at=P.iso(t[0]), ttl_s=1)
    agent.handle_payload(c)
    agent.wait_idle()
    t[0] = t[0] + timedelta(seconds=3600)
    assert agent.handle_payload(c) == "duplicate:resent"
    assert rec.results()[1]["reason"] == "ok"


def test_dedup_forgets_oldest_beyond_capacity():
    agent, _rec, _fac = make_agent(dedup_size=3)
    cs = [cmd(task="nope") for _ in range(4)]
    for c in cs:
        agent.handle_payload(c)
    # 最も古い1件は忘れているので、もう一度評価される（同じ理由で拒否されるが、再送ではない）
    assert agent.handle_payload(cs[0]) == "rejected:unknown_task"
    assert agent.handle_payload(cs[3]) == "duplicate:resent"


# ---------------------------------------------------------------------------
# 3. 停止指令
# ---------------------------------------------------------------------------

def test_cloud_stop_while_running():
    agent, rec, fac = make_agent(duration_s=5.0)
    c = cmd()
    agent.handle_payload(c)
    assert agent.handle_payload(stop_cmd()) == "stop:requested"
    assert agent.state in (P.STOPPING, P.IDLE)
    assert agent.wait_idle()
    (res,) = rec.results()
    assert res["cmd_id"] == json.loads(c)["cmd_id"]
    assert res["state"] == "aborted" and res["reason"] == "cloud_stop"
    assert rec.status_states() == ["RUNNING", "STOPPING", "IDLE"]
    assert fac.created[0].stop_calls == 1


def test_stop_while_idle_is_ignored():
    agent, rec, _ = make_agent()
    assert agent.handle_payload(stop_cmd()) == "stop:ignored"
    assert rec.msgs == []


def test_stop_is_not_subject_to_ttl():
    # 処理順：3（停止）は 4（期限切れ）より先。古い停止指令でも止める（安全側）
    agent, rec, _ = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    old = P.iso(now() - timedelta(hours=1))
    assert agent.handle_payload(stop_cmd(issued_at=old)) == "stop:requested"
    agent.wait_idle()
    assert rec.results()[0]["reason"] == "cloud_stop"


def test_duplicate_stop_is_ignored():
    agent, _rec, _ = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    s = stop_cmd()
    agent.handle_payload(s)
    assert agent.handle_payload(s) == "duplicate:ignored"
    agent.wait_idle()


def test_stop_while_stopping_does_nothing_more():
    agent, rec, _fac = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    agent.request_stop(P.R_OPERATOR_STOP)
    agent.handle_payload(stop_cmd())
    agent.wait_idle()
    (res,) = rec.results()
    assert res["reason"] == "operator_stop"  # 最初の停止理由が残る


# ---------------------------------------------------------------------------
# 4. 期限切れ
# ---------------------------------------------------------------------------

def test_expired_is_rejected():
    agent, rec, fac = make_agent()
    c = cmd(issued_at=P.iso(now() - timedelta(seconds=61)), ttl_s=60)
    assert agent.handle_payload(c) == "rejected:expired"
    assert rec.results()[0]["reason"] == "expired"
    assert fac.created == []


def test_within_ttl_runs():
    agent, _rec, _ = make_agent(duration_s=0.05)
    c = cmd(issued_at=P.iso(now() - timedelta(seconds=59)), ttl_s=60)
    assert agent.handle_payload(c) == "started"
    agent.wait_idle()


def test_expired_wins_over_unknown_task_and_busy():
    agent, _rec, _ = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    c = cmd(task="nope", issued_at=P.iso(now() - timedelta(seconds=120)), ttl_s=60)
    assert agent.handle_payload(c) == "rejected:expired"
    agent.request_stop(P.R_OPERATOR_STOP)
    agent.wait_idle()


# ---------------------------------------------------------------------------
# 5. 許可リスト
# ---------------------------------------------------------------------------

def test_unknown_task_is_rejected():
    agent, _rec, fac = make_agent()
    assert agent.handle_payload(cmd(task="rotate_joint_30deg")) == "rejected:unknown_task"
    assert fac.created == []


def test_unknown_task_wins_over_busy():
    agent, _rec, _ = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    assert agent.handle_payload(cmd(task="nope")) == "rejected:unknown_task"
    agent.request_stop(P.R_OPERATOR_STOP)
    agent.wait_idle()


# ---------------------------------------------------------------------------
# 6. busy
# ---------------------------------------------------------------------------

def test_busy_while_running():
    agent, _rec, fac = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    assert agent.handle_payload(cmd()) == "rejected:busy"
    assert len(fac.created) == 1
    agent.request_stop(P.R_OPERATOR_STOP)
    agent.wait_idle()


def test_busy_while_stopping():
    agent, _rec, _fac = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    with agent._lock:  # STOPPING の状態で止めておくため、ワーカーより先にロックを取る
        agent._request_stop_locked(P.R_OPERATOR_STOP)
        assert agent.state == P.STOPPING
        assert agent.handle_payload(cmd()) == "rejected:busy"
    agent.wait_idle()


def test_can_run_again_after_finish():
    agent, rec, _fac = make_agent(duration_s=0.05)
    agent.handle_payload(cmd())
    agent.wait_idle()
    assert agent.handle_payload(cmd()) == "started"
    agent.wait_idle()
    assert [r["reason"] for r in rec.results()] == ["ok", "ok"]


# ---------------------------------------------------------------------------
# 状態遷移：時間切れ・上限・Runner の異常終了
# ---------------------------------------------------------------------------

def test_timeout_aborts():
    agent, rec, fac = make_agent(duration_s=5.0)
    agent.handle_payload(cmd(max_run_s=0.1))
    assert agent.wait_idle()
    (res,) = rec.results()
    assert res["state"] == "aborted" and res["reason"] == "timeout"
    assert rec.status_states() == ["RUNNING", "STOPPING", "IDLE"]
    assert fac.created[0].stop_calls == 1


def test_max_run_s_is_capped_by_edge_limit():
    agent, rec, _ = make_agent(duration_s=5.0, edge_max_run_s=0.1)
    agent.handle_payload(cmd(max_run_s=3600))  # クラウドが長く頼んでも
    assert agent.wait_idle(2.0)
    assert rec.results()[0]["reason"] == "timeout"  # エッジの上限で止まる


def test_runner_nonzero_exit_is_runner_error():
    agent, rec, _ = make_agent(duration_s=0.05, exit_code=1)
    agent.handle_payload(cmd())
    agent.wait_idle()
    (res,) = rec.results()
    assert res["state"] == "aborted" and res["reason"] == "runner_error"


def test_runner_start_failure_returns_to_idle():
    class Boom:
        def start(self, task): raise RuntimeError("serial port busy")
        def wait(self, timeout): return None
        def stop(self): return 1
    rec = Recorder()
    agent = EdgeAgent(THING, rec, lambda: Boom(), poll_s=0.01)
    assert agent.handle_payload(cmd()) == "aborted:runner_error"
    assert agent.state == P.IDLE
    assert rec.results()[0]["reason"] == "runner_error"


# ---------------------------------------------------------------------------
# ローカル停止キー・ラベル
# ---------------------------------------------------------------------------

def test_local_stop_key():
    agent, rec, _fac = make_agent(duration_s=5.0)
    keys = KeyController(agent, out=io.StringIO())
    agent.handle_payload(cmd())
    keys.run(io.StringIO("hello\ns\n"))  # s 以外は無視
    assert agent.wait_idle()
    (res,) = rec.results()
    assert res["state"] == "aborted" and res["reason"] == "operator_stop"


def test_local_stop_key_when_idle_does_nothing():
    agent, rec, _ = make_agent()
    out = io.StringIO()
    KeyController(agent, out=out).run(io.StringIO("s\n"))
    assert rec.msgs == []
    assert "実行中ではありません" in out.getvalue()


def test_label_switches_stdin_to_yes_no():
    holder = {}
    agent, rec, _ = make_agent(duration_s=0.05, label_provider=lambda c: holder["k"].ask_label(c))
    keys = KeyController(agent, out=io.StringIO())
    holder["k"] = keys
    agent.handle_payload(cmd())
    assert wait_until(lambda: keys._awaiting_label.is_set())
    keys.feed_line("s")      # ラベル待ちの間は、s は停止ではなく回答として扱う（y/n ではないので聞き直し）
    keys.feed_line("y")
    assert agent.wait_idle()
    (res,) = rec.results()
    assert res["reason"] == "ok" and res["operator_label"] == "success"
    assert rec.status_states() == ["RUNNING", "IDLE"]


def test_label_fail():
    holder = {}
    agent, rec, _ = make_agent(duration_s=0.05, label_provider=lambda c: holder["k"].ask_label(c))
    holder["k"] = keys = KeyController(agent, out=io.StringIO())
    agent.handle_payload(cmd())
    assert wait_until(lambda: keys._awaiting_label.is_set())
    keys.feed_line("n")
    agent.wait_idle()
    assert rec.results()[0]["operator_label"] == "fail"


# ---------------------------------------------------------------------------
# 定期的な status
# ---------------------------------------------------------------------------

def test_heartbeat_publishes_status_periodically():
    agent, rec, _ = make_agent()
    agent.start_heartbeat(0.02)
    assert wait_until(lambda: len(rec.statuses()) >= 3)
    agent.close()
    s = rec.statuses()[0]
    assert s["state"] == "IDLE" and s["cmd_id"] is None and s["ts"].endswith("Z")
    assert all(r for t, _, r in rec.msgs if t == T["status"])


# ---------------------------------------------------------------------------
# protocol
# ---------------------------------------------------------------------------

def test_iso_has_millis_and_z():
    s = P.iso(datetime(2026, 11, 8, 7, 30, 0, 123456, tzinfo=UTC))
    assert s == "2026-11-08T07:30:00.123Z"
    assert P.parse_iso(s) == datetime(2026, 11, 8, 7, 30, 0, 123000, tzinfo=UTC)


def test_topics():
    assert P.topics("x") == {"cmd": "so101/x/cmd", "status": "so101/x/status", "result": "so101/x/result"}


# ---------------------------------------------------------------------------
# 実機の試験 C で見つかったもの（Build Log #022 節8-6）
# ---------------------------------------------------------------------------

def test_fullwidth_stop_key_works():
    # 日本語入力のまま打った「ｓ」でも止まる
    agent, rec, _ = make_agent(duration_s=5.0)
    agent.handle_payload(cmd())
    KeyController(agent, out=io.StringIO()).run(io.StringIO("ｓ\n"))
    assert agent.wait_idle()
    assert rec.results()[0]["reason"] == "operator_stop"


def test_fullwidth_label():
    holder = {}
    agent, rec, _ = make_agent(duration_s=0.05, label_provider=lambda c: holder["k"].ask_label(c))
    holder["k"] = keys = KeyController(agent, out=io.StringIO())
    agent.handle_payload(cmd())
    assert wait_until(lambda: keys._awaiting_label.is_set())
    keys.feed_line("ｙ")
    agent.wait_idle()
    assert rec.results()[0]["operator_label"] == "success"


def test_finished_at_excludes_label_wait():
    holder = {}
    agent, rec, _ = make_agent(duration_s=0.05, label_provider=lambda c: holder["k"].ask_label(c))
    holder["k"] = keys = KeyController(agent, out=io.StringIO())
    agent.handle_payload(cmd())
    assert wait_until(lambda: keys._awaiting_label.is_set())
    time.sleep(0.5)  # オペレーターが考えている時間
    answered = now()
    keys.feed_line("y")
    agent.wait_idle()
    finished = P.parse_iso(rec.results()[0]["finished_at"])
    assert finished < answered - timedelta(seconds=0.3)

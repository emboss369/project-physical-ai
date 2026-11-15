"""判断役のツールのテスト（段階 3 の受け入れのうち、コード側のガード）。AWS にはつながない。"""

from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "edge"))

import protocol as EDGE
import tools as T

NOW = datetime(2026, 11, 8, 13, 0, 0, tzinfo=UTC)


class FakeIot:
    def __init__(self, status: dict | None = None, raise_on_get: Exception | None = None):
        self.status = status
        self.raise_on_get = raise_on_get
        self.published: list[tuple[str, dict]] = []

    def get_retained_message(self, topic):
        if self.raise_on_get:
            raise self.raise_on_get
        return {"topic": topic, "payload": json.dumps(self.status).encode()}

    def publish(self, topic, qos, payload):
        assert qos == 1
        self.published.append((topic, json.loads(payload)))


class NoSuchKeyError(Exception):
    pass


class FakeS3:
    class exceptions:
        NoSuchKey = NoSuchKeyError

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.gets = 0

    def get_object(self, Bucket, Key):
        self.gets += 1
        if Key not in self.objects:
            raise NoSuchKeyError(Key)
        return {"Body": io.BytesIO(json.dumps(self.objects[Key]).encode())}


def status(state="IDLE", age_s=1.0, cmd_id=None):
    return {"v": 1, "state": state, "cmd_id": cmd_id, "ts": EDGE.iso(NOW - timedelta(seconds=age_s))}


def make(st=None, **kw):
    iot = FakeIot(st if st is not None else status(), **kw)
    s3 = FakeS3()
    rt = T.RobotTools(iot=iot, s3=s3, bucket="b", thing="so101-edge-01", clock=lambda: NOW, sleep=lambda s: None)
    return rt, iot, s3


# ---- get_robot_status ----

def test_status_idle():
    rt, _, _ = make()
    assert rt.get_robot_status()["state"] == "IDLE"


def test_status_stale_is_unknown():
    rt, _, _ = make(status("IDLE", age_s=31))
    st = rt.get_robot_status()
    assert st["state"] == "UNKNOWN" and st["last_state"] == "IDLE"


def test_status_unreadable_is_unknown():
    rt, _, _ = make(raise_on_get=RuntimeError("ResourceNotFound"))
    assert rt.get_robot_status()["state"] == "UNKNOWN"


def test_status_malformed_is_unknown():
    rt, _, _ = make({"v": 1})
    assert rt.get_robot_status()["state"] == "UNKNOWN"


# ---- dispatch_task（コードで強制するガード） ----

def test_dispatch_sends_valid_cmd_for_edge():
    rt, iot, _ = make()
    r = rt.dispatch_task("pick_yellow_block")
    assert r["ok"]
    ((topic, cmd),) = iot.published
    assert topic == "so101/so101-edge-01/cmd"
    parsed = EDGE.parse_command(json.dumps(cmd))  # エッジがそのまま受け付ける形
    assert parsed.task == "pick_yellow_block" and parsed.max_run_s == T.CMD_MAX_RUN_S
    assert set(cmd) == {"v", "cmd_id", "type", "task", "issued_at", "ttl_s", "max_run_s"}  # 角度・座標は載らない
    assert rt.dispatched == [cmd["cmd_id"]]


def test_dispatch_cmd_respects_edge_limit():
    from edge_agent import EDGE_MAX_RUN_S
    assert T.CMD_MAX_RUN_S <= EDGE_MAX_RUN_S


@pytest.mark.parametrize("task", ["rotate_joint_30deg", "", "PICK_YELLOW_BLOCK", "pick_yellow_block; stop"])
def test_dispatch_rejects_unknown_task(task):
    rt, iot, _ = make()
    r = rt.dispatch_task(task)
    assert not r["ok"] and r["reason"] == "unknown_task"
    assert iot.published == []


@pytest.mark.parametrize("st", [status("RUNNING", cmd_id="x"), status("STOPPING"), status("IDLE", age_s=60)])
def test_dispatch_rejects_when_not_idle_or_stale(st):
    rt, iot, _ = make(st)
    r = rt.dispatch_task("pick_yellow_block")
    assert not r["ok"] and r["reason"] == "not_idle"
    assert iot.published == []


def test_dispatch_rejects_when_status_unreadable():
    rt, iot, _ = make(raise_on_get=RuntimeError("x"))
    assert rt.dispatch_task("pick_yellow_block")["reason"] == "not_idle"
    assert iot.published == []


def test_second_dispatch_in_same_invocation_is_rejected():
    rt, iot, _ = make()
    assert rt.dispatch_task("pick_yellow_block")["ok"]
    r = rt.dispatch_task("pick_yellow_block")
    assert not r["ok"] and r["reason"] == "dispatch_limit"
    assert len(iot.published) == 1


def test_internal_status_check_is_not_recorded_as_tool_call():
    rt, _, _ = make()
    rt.dispatch_task("pick_yellow_block")
    assert [n for n, _ in rt.calls] == ["dispatch_task"]


# ---- get_result ----

def test_result_not_yet():
    rt, _, _ = make()
    r = rt.get_result("abc")
    assert r["done"] is False


def test_result_done():
    rt, _, s3 = make()
    s3.objects["results/so101-edge-01/abc.json"] = {
        "cmd_id": "abc", "state": "completed", "reason": "ok", "operator_label": "success",
        "started_at": "s", "finished_at": "f", "issued_at": "i", "received_at": "r"}
    r = rt.get_result("abc")
    assert {k: v for k, v in r.items() if k != "meaning"} == {
        "done": True, "state": "completed", "reason": "ok", "operator_label": "success",
        "started_at": "s", "finished_at": "f"}
    assert "成功と判定" in r["meaning"]


@pytest.mark.parametrize("res, must, must_not", [
    ({"state": "completed", "reason": "ok", "operator_label": "none"}, "分からない", "成功"),
    ({"state": "completed", "reason": "ok", "operator_label": "fail"}, "失敗と判定", "分からない"),
    ({"state": "aborted", "reason": "timeout", "operator_label": "none"}, "途中で止まった（timeout）", "成功"),
    ({"state": "rejected", "reason": "busy", "operator_label": "none"}, "実行しなかった（busy）", "成功"),
])
def test_result_meaning_does_not_overclaim(res, must, must_not):
    # completed/ok だけで「片付けた」と言わせない（節10-4）
    m = T.RobotTools._meaning(res)
    assert must in m and must_not not in m


def test_result_wait_is_capped(monkeypatch):
    # 150 秒を超えて待つよう頼んでも、150 秒で打ち切る（時間は偽装して進める）
    rt, _, _ = make()
    fake_now = [1000.0]
    monkeypatch.setattr(T.time, "monotonic", lambda: fake_now[0])
    def fake_sleep(sec):
        fake_now[0] += sec
    rt.sleep = fake_sleep
    r = rt.get_result("abc", wait_s=10_000)
    assert r["done"] is False
    assert fake_now[0] - 1000.0 == pytest.approx(T.RESULT_WAIT_MAX_S)


def test_result_arrives_while_waiting(monkeypatch):
    rt, _, s3 = make()
    fake_now = [0.0]
    monkeypatch.setattr(T.time, "monotonic", lambda: fake_now[0])
    def fake_sleep(sec):
        fake_now[0] += sec
        if fake_now[0] >= 10:  # 10 秒後に result が S3 に届く
            s3.objects["results/so101-edge-01/abc.json"] = {"state": "completed", "reason": "ok"}
    rt.sleep = fake_sleep
    r = rt.get_result("abc", wait_s=120)
    assert r["done"] and r["reason"] == "ok"
    assert 10 <= fake_now[0] < 13


def test_result_wait_negative_is_zero():
    rt, _, s3 = make()
    assert rt.get_result("abc", wait_s=-5)["done"] is False
    assert s3.gets == 1


# ---- stop ----

def test_stop_sends_stop_even_when_not_idle():
    rt, iot, _ = make(status("RUNNING", cmd_id="x"))
    assert rt.stop_robot()["ok"]
    ((_, cmd),) = iot.published
    assert EDGE.parse_command(json.dumps(cmd)).type == "stop"


# ---- Strands のツール定義 ----

def test_strands_tool_specs():
    pytest.importorskip("strands")
    import handler
    rt, _, _ = make()
    specs = {t.tool_spec["name"]: t.tool_spec for t in handler.build_tools(rt)}
    assert set(specs) == {"get_robot_status", "dispatch_task", "get_result", "stop_robot"}
    assert specs["dispatch_task"]["inputSchema"]["json"]["required"] == ["task"]
    assert "cmd_id" in specs["get_result"]["inputSchema"]["json"]["properties"]


def test_handler_rejects_missing_prompt():
    pytest.importorskip("strands")
    import handler
    assert handler.lambda_handler({}, None)["ok"] is False
    assert handler.lambda_handler({"prompt": "  "}, None)["ok"] is False

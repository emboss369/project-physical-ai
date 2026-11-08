"""MqttTransport のテスト。AWS にはつながず、偽の MQTT5 クライアントで確かめる。"""

from __future__ import annotations

import io
import json
import sys
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("awscrt")

from mqtt_transport import MqttTransport

CMD_TOPIC = "so101/so101-edge-01/cmd"


class FakeClient:
    def __init__(self, transport, *, connect=True, suback_codes=(1,), publish_error=None):
        self.t = transport
        self.connect_ok = connect
        self.suback_codes = suback_codes
        self.publish_error = publish_error
        self.published = []
        self.subscribed = []
        self.started = self.stopped = False

    def start(self):
        self.started = True
        if self.connect_ok:
            self.t._on_connection_success(SimpleNamespace())

    def stop(self):
        self.stopped = True

    def subscribe(self, pkt):
        self.subscribed.append(pkt)
        f = Future()
        f.set_result(SimpleNamespace(reason_codes=list(self.suback_codes)))
        return f

    def publish(self, pkt):
        self.published.append(pkt)
        f = Future()
        if self.publish_error:
            f.set_exception(self.publish_error)
        else:
            f.set_result(SimpleNamespace())
        return f

    def deliver(self, topic, payload: bytes):
        self.t._on_publish_received(SimpleNamespace(publish_packet=SimpleNamespace(topic=topic, payload=payload)))


def make(on_cmd=lambda b: "ok", **client_kw):
    holder = {}

    def factory(t):
        holder["c"] = FakeClient(t, **client_kw)
        return holder["c"]

    t = MqttTransport(endpoint="x-ats.iot.ap-northeast-1.amazonaws.com", cert="c", key="k", ca="ca",
                      client_id="so101-edge-01", cmd_topic=CMD_TOPIC, on_cmd=on_cmd,
                      client_factory=factory, log=io.StringIO())
    return t, holder


def test_connect_subscribes_cmd_with_qos1():
    t, h = make()
    t.connect(timeout=1)
    (pkt,) = h["c"].subscribed
    (sub,) = pkt.subscriptions
    assert sub.topic_filter == CMD_TOPIC
    assert int(sub.qos) == 1


def test_connect_timeout_stops_client():
    t, h = make(connect=False)
    with pytest.raises(TimeoutError):
        t.connect(timeout=0.1)
    assert h["c"].stopped


def test_subscribe_rejected_raises():
    # IoT ポリシーで Subscribe が許されていないと、SUBACK が 0x80 以上になる
    t, _ = make(suback_codes=(0x87,))
    with pytest.raises(PermissionError):
        t.connect(timeout=1)


def test_cmd_is_passed_to_agent_only_for_cmd_topic():
    got = []
    t, h = make(on_cmd=lambda b: got.append(b) or "started")
    t.connect(timeout=1)
    h["c"].deliver(CMD_TOPIC, b'{"v":1}')
    h["c"].deliver("so101/so101-edge-01/other", b"x")
    assert got == [b'{"v":1}']


def test_exception_in_handler_does_not_propagate():
    def boom(b):
        raise RuntimeError("bug")
    t, h = make(on_cmd=boom)
    t.connect(timeout=1)
    h["c"].deliver(CMD_TOPIC, b"{}")  # 例外が外に出なければよい
    assert "例外" in t._log.getvalue()


def test_publish_packet_fields():
    t, h = make()
    t.connect(timeout=1)
    t.publish("so101/so101-edge-01/status", {"state": "IDLE", "msg": "日本語"}, True)
    (pkt,) = h["c"].published
    assert pkt.topic == "so101/so101-edge-01/status"
    assert pkt.retain is True
    assert int(pkt.qos) == 1
    assert json.loads(pkt.payload) == {"state": "IDLE", "msg": "日本語"}


def test_publish_failure_is_counted():
    t, _ = make(publish_error=RuntimeError("offline"))
    t.connect(timeout=1)
    t.publish("so101/so101-edge-01/result", {}, False)
    assert t.publish_errors == 1

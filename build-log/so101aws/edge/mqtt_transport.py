"""AWS IoT Core への MQTT5 接続（段階 2）。

API は awsiotsdk 1.31.0 / awscrt 0.36.1 のソースで確認した（Build Log #022 節9）：
- awsiot.mqtt5_client_builder.mtls_from_path(cert_filepath, pri_key_filepath, endpoint=, client_id=,
  ca_filepath=, on_publish_received=, on_lifecycle_connection_success=, ...)
- client.start() / client.stop()
- client.publish(PublishPacket(topic, payload, qos, retain)) → future
- client.subscribe(SubscribePacket(subscriptions=[Subscription(topic_filter, qos)])) → future
- 受信は on_publish_received(PublishReceivedData)。.publish_packet.topic / .payload

クライアント ID はモノ名と同じにする（CLAUDE.md §4.1。ポリシーの iot:Connect が client/<モノ名> だけを許す）。
同じクライアント ID で二重に接続すると、先の接続が切られる（Session taken over）。エッジは1つだけ起動すること。
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from typing import Any

QOS1 = 1


class MqttTransport:
    def __init__(
        self,
        *,
        endpoint: str,
        cert: str,
        key: str,
        ca: str,
        client_id: str,
        cmd_topic: str,
        on_cmd: Callable[[bytes], Any],
        client_factory: Callable[..., Any] | None = None,
        log=sys.stderr,
    ):
        self.endpoint = endpoint
        self.cert = cert
        self.key = key
        self.ca = ca
        self.client_id = client_id
        self.cmd_topic = cmd_topic
        self.on_cmd = on_cmd
        self._client_factory = client_factory  # テストで差し替える
        self._log = log
        self._connected = threading.Event()
        self.client = None
        self.publish_errors = 0

    # ---- コールバック（awscrt のイベントループのスレッドで呼ばれる） ----

    def _on_publish_received(self, data) -> None:
        pkt = data.publish_packet
        if pkt.topic != self.cmd_topic:
            return
        try:
            outcome = self.on_cmd(bytes(pkt.payload or b""))
            print(f"[mqtt] cmd → {outcome}", file=self._log, flush=True)
        except Exception as e:  # noqa: BLE001  コールバックで例外を投げると受信が止まるので、記録して続ける
            print(f"[mqtt] cmd の処理で例外: {e!r}", file=self._log, flush=True)

    def _on_connection_success(self, data) -> None:
        print("[mqtt] 接続した", file=self._log, flush=True)
        self._connected.set()

    def _on_connection_failure(self, data) -> None:
        print(f"[mqtt] 接続に失敗: {getattr(data, 'exception', data)!r}", file=self._log, flush=True)

    def _on_disconnection(self, data) -> None:
        self._connected.clear()
        print(f"[mqtt] 切断: {getattr(data, 'exception', data)!r}", file=self._log, flush=True)

    # ---- 操作 ----

    def _build(self):
        if self._client_factory is not None:
            return self._client_factory(self)
        from awsiot import mqtt5_client_builder
        return mqtt5_client_builder.mtls_from_path(
            cert_filepath=self.cert,
            pri_key_filepath=self.key,
            endpoint=self.endpoint,
            client_id=self.client_id,
            ca_filepath=self.ca,
            on_publish_received=self._on_publish_received,
            on_lifecycle_connection_success=self._on_connection_success,
            on_lifecycle_connection_failure=self._on_connection_failure,
            on_lifecycle_disconnection=self._on_disconnection,
        )

    def connect(self, timeout: float = 15.0) -> None:
        self.client = self._build()
        self.client.start()
        if not self._connected.wait(timeout):
            self.client.stop()
            raise TimeoutError(f"{timeout} 秒以内に {self.endpoint} へ接続できなかった")
        from awscrt import mqtt5
        sub = mqtt5.SubscribePacket(subscriptions=[mqtt5.Subscription(topic_filter=self.cmd_topic, qos=mqtt5.QoS.AT_LEAST_ONCE)])
        suback = self.client.subscribe(sub).result(timeout)
        codes = [int(c) for c in getattr(suback, "reason_codes", [])]
        # 0/1/2 = 付与された QoS。それ以外（0x80 以上）は拒否
        if not codes or any(c >= 0x80 for c in codes):
            raise PermissionError(f"{self.cmd_topic} の購読が拒否された: {codes}")
        print(f"[mqtt] 購読した: {self.cmd_topic} (reason_codes={codes})", file=self._log, flush=True)

    def publish(self, topic: str, payload: dict, retain: bool) -> None:
        """非同期で送る（エージェントのロックの中から呼ばれるので待たない）。失敗は記録する。"""
        from awscrt import mqtt5
        pkt = mqtt5.PublishPacket(
            topic=topic,
            payload=json.dumps(payload, ensure_ascii=False).encode(),
            qos=mqtt5.QoS.AT_LEAST_ONCE,
            retain=retain,
        )
        fut = self.client.publish(pkt)

        def done(f):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001  送信の失敗は記録して数える（エッジの動作は止めない）
                self.publish_errors += 1
                print(f"[mqtt] publish 失敗 {topic}: {e!r}", file=self._log, flush=True)

        fut.add_done_callback(done)

    def close(self, timeout: float = 5.0) -> None:
        if self.client is not None:
            self.client.stop()

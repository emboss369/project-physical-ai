"""判断役のツール（CLAUDE.md §4.5）。

ガードはプロンプトに頼らず、ここのコードで強制する。
- 許可リストにないタスクは送らない
- 直前の status が IDLE かつ新しい（30 秒以内）ときだけ送る
- 1 回の Lambda 呼び出しで送れる指令は 1 件だけ
- 関節角度・座標・速度は送らない（cmd にはタスク名しか載せない）

retained の status は反映が遅れることがある（Build Log #022 節9-4）。IDLE に見えても実は動いていることがありうるが、
そのときはエッジが busy で拒否するので、二重には動かない。

AWS のクライアントは外から渡す（テストでは偽物を渡す）。
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

ALLOWED_TASKS = {
    "pick_yellow_block": "黄色いレゴブロックを掴んで白いケースに入れる",
}
STATUS_STALE_S = 30.0
CMD_TTL_S = 60
CMD_MAX_RUN_S = 90  # エッジの PolicyRunner：動かす 20 秒 + 起動 15 秒 + 後始末 6 秒 + 余裕。エッジ側の上限 120 秒を超えない
RESULT_WAIT_MAX_S = 150.0


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RobotTools:
    def __init__(self, *, iot, s3, bucket: str, thing: str,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 sleep: Callable[[float], None] = time.sleep,
                 max_dispatch: int = 1):
        self.iot = iot
        self.s3 = s3
        self.bucket = bucket
        self.thing = thing
        self.clock = clock
        self.sleep = sleep
        self.max_dispatch = max_dispatch
        self.dispatched: list[str] = []      # この呼び出しで送った cmd_id
        self.calls: list[tuple[str, dict]] = []  # ツールの呼び出し記録（テストと応答に使う）
        self.topic = {k: f"so101/{thing}/{k}" for k in ("cmd", "status", "result")}

    # ---- status ----

    def get_robot_status(self) -> dict[str, Any]:
        """ロボットの現在の状態を返す。古ければ state を UNKNOWN にする。"""
        self.calls.append(("get_robot_status", {}))
        try:
            r = self.iot.get_retained_message(topic=self.topic["status"])
        except Exception as e:  # noqa: BLE001  status が読めないときは「不明」として扱う（送らない側に倒す）
            return {"state": "UNKNOWN", "reason": f"status を読めない: {type(e).__name__}"}
        try:
            st = json.loads(r["payload"])
            ts = datetime.fromisoformat(st["ts"])
        except (KeyError, ValueError, TypeError) as e:
            return {"state": "UNKNOWN", "reason": f"status の形式が不正: {e}"}
        age = (self.clock() - ts).total_seconds()
        if age > STATUS_STALE_S:
            return {"state": "UNKNOWN", "reason": f"status が古い（{age:.0f} 秒前）。エッジが止まっている可能性",
                    "last_state": st.get("state"), "age_s": round(age, 1)}
        return {"state": st.get("state", "UNKNOWN"), "cmd_id": st.get("cmd_id"), "age_s": round(age, 1)}

    # ---- dispatch ----

    def dispatch_task(self, task: str) -> dict[str, Any]:
        """許可リストのタスクをエッジに送る。完了は待たない。"""
        self.calls.append(("dispatch_task", {"task": task}))
        if task not in ALLOWED_TASKS:
            return {"ok": False, "reason": "unknown_task",
                    "message": f"'{task}' は許可されていない。使えるタスク: {sorted(ALLOWED_TASKS)}"}
        if len(self.dispatched) >= self.max_dispatch:
            return {"ok": False, "reason": "dispatch_limit",
                    "message": f"1 回の依頼で送れる指令は {self.max_dispatch} 件まで。送信済み: {self.dispatched}"}
        st = self.get_robot_status()
        self.calls.pop()  # 内部で呼んだ分は記録から外す
        if st["state"] != "IDLE":
            return {"ok": False, "reason": "not_idle", "message": f"ロボットが待機中ではない: {st}"}
        cmd = {
            "v": 1, "cmd_id": str(uuid.uuid4()), "type": "run_task", "task": task,
            "issued_at": iso(self.clock()), "ttl_s": CMD_TTL_S, "max_run_s": CMD_MAX_RUN_S,
        }
        self.iot.publish(topic=self.topic["cmd"], qos=1, payload=json.dumps(cmd).encode())
        self.dispatched.append(cmd["cmd_id"])
        return {"ok": True, "cmd_id": cmd["cmd_id"], "task": task, "issued_at": cmd["issued_at"],
                "message": "送った。完了は get_result で確かめる"}

    # ---- result ----

    def _read_result(self, cmd_id: str) -> dict | None:
        try:
            o = self.s3.get_object(Bucket=self.bucket, Key=f"results/{self.thing}/{cmd_id}.json")
        except self.s3.exceptions.NoSuchKey:
            return None
        return json.loads(o["Body"].read())

    def get_result(self, cmd_id: str, wait_s: float = 0) -> dict[str, Any]:
        """指令の結果を読む。wait_s 秒まで待つ（上限あり）。"""
        self.calls.append(("get_result", {"cmd_id": cmd_id, "wait_s": wait_s}))
        wait_s = max(0.0, min(float(wait_s), RESULT_WAIT_MAX_S))
        deadline = time.monotonic() + wait_s
        while True:
            res = self._read_result(cmd_id)
            if res is not None:
                out = {"done": True, **{k: res.get(k) for k in
                                        ("state", "reason", "operator_label", "started_at", "finished_at")}}
                out["meaning"] = self._meaning(out)
                return out
            if time.monotonic() >= deadline:
                return {"done": False, "message": "まだ結果が届いていない（実行中か、エッジに届いていない）"}
            self.sleep(min(2.0, max(0.0, deadline - time.monotonic())))

    @staticmethod
    def _meaning(r: dict) -> str:
        """result の意味を、言いすぎないように添える。

        ポリシーには成功を知らせる仕組みがない（CLAUDE.md §4.3）。completed/ok は「動作が最後まで終わった」だけで、
        ブロックが入ったかは分からない。判断役が「片付けました」と言い切らないよう、事実をコードから渡す（Build Log #022 節10-4）。
        """
        label = r.get("operator_label")
        if r.get("state") == "completed":
            base = "ロボットの動作が最後まで終わった。"
        elif r.get("state") == "aborted":
            base = f"ロボットの動作は途中で止まった（{r.get('reason')}）。"
        else:
            base = f"エッジがこの指令を実行しなかった（{r.get('reason')}）。"
        if label == "success":
            return base + "オペレーターが目で見て、成功と判定した。"
        if label == "fail":
            return base + "オペレーターが目で見て、失敗と判定した。"
        return base + "ブロックがケースに入ったかどうかは、誰も判定していないので分からない。"

    # ---- stop ----

    def stop_robot(self) -> dict[str, Any]:
        """実行中の動作を止める指令を送る（止める側の指令にはガードを付けない）。"""
        self.calls.append(("stop_robot", {}))
        cmd = {"v": 1, "cmd_id": str(uuid.uuid4()), "type": "stop", "issued_at": iso(self.clock())}
        self.iot.publish(topic=self.topic["cmd"], qos=1, payload=json.dumps(cmd).encode())
        return {"ok": True, "cmd_id": cmd["cmd_id"]}

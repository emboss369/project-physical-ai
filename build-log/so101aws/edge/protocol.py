"""MQTT メッセージの仕様（CLAUDE.md §4.2・§4.3）。

ここは純粋な関数とデータだけを置く。MQTT・スレッド・時刻の取得は持たない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = 1

# クラウドが送れるタスクの許可リスト（§4.3。初期は 1 つだけ）
ALLOWED_TASKS = frozenset({"pick_yellow_block"})

# state
IDLE = "IDLE"
RUNNING = "RUNNING"
STOPPING = "STOPPING"

# result.state
COMPLETED = "completed"
ABORTED = "aborted"
REJECTED = "rejected"

# result.reason
R_OK = "ok"
R_OPERATOR_STOP = "operator_stop"
R_CLOUD_STOP = "cloud_stop"
R_TIMEOUT = "timeout"
R_EXPIRED = "expired"
R_BUSY = "busy"
R_UNKNOWN_TASK = "unknown_task"
R_INVALID = "invalid"
# §4.3 の一覧にない追加。Runner が 0 以外の終了コードで終わったとき（§4.4 の状態遷移表に該当行がないため）
R_RUNNER_ERROR = "runner_error"

CMD_RUN_TASK = "run_task"
CMD_STOP = "stop"


def topics(thing: str) -> dict[str, str]:
    return {
        "cmd": f"so101/{thing}/cmd",
        "status": f"so101/{thing}/status",
        "result": f"so101/{thing}/result",
    }


def iso(dt: datetime | None) -> str | None:
    """UTC の ISO 8601（ミリ秒、末尾 Z）。E1 の計算に使うのでミリ秒まで残す。"""
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)  # Python 3.11 以降は末尾の Z を受け付ける
    if dt.tzinfo is None:
        raise ValueError("timezone is required")
    return dt


@dataclass(frozen=True)
class Command:
    cmd_id: str
    type: str
    issued_at: datetime
    task: str | None = None
    ttl_s: float | None = None
    max_run_s: float | None = None
    issued_at_raw: str = ""


class InvalidCommand(ValueError):
    """スキーマ不正。cmd_id が読めた場合は持たせる（result に載せるため）。"""

    def __init__(self, message: str, cmd_id: str | None = None, issued_at_raw: str | None = None):
        super().__init__(message)
        self.cmd_id = cmd_id
        self.issued_at_raw = issued_at_raw


def _positive_number(d: dict, key: str, cmd_id: str | None, raw: str | None) -> float:
    v = d.get(key)
    # bool は int のサブクラスなので明示的に弾く
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise InvalidCommand(f"{key} must be a positive number", cmd_id, raw)
    return float(v)


def parse_command(payload: bytes | str) -> Command:
    """cmd のペイロードを検証して Command にする。不正なら InvalidCommand。"""
    try:
        d = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as e:
        raise InvalidCommand(f"not json: {e}") from e
    if not isinstance(d, dict):
        raise InvalidCommand("not an object")

    cmd_id = d.get("cmd_id") if isinstance(d.get("cmd_id"), str) and d.get("cmd_id") else None
    raw = d.get("issued_at") if isinstance(d.get("issued_at"), str) else None

    if d.get("v") != VERSION:
        raise InvalidCommand("version mismatch", cmd_id, raw)
    if cmd_id is None:
        raise InvalidCommand("cmd_id is required")
    if raw is None:
        raise InvalidCommand("issued_at is required", cmd_id)
    try:
        issued_at = parse_iso(raw)
    except ValueError as e:
        raise InvalidCommand(f"bad issued_at: {e}", cmd_id, raw) from e

    t = d.get("type")
    if t == CMD_STOP:
        return Command(cmd_id=cmd_id, type=CMD_STOP, issued_at=issued_at, issued_at_raw=raw)
    if t != CMD_RUN_TASK:
        raise InvalidCommand("unknown type", cmd_id, raw)

    task = d.get("task")
    if not isinstance(task, str) or not task:
        raise InvalidCommand("task is required", cmd_id, raw)
    ttl_s = _positive_number(d, "ttl_s", cmd_id, raw)
    max_run_s = _positive_number(d, "max_run_s", cmd_id, raw)
    return Command(
        cmd_id=cmd_id,
        type=CMD_RUN_TASK,
        issued_at=issued_at,
        task=task,
        ttl_s=ttl_s,
        max_run_s=max_run_s,
        issued_at_raw=raw,
    )


def make_result(
    *,
    cmd_id: str | None,
    state: str,
    reason: str,
    issued_at: str | None,
    received_at: datetime | None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    operator_label: str = "none",
) -> dict[str, Any]:
    return {
        "v": VERSION,
        "cmd_id": cmd_id,
        "state": state,
        "reason": reason,
        "issued_at": issued_at,
        "received_at": iso(received_at),
        "started_at": iso(started_at),
        "finished_at": iso(finished_at),
        "operator_label": operator_label,
    }


def make_status(state: str, cmd_id: str | None, ts: datetime) -> dict[str, Any]:
    return {"v": VERSION, "state": state, "cmd_id": cmd_id, "ts": iso(ts)}

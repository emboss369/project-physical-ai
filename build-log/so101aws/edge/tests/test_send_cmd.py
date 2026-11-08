"""scripts/send_cmd.py の、AWS につながない部分のテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protocol as P
import send_cmd as S


def test_make_cmd_is_valid_for_edge():
    # send_cmd が作る指令を、エッジの検証がそのまま受け付けること（両者の仕様のずれを防ぐ）
    c = S.make_cmd(max_run_s=30)
    import json
    parsed = P.parse_command(json.dumps(c))
    assert parsed.type == "run_task" and parsed.task == "pick_yellow_block" and parsed.max_run_s == 30


def test_make_stop_is_valid_for_edge():
    import json
    parsed = P.parse_command(json.dumps(S.make_cmd(type_="stop")))
    assert parsed.type == "stop"


def test_latency_ms():
    r = {"issued_at": "2026-11-08T13:00:00.000Z", "received_at": "2026-11-08T13:00:00.123Z"}
    assert abs(S.latency_ms(r) - 123.0) < 1e-6


def test_summarize():
    s = S.summarize([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert s["n"] == 10 and s["min"] == 10 and s["max"] == 100
    assert s["median"] == 55
    assert s["p90"] == 90


def test_topics_match_edge():
    assert P.topics(S.THING) == S.TOPIC

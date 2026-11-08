"""scripts/emergency_stop.sh のテスト。偽の lerobot-rollout で、3 段階の止め方と「関係ないプロセスを止めない」ことを確かめる。

STOP_PATTERN をテスト用の一時ディレクトリに絞るので、本物の lerobot-rollout が動いていても止めない。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

FAKE = """#!/usr/bin/env python3
import os, signal, sys, time
mode = os.environ.get("MODE", "graceful")
def done(*a):
    time.sleep(0.2); sys.exit(0)
if mode == "graceful":
    signal.signal(signal.SIGINT, done); signal.signal(signal.SIGTERM, done)
elif mode == "ignore_int":
    signal.signal(signal.SIGINT, signal.SIG_IGN); signal.signal(signal.SIGTERM, done)
else:
    signal.signal(signal.SIGINT, signal.SIG_IGN); signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("ready", flush=True)
time.sleep(60)
"""


@pytest.fixture
def fake_bin(tmp_path):
    d = tmp_path / "bin"
    d.mkdir()
    exe = d / "lerobot-rollout"
    exe.write_text(FAKE)
    exe.chmod(0o755)
    return exe


def _env(fake_bin: Path) -> dict:
    # 本番と同じ形（python … /bin/lerobot-rollout）で、かつこのテストの一時ディレクトリに限る
    pattern = f"^[^ ]*python[0-9.]* {fake_bin.parent}/lerobot-rollout( |$)"
    return {**os.environ, "STOP_PATTERN": pattern, "GRACE_S": "1"}


def _spawn(fake_bin: Path, mode: str) -> subprocess.Popen:
    p = subprocess.Popen([sys.executable, str(fake_bin)], env={**os.environ, "MODE": mode},
                         stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "ready"  # シグナルハンドラが入ってから
    return p


@pytest.mark.parametrize("mode, last_signal", [
    ("graceful", "SIGINT"),
    ("ignore_int", "SIGTERM"),
    ("ignore_all", "SIGKILL"),
])
def test_emergency_stop_escalation(fake_bin, mode, last_signal):
    p = _spawn(fake_bin, mode)
    out = subprocess.run([str(SCRIPTS / "emergency_stop.sh")], check=False, env=_env(fake_bin),
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert f"停止した（{last_signal}）" in out.stdout
    assert p.wait(5) is not None


def test_emergency_stop_does_not_touch_unrelated_processes(fake_bin):
    # コマンド文字列に lerobot-rollout を含むだけのシェルは止めない（節9-1 で実際に起きた）
    decoy = subprocess.Popen(["bash", "-c", f"sleep 30; : {fake_bin}"])
    try:
        out = subprocess.run([str(SCRIPTS / "emergency_stop.sh")], check=False, env=_env(fake_bin),
                             capture_output=True, text=True, timeout=30)
        assert "動いていない" in out.stdout
        time.sleep(0.2)
        assert decoy.poll() is None
    finally:
        decoy.kill()


def test_default_pattern_matches_real_command_line_only():
    # 本番のパターンが、実際の lerobot-rollout のコマンドラインに一致し、シェルや tail には一致しないこと
    import re
    src = (SCRIPTS / "emergency_stop.sh").read_text()
    pattern = re.search(r"DEFAULT_PATTERN='([^']+)'", src).group(1)
    real = ("/home/hiro/development/lerobot-workspace/.venv/bin/python3 "
            "/home/hiro/development/lerobot-workspace/.venv/bin/lerobot-rollout --robot.type=so101_follower")
    assert re.search(pattern, real)
    assert not re.search(pattern, "/bin/bash -c cd x && ./bin/lerobot-rollout --help")
    assert not re.search(pattern, "tail -f /mnt/data/lerobot-outputs/logs/rollout_smolvla_x.log")
    assert not re.search(pattern, "python3 edge_agent.py --runner policy")

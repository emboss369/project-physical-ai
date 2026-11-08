"""PolicyRunner のテスト用：lerobot-rollout のふりをするプロセス。

環境変数
- DURATION      : この秒数で自然に終わる（終了コード 0）
- FAKE_MODE     : graceful（既定。SIGINT/SIGTERM で TEARDOWN 秒後に 0 で終わる）
                  ignore_int（SIGINT を無視、SIGTERM で終わる）
                  ignore_all（SIGINT/SIGTERM とも無視。SIGKILL でしか止まらない）
- FAKE_TEARDOWN : 後始末にかかる秒数（既定 0.2）
"""

import os
import signal
import sys
import time

duration = float(os.environ.get("DURATION", "5"))
mode = os.environ.get("FAKE_MODE", "graceful")
teardown = float(os.environ.get("FAKE_TEARDOWN", "0.2"))
stop = {"flag": False}


def handler(signum, frame):
    stop["flag"] = True


if mode == "graceful":
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
elif mode == "ignore_int":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, handler)
elif mode == "ignore_all":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

print("ready", flush=True)
t0 = time.monotonic()
while time.monotonic() - t0 < duration and not stop["flag"]:
    time.sleep(0.01)
time.sleep(teardown)  # 開始姿勢へ戻る・切断のかわり
sys.exit(0)

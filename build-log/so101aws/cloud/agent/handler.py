"""Lambda: 判断役（CLAUDE.md §4.5）。

  aws lambda invoke --function-name so101-judge --payload '{"prompt":"黄色いブロックを片付けて"}' ...

Strands Agents 1.64.0（API はインストールしたパッケージで確認）:
  from strands import Agent, tool / from strands.models import BedrockModel / str(agent_result) で本文
"""

from __future__ import annotations

import os
import time

import boto3

from prompts import SYSTEM_PROMPT
from tools import RobotTools


def build_tools(rt: RobotTools):
    from strands import tool

    @tool
    def get_robot_status() -> dict:
        """ロボットの現在の状態（IDLE / RUNNING / STOPPING / UNKNOWN）を返す。タスクを頼む前に必ず呼ぶ。"""
        return rt.get_robot_status()

    @tool
    def dispatch_task(task: str) -> dict:
        """許可されたタスクをロボットに頼む。完了は待たない。

        Args:
            task: タスク名。使えるのは pick_yellow_block だけ
        """
        return rt.dispatch_task(task)

    @tool
    def get_result(cmd_id: str, wait_s: float = 0) -> dict:
        """頼んだタスクの結果を読む。

        Args:
            cmd_id: dispatch_task が返した cmd_id
            wait_s: 結果が届くまで待つ秒数（最大 150）
        """
        return rt.get_result(cmd_id, wait_s)

    @tool
    def stop_robot() -> dict:
        """実行中の動作を止める。"""
        return rt.stop_robot()

    return [get_robot_status, dispatch_task, get_result, stop_robot]


def lambda_handler(event, context):
    from strands import Agent
    from strands.models import BedrockModel

    prompt = (event or {}).get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return {"ok": False, "error": "prompt（文字列）が要る"}

    t0 = time.monotonic()
    # 呼び出しごとに作り直す（1 回の呼び出しで送れる指令は 1 件、のカウンタもここで初期化される）
    rt = RobotTools(
        iot=boto3.client("iot-data", endpoint_url=f"https://{os.environ['IOT_ENDPOINT']}"),
        s3=boto3.client("s3"),
        bucket=os.environ["RESULTS_BUCKET"],
        thing=os.environ.get("THING", "so101-edge-01"),
    )
    model = BedrockModel(
        model_id=os.environ["MODEL_ID"],
        region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
        max_tokens=1024,
        temperature=0.0,
    )
    agent = Agent(model=model, tools=build_tools(rt), system_prompt=SYSTEM_PROMPT, callback_handler=None)
    result = agent(prompt)
    return {
        "ok": True,
        "reply": str(result).strip(),
        "dispatched": rt.dispatched,
        "tool_calls": [name for name, _ in rt.calls],
        "elapsed_s": round(time.monotonic() - t0, 1),
    }

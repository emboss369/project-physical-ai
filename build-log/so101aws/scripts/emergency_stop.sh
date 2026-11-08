#!/usr/bin/env bash
# 緊急停止（CLAUDE.md §4.4）。edge_agent とは独立に、lerobot-rollout を止める。
#
#   1) SIGINT  → lerobot-rollout は開始時の姿勢に戻ってから脱力して終わる
#   2) SIGTERM → （1 で終わらなければ）
#   3) SIGKILL → （それでも終わらなければ）後始末なしで即死。サーボは最後の位置で力を保つと思われる（推測）
#
# 電源を切るのが最終手段であることは変わらない。
set -u
# 「python で …/bin/lerobot-rollout を動かしているプロセス」だけに一致させる。
# 'bin/lerobot-rollout' を含むだけで一致させると、その文字列を打ったシェルまで止めてしまう（実際に起きた。Build Log #022 節9-1）
DEFAULT_PATTERN='^[^ ]*python[0-9.]* [^ ]*/bin/lerobot-rollout( |$)'
PATTERN="${STOP_PATTERN:-$DEFAULT_PATTERN}"   # テストでは STOP_PATTERN で、テスト用の偽プロセスだけに絞る
GRACE_S="${GRACE_S:-10}"  # 実測：SIGINT から終了まで 5.6 秒（開始姿勢へ戻る 3 秒 + 切断 約 2 秒）。Build Log #022 節8-5

mapfile -t pids < <(pgrep -f "$PATTERN" || true)
[ "${#pids[@]}" -eq 0 ] && { echo "lerobot-rollout は動いていない"; exit 0; }

for sig in INT TERM KILL; do
  echo "$(date +%T.%3N) SIG$sig → ${pids[*]}"
  kill -s "$sig" "${pids[@]}" 2>/dev/null || true
  [ "$sig" = KILL ] && break
  for _ in $(seq $((GRACE_S * 10))); do
    sleep 0.1
    mapfile -t pids < <(pgrep -f "$PATTERN" || true)
    [ "${#pids[@]}" -eq 0 ] && { echo "$(date +%T.%3N) 停止した（SIG$sig）"; exit 0; }
  done
done
sleep 0.5
pgrep -f "$PATTERN" >/dev/null && { echo "まだ動いている。電源を切ること" >&2; exit 1; }
echo "$(date +%T.%3N) 停止した（SIGKILL）"

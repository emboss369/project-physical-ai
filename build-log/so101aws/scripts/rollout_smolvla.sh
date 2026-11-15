#!/usr/bin/env bash
# SmolVLA で SO-101 を1回動かす（Build Log #022 節4-3 のコマンドが土台）。
# PolicyRunner（段階1の後半）が呼ぶコマンドの元にもなる。
#
#   DURATION=30 ./rollout_smolvla.sh        # 30 秒で自然に終わる
#   LOG=/path/to/log ./rollout_smolvla.sh
#
# どう終わっても（時間切れ・SIGINT・SIGTERM）、lerobot-rollout は開始時の姿勢に 3 秒かけて戻ってから
# トルクを切る（disable_torque_on_disconnect=True）。開始時の姿勢は「脱力しても安全な姿勢」にしておくこと。
set -euo pipefail

DURATION="${DURATION:-30}"
WS="${LEROBOT_WS:-$HOME/development/lerobot-workspace}"
POLICY="${POLICY:-/mnt/data/lerobot-outputs/train/smolvla_yellow_lego/checkpoints/last/pretrained_model}"
LOG="${LOG:-/mnt/data/lerobot-outputs/logs/rollout_smolvla_$(date +%Y%m%d_%H%M%S).log}"
WRIST=/dev/v4l/by-id/usb-Innomaker_Innomaker-U20CAM-1080p-S1_SN0001-video-index0
FRONT=/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0

: "${FOLLOWER_ARM:?FOLLOWER_ARM が未設定}"
for dev in "$FOLLOWER_ARM" "$WRIST" "$FRONT"; do
  [ -e "$dev" ] || { echo "見つからない: $dev" >&2; exit 2; }
done
# 排他：同じアーム・カメラを使う LeRobot のプロセスが動いていないこと（CLAUDE.md §4.4）
if pgrep -f '^[^ ]*python[0-9.]* [^ ]*/bin/lerobot-(rollout|teleoperate|record)( |$)' >/dev/null; then
  echo "別の LeRobot プロセスが動いている" >&2; exit 3
fi

cd "$WS/lerobot"
# shellcheck disable=SC1091
source ../.venv/bin/activate
mkdir -p "$(dirname "$LOG")"
echo "[rollout] pid=$$ duration=${DURATION}s log=$LOG" >&2

# exec で置き換えるので、このシェルの PID = lerobot-rollout の PID になる（シグナルを直接届けるため）
exec lerobot-rollout \
  --robot.type=so101_follower --robot.port="$FOLLOWER_ARM" --robot.id=right_follower_arm \
  --robot.cameras="{
    wrist: {type: opencv, index_or_path: $WRIST, width: 640, height: 480, fps: 30},
    front: {type: opencv, index_or_path: $FRONT, width: 640, height: 480, fps: 30}
  }" \
  --policy.path="$POLICY" \
  --rename_map='{"observation.images.front":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}' \
  --fps=30 --task="Put the yellow lego block into the white case" \
  --display_data=false --duration="$DURATION" \
  > >(trap "" INT TERM; exec tee -a "$LOG") 2>&1   # tee は INT/TERM を無視する（先に死ぬと後始末のログが書けない）

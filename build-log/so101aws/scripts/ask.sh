#!/usr/bin/env bash
# 判断役（Lambda so101-judge）に日本語で頼む。
#   ./ask.sh "黄色いブロックを片付けて"
#
# AWS CLI は読み取りタイムアウト（既定 60 秒）で再試行することがあり、そうなると判断役が二重に呼ばれる。
# 判断役は結果を最大 150 秒待つので、読み取りタイムアウトを Lambda の上限（300 秒）より長くし、再試行を切る。
# （二重に呼ばれても、エッジの busy 拒否と重複排除で同時に2回は動かない。CLAUDE.md §4.5）
set -euo pipefail
PROMPT="${1:?使い方: $0 \"依頼文\"}"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
payload=$(python3 -c 'import json,sys; print(json.dumps({"prompt": sys.argv[1]}, ensure_ascii=False))' "$PROMPT")
AWS_MAX_ATTEMPTS=1 aws lambda invoke \
  --function-name so101-judge \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 320 \
  --payload "$payload" \
  "$OUT" >/dev/null
python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), ensure_ascii=False, indent=2))' "$OUT"

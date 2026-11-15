#!/usr/bin/env bash
# 判断役の Lambda の zip を作る（x86_64、Python 3.12）。
# 依存は cloud/agent/requirements.txt。Lambda 用の Linux の wheel だけを使う（--only-binary）。
# 出力: build/agent.zip（Git 管理外）。サイズは 2026-11-08 時点で zip 約 29MB / 展開後 約 77MB（直接アップロードの上限 50MB 以内）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build"
PKG="$OUT/package"
mkdir -p "$OUT"
if [ -d "$PKG" ]; then
  find "$PKG" -mindepth 1 -delete
fi
uv pip install --quiet --target "$PKG" \
  --python-platform x86_64-manylinux2014 --python-version 3.12 --only-binary :all: \
  -r "$ROOT/cloud/agent/requirements.txt"
cp "$ROOT/cloud/agent/handler.py" "$ROOT/cloud/agent/tools.py" "$ROOT/cloud/agent/prompts.py" "$PKG/"
rm -f "$OUT/agent.zip"
(cd "$PKG" && zip -qr -X "$OUT/agent.zip" . -x '*/__pycache__/*' '*.pyc')
ls -lh "$OUT/agent.zip"

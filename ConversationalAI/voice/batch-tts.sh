#!/usr/bin/env bash
# テキストファイルを1行1本として、Irodori-TTS-Server で WAV を一括生成する。
#
# 使い方:
#   ./batch-tts.sh lines.txt
#   OUT_DIR=~/somewhere PREFIX=test VOICE=none CAPTION="..." SEED=1234 ./batch-tts.sh lines.txt
#
# - 空行と # で始まる行は飛ばす。番号は「読み上げた行」の通し番号（001, 002, ...）
# - 出力: $OUT_DIR/$PREFIX-NNN.wav と $OUT_DIR/index.tsv（番号・元の行番号・seed・テキスト）
# - 既にある WAV は飛ばす（途中で止めても再実行で続きから）。作り直すときは FORCE=1
# - サーバーは先に起動しておくこと（Build Log #013）:
#     cd ~/development/Irodori-TTS-Server && uv run --no-sync python -m irodori_openai_tts --host 0.0.0.0 --port 8088
set -euo pipefail

INPUT="${1:?使い方: $0 <テキストファイル>}"
OUT_DIR="${OUT_DIR:-$HOME/development/ComfyUI/output/WAV}"
PREFIX="${PREFIX:-midori-ptn}"
VOICE="${VOICE:-sakura_midori}"
CAPTION="${CAPTION:-}"
SEED="${SEED:-}"
SERVER="${SERVER:-http://localhost:8088}"
FORCE="${FORCE:-0}"

[ -f "$INPUT" ] || { echo "入力ファイルがありません: $INPUT" >&2; exit 1; }
curl -sf "$SERVER/health" > /dev/null || { echo "Irodori-TTS-Server に繋がりません: $SERVER" >&2; exit 1; }
mkdir -p "$OUT_DIR"

INDEX="$OUT_DIR/index.tsv"
[ -f "$INDEX" ] || printf 'file\tsrc_line\tseed\ttext\n' > "$INDEX"

n=0
src=0
ok=0
skip=0
fail=0
while IFS= read -r line || [ -n "$line" ]; do
  src=$((src + 1))
  line="${line%$'\r'}"
  [[ -z "${line//[[:space:]]/}" || "$line" == \#* ]] && continue
  n=$((n + 1))
  name=$(printf '%s-%03d.wav' "$PREFIX" "$n")
  out="$OUT_DIR/$name"

  if [ -f "$out" ] && [ "$FORCE" != 1 ]; then
    skip=$((skip + 1))
    continue
  fi

  body=$(jq -n --arg t "$line" --arg v "$VOICE" --arg c "$CAPTION" --arg s "$SEED" \
    '{model:"irodori-tts", input:$t, voice:$v, response_format:"wav"}
     + (if $c != "" then {caption:$c} else {} end)
     + (if $s != "" then {seed:($s|tonumber)} else {} end)')

  tmp="$out.part"
  headers=$(curl -s -D - -o "$tmp" -w '%{http_code}' -X POST "$SERVER/v1/audio/speech" \
    -H "Content-Type: application/json" -d "$body") || true
  code="${headers##*$'\n'}"
  if [ "$code" != 200 ]; then
    echo "[$name] 失敗 (HTTP $code): $line" >&2
    rm -f "$tmp"
    fail=$((fail + 1))
    continue
  fi
  mv "$tmp" "$out"
  used=$(printf '%s' "$headers" | grep -i '^x-irodori-seed:' | tr -d '\r' | awk '{print $2}')
  printf '%s\t%d\t%s\t%s\n' "$name" "$src" "$used" "$line" >> "$INDEX"
  ok=$((ok + 1))
  echo "[$name] seed=$used $line"
done < "$INPUT"

echo "完了: 生成 $ok / スキップ $skip / 失敗 $fail（出力先 $OUT_DIR）"

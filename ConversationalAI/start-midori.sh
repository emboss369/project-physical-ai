#!/usr/bin/env bash
#
# 佐倉みどりを起動する（Build Log #013）
#
#   ./start-midori.sh            Irodori-TTS → バックエンド → Electron（ペットモード）
#   ./start-midori.sh --check    起動せず、3つのプロセスの生死だけ確認する
#   ./start-midori.sh --no-app   Electron を起動しない（ブラウザで使うとき）
#   ./start-midori.sh --no-warm  LLM の事前ロードをしない
#
# すでに動いているサーバーは再利用し、終了時にも止めない。
# このスクリプトが起動したものだけを、終了時に片付ける。

set -uo pipefail

IRODORI_DIR="$HOME/development/Irodori-TTS-Server"
VTUBER_DIR="$HOME/development/open-llm-vtuber-lab/Open-LLM-VTuber"
WEB_DIR="$HOME/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sakura-midori"

OLLAMA_URL="http://localhost:11434"
TTS_URL="http://localhost:8088"
VTUBER_URL="http://localhost:12393"
LLM_MODEL="qwen3-vl-8k"

DO_APP=1; DO_WARM=1; CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --check)   CHECK_ONLY=1 ;;
    --no-app)  DO_APP=0 ;;
    --no-warm) DO_WARM=0 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "不明な引数: $arg （--help を見て）" >&2; exit 2 ;;
  esac
done

TTS_PID=""; VTUBER_PID=""

say()  { printf '\033[1;36m▶\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✅\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠️\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31m❌\033[0m %s\n' "$*" >&2; exit 1; }

alive() { curl -s -o /dev/null --max-time 2 "$1"; }

# $1=URL $2=表示名 $3=秒数
wait_for() {
  local url="$1" name="$2" limit="${3:-120}" i=0
  while ! alive "$url"; do
    i=$((i+1))
    [ "$i" -ge "$limit" ] && return 1
    printf '\r   %s の起動待ち... %ds' "$name" "$i"
    sleep 1
  done
  [ "$i" -gt 0 ] && printf '\r\033[K'
  return 0
}

cleanup() {
  local code=$?
  echo
  # 自分で起動したものだけ止める
  if [ -n "$VTUBER_PID" ] && kill -0 "$VTUBER_PID" 2>/dev/null; then
    say "バックエンドを停止 (PID $VTUBER_PID)"; kill "$VTUBER_PID" 2>/dev/null
  fi
  if [ -n "$TTS_PID" ] && kill -0 "$TTS_PID" 2>/dev/null; then
    say "Irodori-TTS を停止 (PID $TTS_PID)"; kill "$TTS_PID" 2>/dev/null
  fi
  exit $code
}
trap cleanup EXIT INT TERM

status_line() {
  local url="$1" name="$2"
  if alive "$url"; then ok "$name"; else warn "$name — 停止中"; fi
}

if [ "$CHECK_ONLY" = 1 ]; then
  say "起動状況"
  status_line "$OLLAMA_URL/api/tags" "Ollama        ($OLLAMA_URL)"
  status_line "$TTS_URL/health"      "Irodori-TTS   ($TTS_URL)"
  status_line "$VTUBER_URL"          "Open-LLM-VTuber ($VTUBER_URL)"
  trap - EXIT; exit 0
fi

mkdir -p "$LOG_DIR"

# ── 1. Ollama（systemd。起動していなければ起こす）─────────────────────────
if alive "$OLLAMA_URL/api/tags"; then
  ok "Ollama は起動済み"
else
  say "Ollama を起動"
  sudo systemctl start ollama || die "Ollama を起動できなかった"
  wait_for "$OLLAMA_URL/api/tags" "Ollama" 30 || die "Ollama が応答しない"
  ok "Ollama"
fi

# ── 2. Irodori-TTS ────────────────────────────────────────────────────────
if alive "$TTS_URL/health"; then
  ok "Irodori-TTS は起動済み（このスクリプトでは止めない）"
else
  [ -d "$IRODORI_DIR" ] || die "$IRODORI_DIR が無い"
  say "Irodori-TTS を起動 → $LOG_DIR/irodori.log"
  ( cd "$IRODORI_DIR" && exec uv run --no-sync python -m irodori_openai_tts \
      --host 0.0.0.0 --port 8088 ) >"$LOG_DIR/irodori.log" 2>&1 &
  TTS_PID=$!
  wait_for "$TTS_URL/health" "Irodori-TTS" 180 \
    || die "Irodori-TTS が応答しない。$LOG_DIR/irodori.log を見て"
  ok "Irodori-TTS (PID $TTS_PID)"
fi

# 声のリファレンスが登録されているか
if ! curl -s --max-time 3 "$TTS_URL/health" | grep -q '"files": *[1-9]'; then
  warn "voices/ にリファレンス音声が無い。声が毎回変わる（ConversationalAI/voice/README.md 参照）"
fi

# ── 3. LLM の事前ロード（初回応答を速くする）──────────────────────────────
if [ "$DO_WARM" = 1 ]; then
  say "$LLM_MODEL をVRAMへ事前ロード"
  curl -s --max-time 180 "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$LLM_MODEL\",\"prompt\":\"\",\"keep_alive\":\"30m\"}" >/dev/null \
    && ok "$LLM_MODEL ロード済み" || warn "事前ロードに失敗（動作はする）"
fi

# ── 4. Open-LLM-VTuber バックエンド ───────────────────────────────────────
if alive "$VTUBER_URL"; then
  ok "バックエンドは起動済み（このスクリプトでは止めない）"
else
  [ -d "$VTUBER_DIR" ] || die "$VTUBER_DIR が無い"
  say "バックエンドを起動 → $LOG_DIR/vtuber.log"
  ( cd "$VTUBER_DIR" && exec uv run run_server.py ) >"$LOG_DIR/vtuber.log" 2>&1 &
  VTUBER_PID=$!
  wait_for "$VTUBER_URL" "バックエンド" 180 \
    || die "バックエンドが応答しない。$LOG_DIR/vtuber.log を見て"
  ok "バックエンド (PID $VTUBER_PID)"
fi

# ── 5. Electron（Desktop Pet Mode）───────────────────────────────────────
if [ "$DO_APP" = 0 ]; then
  echo
  ok "準備完了。ブラウザで $VTUBER_URL を開く"
  echo "   Setting → Character Preset → 佐倉みどり で切り替える"
  echo "   終了は Ctrl+C（このスクリプトが起動したサーバーも一緒に止まる）"
  # サーバーを自分で起動している場合だけ、ここで待つ
  if [ -n "$TTS_PID" ] || [ -n "$VTUBER_PID" ]; then wait; fi
  exit 0
fi

APP_BIN="$(ls -d "$WEB_DIR"/release/*/linux-unpacked/open-llm-vtuber 2>/dev/null | sort -V | tail -1)"
if [ -z "$APP_BIN" ]; then
  warn "Electron のバイナリが見つからない（$WEB_DIR/release/*/linux-unpacked/）"
  echo "   ブラウザで $VTUBER_URL を開いて使う。ビルド手順は Build Log #010 を参照"
  if [ -n "$TTS_PID" ] || [ -n "$VTUBER_PID" ]; then wait; fi
  exit 0
fi

echo
say "Electron を起動: $APP_BIN"
echo "   ペットモードは トレイアイコン → Pet Mode"
echo "   Setting → Character Preset → 佐倉みどり で切り替える"
echo
# env -u ELECTRON_RUN_AS_NODE は必須。VS Code のターミナルから起動すると
# ELECTRON_RUN_AS_NODE=1 を継承して GUI が出ない（Build Log #010）。
( cd "$(dirname "$APP_BIN")" && exec env -u ELECTRON_RUN_AS_NODE ./open-llm-vtuber )

# Electron を閉じたら trap cleanup が走り、自分で起動したサーバーを片付ける

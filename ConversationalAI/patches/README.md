# patches — Open-LLM-VTuber への改修

本家リポジトリに手を加えた内容のバックアップ。本家は `.gitignore` で設定類を
除外しており、改修もフォーク前でpush先が無いため、ここに diff として保管する。

**2026-10-01 にフォークし、ここの改修はすべてフォークにコミットした（Build Log #017 節14）。
今後の正はフォーク側。このディレクトリは履歴として残し、更新しない。**

| パッチ | フォークのコミット |
|---|---|
| `open-llm-vtuber-web-linux-pet-mode.patch` | [emboss369/Open-LLM-VTuber-Web `e70eb42`](https://github.com/emboss369/Open-LLM-VTuber-Web/commit/e70eb42) |
| `013-sentence-divider-emoji.patch` | [emboss369/Open-LLM-VTuber `3c5b6a9`](https://github.com/emboss369/Open-LLM-VTuber/commit/3c5b6a9) |
| `017-midori-agent.patch` | [emboss369/Open-LLM-VTuber `47b1cc9`](https://github.com/emboss369/Open-LLM-VTuber/commit/47b1cc9)（フォークでは `MidoriAgent` の import を遅延に変えている。パッチのままだと、シンボリックリンクの無い clone で全 Agent が import で落ちるため） |

パッチに入っていなかったもの：`mcp_servers.json` のタイムゾーン（`21a5d49`）、
フロントエンドの `package-lock.json` の version 合わせ（`da93692`）。

---

## open-llm-vtuber-web-linux-pet-mode.patch

Linux で Desktop Pet Mode のクリック透過・ホバー判定を機能させる改修。
詳細な調査過程は build-log/build-log-010.md を参照。

| | |
|---|---|
| 対象リポジトリ | https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web |
| ベースコミット | `d176e7df2366952e3bacbf12cf9a8b18a4315932`（2025-09-05） |
| ブランチ | `main` |
| 変更ファイル | `src/main/window-manager.ts`, `src/renderer/src/hooks/canvas/use-live2d-model.ts` |

### 解決している問題

1. `setIgnoreMouseEvents(ignore, { forward: true })` の `forward` は macOS /
   Windows 限定（electron/electron#16777、2019年から未解決）。Linux では
   マウス移動がレンダラーに届かず、「モデルの上だけ触れる」ホバー判定が
   一度も発火しないため、ペットモードのウィンドウが永久にクリック透過になる
2. 代替として `screen.getCursorScreenPoint()` を使うと、クリック透過中は
   Chromium が入力を受け取らないため値が凍結する（実測で確認）

### 解決方法

カーソル位置を X11 に直接問い合わせる。`XQueryPointer` を約33Hzでポーリング
して stdout にストリームする Python ヘルパーをメインプロセスから常駐起動し、
得た座標をレンダラーへ送って既存の `anyhitTest` / `isHitOnModel` に通す。
python3 や X が無い環境では従来の `getCursorScreenPoint()` 方式へ自動で
フォールバックする。

### 適用方法

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web
git apply ~/Develop/project-physical-ai/ConversationalAI/patches/open-llm-vtuber-web-linux-pet-mode.patch
```

すでに適用済みかの確認（適用済みなら成功する）:

```bash
git apply --check --reverse .../open-llm-vtuber-web-linux-pet-mode.patch
```

### デバッグ

メインプロセス側のトレースは環境変数で有効化する。

```bash
PET_DEBUG=1 ELECTRON_ENABLE_LOGGING=1 ./open-llm-vtuber
```

---

## 017-midori-agent.patch

自作 Agent `midori_agent` を本体に登録する改修（Build Log #017）。Agent 本体は
`ConversationalAI/agent/midori_agent.py`（Build Log 検索は同じ場所の `build_log_rag.py`）で、本体側からはシンボリックリンクで参照する。
このパッチは登録に必要な2箇所だけ。

| | |
|---|---|
| 対象リポジトリ | https://github.com/Open-LLM-VTuber/Open-LLM-VTuber |
| ベースコミット | `992309c0aa19845960228f880013d4685fde93b5` |
| 変更ファイル | `src/open_llm_vtuber/agent/agent_factory.py`, `src/open_llm_vtuber/config_manager/agent.py` |

- `config_manager/agent.py`：`conversation_agent_choice` は `Literal` で検証されるため、選択肢に `midori_agent` を足す
- `agent_factory.py`：`midori_agent` を `basic_memory_agent` と同じ分岐で作る。LLM・MCP の設定を共用するので、MCP ツールも使える

### 適用方法

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
git apply ~/Develop/project-physical-ai/ConversationalAI/patches/017-midori-agent.patch
for f in midori_agent.py build_log_rag.py; do
  ln -s ~/Develop/project-physical-ai/ConversationalAI/agent/$f src/open_llm_vtuber/agent/agents/$f
done
```

使うキャラクターの YAML に `agent_config.conversation_agent_choice: 'midori_agent'` を書く
（`sakura_midori.yaml` で設定済み）。

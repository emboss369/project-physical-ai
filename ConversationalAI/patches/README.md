# patches — Open-LLM-VTuber への改修

本家リポジトリに手を加えた内容のバックアップ。本家は `.gitignore` で設定類を
除外しており、改修もフォーク前でpush先が無いため、ここに diff として保管する。

フォークを作ったら（→ ConversationalAI/CLAUDE.md のバックログ）、
フォーク先で `git apply` してからコミットし、このディレクトリは役目を終える。

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
git apply /mnt/data/git/project-physical-ai/ConversationalAI/patches/open-llm-vtuber-web-linux-pet-mode.patch
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

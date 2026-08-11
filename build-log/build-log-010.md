# Build Log #010 — 2026-08-09〜08-10

## 今日やったこと

Build Log #007 で止まっていた Open-LLM-VTuber の続き。相棒AIキャラクターに人格を入れ、Live2Dモデルの利用条件を確認し、Desktop Pet Mode を Linux で動かした。

1. **佐倉みどりのペルソナ投入**：キャラクター設定を Open-LLM-VTuber の形式に整備し、リポジトリ側を正としてシンボリックリンクで配置
2. **Live2Dモデルのライセンス確認**：`mao_pro` は営利利用可（要著作権表記）、`shizuku` は使用不可と判定
3. **Desktop Pet Mode の Linux 対応**：公式が Linux バイナリを配布していないためソースビルドし、さらに**Electron の Linux 固有の制約2つ**に阻まれたのを、X11 への直接問い合わせで突破した

**今日の結論を一行で：Linux で「クリック透過するデスクトップペット」が作れないのは、`setIgnoreMouseEvents` の `forward` が非対応なだけでなく、`getCursorScreenPoint()` まで凍るという二重の理由からだった。**

---

### 1. キャラクター名の表記を確定させる

claude.ai 側で作った人格設定ファイル `ConversationalAI/sakura_midori.yaml` を投入するところから始めた。ファイルを開いたところ、**キャラクター名の読みが3箇所で割れていた**。

| 場所 | 表記 |
|---|---|
| 本文 | 「佐倉碧（さくら **あおい**）」 |
| 口癖 | 「いつか、**みどり**ちゃんに体を！」 |
| ファイル名 | `sakura_**midori**.yaml` |

「碧」は「あおい」とも「みどり」とも読める。音声で読み上げるキャラクターで読みが不定なのは致命的なので、**「みどり」としか読めない表記に変える**方針で候補を出した。

| 案 | 読みの曖昧さ | TTS（edge_tts）の誤読リスク |
|---|---|---|
| 佐倉 緑 | 人名では「みどり」一択 | 中。「さくらりょく」と音読みされうる |
| **佐倉 みどり** | **ゼロ** | **ほぼゼロ** |
| 佐倉 翠 | 「すい」とも読める | 中〜高 |
| 佐倉 美登里 | ゼロ（当て字） | 低 |

**「佐倉みどり」（ひらがな）を採用。** 漢字の見栄えより、TTS が確実に読めることを優先した。ConversationalAI/CLAUDE.md の TTS バックログに「固有名詞・英字混在で読み誤りリスク」と書いてあるとおり、読み誤りは後から SSML や置換辞書で潰す作業が発生する。最初から回避できるならその方が安い。

---

### 2. Open-LLM-VTuber のキャラクター設定形式を調べる

`characters/` に置くファイルの形式を確認した。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber
ls characters/
cat characters/README.md
cat characters/en_unhelpful_ai.yaml
```

```
README.md  en_nuke_debate.yaml  en_unhelpful_ai.yaml  zh_米粒.yaml  zh_翻译腔.yaml
```

README から分かったこと：

- `conf.yaml` がベース設定で、`characters/*.yaml` は**差分だけを上書きする**
- ルートは `character_config:` でラップする必要がある
- `conf_uid` は一意にすること（チャット履歴の識別に使われる）

手元の `sakura_midori.yaml` は `persona_prompt:` がトップレベルに書かれているだけで、**このままでは読み込まれない**。書き換えが必要と判明。

ベース側の現在の設定も確認した。

```bash
grep -n "character_config\|conf_uid\|conf_name\|live2d_model_name\|persona_prompt\|character_name" conf.yaml
grep -n -A8 "^      ollama_llm:" conf.yaml
grep -n -A5 "edge_tts:" conf.yaml
```

```
29:character_config:
30:  conf_name: 'mao_pro'
31:  conf_uid: 'mao_pro_001'
32:  live2d_model_name: 'mao_pro'
33:  character_name: 'Mao'
42:  persona_prompt: |

129:      ollama_llm:
130-        base_url: 'http://localhost:11434/v1'
131-        model: 'qwen2.5:latest'
132-        temperature: 0.9

292:    edge_tts:
295-      voice: 'ja-JP-NanamiNeural'
```

Build Log #007 で決めた最終構成（qwen2.5:latest / temperature 0.9 / ja-JP-NanamiNeural）がそのまま残っていることを確認。

---

### 3. 佐倉みどりの設定ファイルを書き換える

`ConversationalAI/sakura_midori.yaml` を `character_config:` 形式に書き換えた。人格部分は元の内容を保ちつつ、以下を反映した。

- 名前を「佐倉みどり（さくら みどり）」に統一
- **言語指定を最優先セクションとして追加**（Build Log #007 で qwen2.5 の中国語混入対策として有効性を確認済み）。ただし「SO-101」「LeRobot」等のプロジェクト固有名詞だけは英字のまま使う例外を明記
- **「箇条書き・見出し・太字などの記号は使わず、話し言葉で答える」を追加**。#007 で、番号付きリストや `**太字**` を含む応答に TTS が対応できず `Error preparing audio payload: Audio is empty or all zero.` を5回連続で出した実績があるため
- 「推測で数字をでっち上げない」を追加（#007 の「検索したフリをして捏造する」事例を踏まえて）
- `live2d_model_name: 'mao_pro'`、`tts_config.edge_tts.voice: 'ja-JP-NanamiNeural'` を明示

---

### 4. リポジトリを正とするシンボリックリンク配置

`characters/` に実ファイルを置くとリポジトリ管理から外れる。先にスキャン処理の実装を確認した。

```bash
grep -rn "config_alts_dir" --include=*.py src/
sed -n '127,185p' src/open_llm_vtuber/config_manager/utils.py
```

```python
    # Scan other configs
    for root, _, files in os.walk(config_alts_dir):
        for file in files:
            if file.endswith(".yaml"):
```

`os.walk` はシンボリックリンクされたファイルも `files` に含めるため、リンクで問題ないと判断した。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber
ln -sfn /mnt/data/git/project-physical-ai/ConversationalAI/sakura_midori.yaml characters/sakura_midori.yaml
ls -l characters/
```

```
lrwxrwxrwx 1 hiro hiro   69  8月  9 22:27 sakura_midori.yaml -> /mnt/data/git/project-physical-ai/ConversationalAI/sakura_midori.yaml
```

YAML として妥当か検証。

```bash
uv run python -c "
import yaml, sys
d = yaml.safe_load(open('characters/sakura_midori.yaml'))
cc = d['character_config']
print('conf_name      :', cc['conf_name'])
print('conf_uid       :', cc['conf_uid'])
print('character_name :', cc['character_name'])
print('live2d_model   :', cc['live2d_model_name'])
print('avatar         :', cc['avatar'])
print('tts voice      :', cc['tts_config']['edge_tts']['voice'])
print('persona chars  :', len(cc['persona_prompt']))
"
```

```
conf_name      : 佐倉みどり
conf_uid       : sakura_midori_001
character_name : 佐倉みどり
live2d_model   : mao_pro
avatar         : mao.png
tts voice      : ja-JP-NanamiNeural
persona chars  : 1689
```

アプリ側のスキャン関数を直接叩いて認識を確認。

```bash
uv run python -c "
import sys; sys.path.insert(0,'.')
from src.open_llm_vtuber.config_manager.utils import scan_config_alts_directory
for c in scan_config_alts_directory('characters'):
    print(f\"{c['name']:<20} <- {c['filename']}\")
"
```

```
mao_pro              <- conf.yaml
米粒                   <- zh_米粒.yaml
翻译腔-神经大人             <- zh_翻译腔.yaml
en_nuke_debator      <- en_nuke_debate.yaml
unhelpful_ai         <- en_unhelpful_ai.yaml
佐倉みどり                <- sakura_midori.yaml
```

**シンボリックリンク越しに正しく認識された。**

---

### 5. Live2Dモデルの利用条件を確認する

YouTube で使えるモデルを選ぶため、同梱モデルと `model_dict.json` の登録状況を確認した。

```bash
python3 -c "
import json
d=json.load(open('model_dict.json'))
for m in d: print(m.get('name'), '|', m.get('url'))
"
ls live2d-models/
ls avatars/
```

```
mao_pro | /live2d-models/mao_pro/runtime/mao_pro.model3.json

live2d-models: mao_pro  shizuku
avatars: mao.png  shizuku.png
```

`shizuku` はディレクトリだけあって `model_dict.json` に未登録。

次に `LICENSE-Live2D.md` を読んだ。要点は以下。

**Live2Dオリジナルキャラクター一覧**（該当部分）

> Izumi, Epsilon, Gantzert & Felixander, Kei, Koharu & Haruto, **Shizuku**, simple model, Chitose, Tororo & Hijiki, **Mao Niziiro**, Nito, Haru, ...

両方ともLive2Dオリジナルキャラクターに分類される。

**個別利用条件**

> **Shizuku** — Use this character directly without changing the name or settings.

Shizuku には「名前や設定を変えずに使うこと」という個別条件がある。**佐倉みどりとして使う時点でこれに反する**。一方 **Mao Niziiro には個別条件の記載が無い**。

**使用等目的**（Free Material License Agreement 2.1.3.1）

> 2.1.3.1 一般ユーザーおよび小規模事業者による使用の場合
> 使用等目的： 営利・非営利の目的を問わない

一般ユーザーの定義は「直近売上高が1,000万円未満の個人・学生・サークル・その他の団体」（1.22）。**YouTube の収益化があっても利用可**。

**著作権表記**（2.1.5）— 必須。YouTube 概要欄など長文が書ける場所には以下を記載する。

```
This content uses sample data owned and copyrighted by Live2D Inc.
The sample data are utilized in accordance with terms and conditions set by Live2D Inc.
This content itself is created at the author's sole discretion.
```

X など短文の場所は短縮版。

```
This content uses sample data owned and copyrighted by Live2D Inc.
```

**結論：`mao_pro` を採用、`shizuku` は使用不可。** `model_dict.json` に未登録なのは都合が良く、そのまま登録せずに放置する。

なお 4.1.2（体のバランスを著しく崩す改変の禁止）と 4.1.7（政治的・宗教的主張、暴力的・差別的な内容での使用の禁止）にも留意。本チャンネルの用途では該当しない。

これは法律判断ではなく条文の読み取り。将来アバターを自作すれば、この表記義務ごと外せる。

---

### 6. サーバー起動と動作確認

```bash
curl -s -m 5 http://localhost:11434/api/tags >/dev/null && echo "Ollama: 起動中" || echo "Ollama: 停止"
curl -s -m 3 http://localhost:12393 >/dev/null && echo "VTuber server: すでに起動中" || echo "VTuber server: 停止"
```

```
Ollama: 起動中
VTuber server: 停止
```

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run run_server.py
```

```
2026-08-09 22:28:25 | INFO | mcpp.mcp_client:_ensure_server_running_and_get_session:75 | MCPC: Successfully connected to server 'ddg-search'.
2026-08-09 22:28:25 | INFO | mcpp.tool_manager:__init__:28 | ToolManager initialized with 2 OpenAI tools and 2 Claude tools.
2026-08-09 22:28:25 | INFO | service_context:init_agent:366 | Initializing Agent: basic_memory_agent
2026-08-09 22:28:25 | INFO | agent.stateless_llm_factory:create_llm:23 | Initializing LLM: ollama_llm
2026-08-09 22:28:25 | INFO | openai_compatible_llm:__init__:56 | Initialized AsyncLLM with the parameters: http://localhost:11434/v1, qwen2.5:latest
2026-08-09 22:28:25 | INFO | ollama_llm:__init__:32 | Preloading model for Ollama
2026-08-09 22:28:28 | INFO | agents.basic_memory_agent:__init__:112 | BasicMemoryAgent initialized.
2026-08-09 22:28:28 | INFO | __main__:run:152 | Server context initialized successfully.
INFO:     Uvicorn running on http://localhost:12393 (Press CTRL+C to quit)
```

Build Log #007 で ImportError を出していた MCP サーバー `ddg-search` が、今回は起動時から正常接続している。

一方 `time` は**#007 と全く同じエラーのまま**、12日経っても直っていない。

```
2026-08-09 22:28:23 | INFO  | mcp_client:_ensure_server_running_and_get_session:50 | MCPC: Starting and connecting to server 'time'...
    from mcp.shared.exceptions import McpError
ImportError: cannot import name 'McpError' from 'mcp.shared.exceptions'
    (/home/hiro/.cache/uv/archive-v0/5pn-cnaK1FWHsq9l/lib/python3.12/site-packages/mcp/shared/exceptions.py).
    Did you mean: 'MCPError'?
2026-08-09 22:28:24 | ERROR | mcp_client:_ensure_server_running_and_get_session:78 | MCPC: Failed to connect to server 'time': Connection closed
```

Python の親切な提案（`Did you mean: 'MCPError'?`）が原因を明示している。**mcp ライブラリ側で `McpError` が `MCPError` にリネームされ、呼び出し側が追随していない**という単純な API 不一致。#007 では「一貫して import エラーで機能せず未解決」とだけ書いていたが、今回エラー全文を読んで原因が特定できた。現在時刻取得の機能なので実害は小さく、今回は深追いしない。

---

### 7. Desktop Pet Mode：まず Open-LLM-VTuber-Web の正体を確認する

「Open-LLM-VTuber-Web とは何か」から確認した。

```bash
cat .gitmodules
git submodule status
```

```
[submodule "frontend"]
	path = frontend
	url = https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web
	branch = build

 06a659b114fff788cf0daaa86e484576db4975bf frontend (06a659b)
```

```bash
ls frontend
```

```
assets  favicon.ico  index.html  libs
```

分かったこと：

- **Open-LLM-VTuber** = バックエンド（Python、ASR/LLM/TTS/WebSocket）
- **Open-LLM-VTuber-Web** = フロントエンド（React + Live2D描画）。`git clone --recursive` で `frontend/` として既に取得済みだった。Build Log #007 でブラウザから触っていた画面がまさにこれ
- ただし `frontend/` が指しているのは `branch = build`（**ビルド済み成果物だけのブランチ**）で、ソースコードは入っていない
- 同じソースから Web版（ブラウザ）と デスクトップ版（Electron）の2通りにビルドされる。**ペットモード（透過背景・最前面・クリック透過）は Electron 版でしか実現できない**（ブラウザには背景透過・クリック透過の手段がない）

---

### 8. リリース確認：Linux バイナリは存在しない

```bash
curl -s "https://api.github.com/repos/Open-LLM-VTuber/Open-LLM-VTuber-Web/releases?per_page=5" | python3 -c "
import json,sys
rs=json.load(sys.stdin)
for r in rs:
    print('===', r['tag_name'], r['name'], r['published_at'])
    for a in r['assets']:
        print('   ', a['name'], round(a['size']/1e6,1),'MB', 'DL:',a['download_count'])
"
```

```
=== v1.2.1 1.2.1 2025-08-21T12:36:24Z
    open-llm-vtuber-1.2.1-setup.exe 101.1 MB DL: 2766
    open-llm-vtuber-1.2.1.dmg 173.2 MB DL: 691
=== v1.2.0 v1.2.0 2025-08-03T05:46:25Z
    open-llm-vtuber-1.2.0-setup.exe 101.1 MB DL: 111
    open-llm-vtuber-1.2.0.dmg 173.2 MB DL: 58
=== v1.1.0 v1.1.0 2025-02-18T12:23:25Z
    latest-mac.yml 0.0 MB DL: 45
    latest.yml 0.0 MB DL: 86
    open-llm-vtuber-electron-1.1.0-arm64-mac.zip 158.4 MB DL: 164
    open-llm-vtuber-electron-1.1.0-setup.exe 127.1 MB DL: 1001
    open-llm-vtuber-electron-1.1.0.dmg 165.2 MB DL: 190
=== v1.0.0 v1.0.0 2025-01-28T04:55:37Z
    open-llm-vtuber-electron-1.0.0-setup.exe 123.5 MB DL: 201
    open-llm-vtuber-electron-1.0.0.dmg 160.0 MB DL: 45
```

**4リリース全て exe と dmg のみ。AppImage / deb / snap は一つも無い。**

ただしビルド設定には Linux ターゲットが存在するか確認した。

```bash
for f in package.json electron-builder.yml electron-builder.yaml electron-builder.json; do
  echo "=== $f ==="
  curl -sf "https://raw.githubusercontent.com/Open-LLM-VTuber/Open-LLM-VTuber-Web/main/$f" || echo "(not found)"
done
```

```json
"build:linux": "electron-vite build && electron-builder --linux",
```

```yaml
linux:
  target:
    - AppImage
    - snap
    - deb
  maintainer: electronjs.org
  category: Utility
...
electronDownload:
  mirror: https://npmmirror.com/mirrors/electron/
```

**Linux ビルドは設定上サポート済みで、公式が配布していないだけ**と判明。`electronDownload.mirror` が中国のミラーに固定されている点だけ注意（遅い場合は `ELECTRON_MIRROR` で上書き）。

環境も確認。

```bash
node -v; npm -v
apt-cache policy nodejs
lsb_release -d
df -h /home/hiro | tail -1
```

```
/bin/bash: 行 1: node: コマンドが見つかりません
nodejs: インストールされているバージョン: (なし)
        候補:               18.19.1+dfsg-6ubuntu5
Description:	Ubuntu 24.04.4 LTS
/dev/nvme0n1p5  468G   71G  374G  16% /
```

Node.js 未インストール。apt の候補は 18.19 で、Electron 31 / Vite 5 のビルドには古い可能性があるため、**sudo 不要で新しいバージョンを入れられる nvm** を選んだ。

---

### 9. Electron 版のソースビルド

ビルド手順をスクリプトにまとめた（`/tmp/.../build-electron.sh`）。

```bash
#!/usr/bin/env bash
set -euo pipefail

LAB=/home/hiro/development/open-llm-vtuber-lab
WEB=$LAB/Open-LLM-VTuber-Web
export NVM_DIR="$HOME/.nvm"

echo "=========== [1/5] nvm ==========="
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
. "$NVM_DIR/nvm.sh"

echo "=========== [2/5] Node.js 20 LTS ==========="
nvm install 20
nvm use 20
node -v
npm -v

echo "=========== [3/5] clone Open-LLM-VTuber-Web (main) ==========="
if [ -d "$WEB/.git" ]; then
  git -C "$WEB" fetch --all --prune
  git -C "$WEB" checkout main
  git -C "$WEB" pull --ff-only
else
  git clone --branch main https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web.git "$WEB"
fi
cd "$WEB"
git log --oneline -1

echo "=========== [4/5] npm install ==========="
npm install

echo "=========== [5/5] electron-builder --linux ==========="
npm run build:linux

echo "=========== 成果物 ==========="
find "$WEB/release" -maxdepth 3 -type f \( -name '*.AppImage' -o -name '*.deb' -o -name '*.snap' \) -exec ls -lh {} \;
echo "DONE"
```

```bash
chmod +x build-electron.sh
bash build-electron.sh 2>&1 | tee electron-build.log
```

実行ログ抜粋：

```
=========== [1/5] nvm ===========
=> Downloading nvm from git to '/home/hiro/.nvm'
=> Cloning into '/home/hiro/.nvm'...
=> Appending nvm source string to /home/hiro/.bashrc

=========== [2/5] Node.js 20 LTS ===========
Downloading and installing node v20.20.2...
Downloading https://nodejs.org/dist/v20.20.2/node-v20.20.2-linux-x64.tar.xz...
Computing checksum with sha256sum
Checksums matched!
Now using node v20.20.2 (npm v10.8.2)

=========== [3/5] clone Open-LLM-VTuber-Web (main) ===========
Cloning into '/home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web'...
d176e7d Merge branch 'main' of https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web

=========== [4/5] npm install ===========
added 812 packages, and audited 813 packages in 14s

=========== [5/5] electron-builder --linux ===========
✓ 2047 modules transformed.
../../out/renderer/assets/index-DJNjLrpm.js   2,972.43 kB
✓ built in 2.70s
  • electron-builder  version=24.13.3 os=7.0.0-28-generic
  • packaging       platform=linux arch=x64 electron=31.7.7 appOutDir=release/1.2.1/linux-unpacked
  • downloading     url=https://npmmirror.com/mirrors/electron/31.7.7/electron-v31.7.7-linux-x64.zip size=106 MB parts=8
  • downloaded      url=https://npmmirror.com/mirrors/electron/31.7.7/electron-v31.7.7-linux-x64.zip duration=9.726s
  • building        target=AppImage arch=x64 file=release/1.2.1/open-llm-vtuber-1.2.1.AppImage
  • building        target=snap arch=x64 file=release/1.2.1/open-llm-vtuber_1.2.1_amd64.snap
  • building        target=deb arch=x64 file=release/1.2.1/open-llm-vtuber_1.2.1_amd64.deb

=========== 成果物 ===========
-rwxr-xr-x 1 hiro hiro 178M  8月  9 22:30 .../release/1.2.1/open-llm-vtuber-1.2.1.AppImage
-rw-r--r-- 1 hiro hiro 152M  8月  9 22:30 .../release/1.2.1/open-llm-vtuber_1.2.1_amd64.snap
-rw-rw-r-- 1 hiro hiro 101M  8月  9 22:31 .../release/1.2.1/open-llm-vtuber_1.2.1_amd64.deb
DONE
```

**約3分でビルド完了。** npmmirror が心配だったが 106MB を9.7秒で取得できた。

---

### 10. 起動できない①：`ELECTRON_RUN_AS_NODE`

環境を確認。

```bash
echo "DISPLAY=${DISPLAY:-(未設定)}"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-(未設定)}"
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-(未設定)}"
dpkg -l libfuse2 libfuse2t64 2>/dev/null | grep ^ii || echo "libfuse2: 未インストール"
```

```
DISPLAY=:1
WAYLAND_DISPLAY=(未設定)
XDG_SESSION_TYPE=x11
libfuse2: 未インストール
```

X11 セッション。**AppImage は libfuse2 が無いため直接起動できない**ので、展開済みバイナリを直接叩く方針にした。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web/release/1.2.1/linux-unpacked
ls -l | grep -v '\.pak\|\.so\|\.bin\|\.dat\|\.json\|\.html\|\.txt'
```

```
-rwxr-xr-x 1 hiro hiro     54192  8月  9 22:30 chrome-sandbox
-rwxr-xr-x 1 hiro hiro   1251088  8月  9 22:30 chrome_crashpad_handler
drwxrwxr-x 2 hiro hiro      4096  8月  9 22:30 locales
-rwxr-xr-x 1 hiro hiro 181922488  8月  9 22:30 open-llm-vtuber
drwxrwxr-x 3 hiro hiro      4096  8月  9 22:30 resources
```

起動してみると、**何も出力せず即終了**した。

```bash
timeout 20 ./open-llm-vtuber 2>&1 | head -40; echo "EXIT=${PIPESTATUS[0]}"
```

```
EXIT=0
```

引数を付けると別のエラーになった。

```bash
ELECTRON_ENABLE_LOGGING=1 ./open-llm-vtuber --no-sandbox; echo "EXIT=$?"
file ./open-llm-vtuber
ldd ./open-llm-vtuber 2>&1 | grep -i "not found" || echo "共有ライブラリ欠損なし"
```

```
./open-llm-vtuber: bad option: --no-sandbox
EXIT=9
./open-llm-vtuber: ELF 64-bit LSB pie executable, x86-64, ...
共有ライブラリ欠損なし
```

`--no-sandbox` は Electron が受け付けるはずのオプション。そして `bad option:` というメッセージ形式と **exit code 9** は、Electron ではなく **Node.js** のもの（Node の「Invalid Argument」は 9）。引数なしで exit 0 だったのも、Node が REPL を起動しようとして stdin が `/dev/null` だったため即終了した挙動と一致する。

Electron バイナリは `ELECTRON_RUN_AS_NODE` が立っていると素の Node.js として動く。環境を確認した。

```bash
env | grep -i "ELECTRON\|VSCODE" | head
```

```
XDG_CONFIG_DIRS_VSCODE_SNAP_ORIG=/etc/xdg/xdg-ubuntu:/etc/xdg
ELECTRON_RUN_AS_NODE=1
VSCODE_ESM_ENTRYPOINT=vs/workbench/api/node/extensionHostProcess
VSCODE_PID=4682
VSCODE_CWD=/home/hiro
```

**犯人は VS Code。** 拡張ホストが自分の Node プロセス用に立てている `ELECTRON_RUN_AS_NODE=1` を、そこから起動したシェルが継承していた。アプリの不具合でも設定ミスでもない。

```bash
nohup env -u ELECTRON_RUN_AS_NODE ./open-llm-vtuber > electron-run.log 2>&1 &
xwininfo -root -tree | grep -i "vtuber"
```

```
     0x3800004 "Open-LLM-Vtuber": ("open-llm-vtuber" "open-llm-vtuber")  900x670+282+169
     0x3a00003 "open-llm-vtuber": ("open-llm-vtuber" "Open-llm-vtuber")  200x200+0+0
     0x3a00001 "open-llm-vtuber": ("open-llm-vtuber" "Open-llm-vtuber")  10x10+10+10
```

**ウィンドウが出た。** バックエンドのログにもモデル取得が記録された。

```
INFO: 127.0.0.1:50762 - "GET /live2d-models/mao_pro/runtime/motions/special_01.motion3.json HTTP/1.1" 200 OK
INFO: 127.0.0.1:50752 - "GET /live2d-models/mao_pro/runtime/mao_pro.4096/texture_00.png HTTP/1.1" 200 OK
```

---

### 11. ペットモードへの切り替え方

切り替え手段をソースで確認した。

```bash
grep -rn "pet" --include=*.ts --include=*.tsx src/main/ src/renderer/src/context | grep -i "mode\|toggle\|window"
sed -n '30,80p' src/main/menu-manager.ts
sed -n '118,175p' src/main/menu-manager.ts
```

トレイメニューと、モデル上の右クリック文脈メニューの両方に `Window Mode` / `Pet Mode` のラジオ項目がある。ペットモードのときだけ以下が追加される。

| メニュー | 効果 |
|---|---|
| Toggle Mouse Passthrough | クリック透過のオン/オフ |
| Toggle InputBox and Subtitle | 入力欄と字幕の表示/非表示 |
| **Switch Character** | キャラクター切り替え（**トレイメニューには無い**） |
| Toggle Scrolling to Resize | ホイールでサイズ変更 |

実機では**トレイアイコン（Ubuntu 上部バー）のメニューから Pet Mode を選ぶ**方法で切り替わり、透過背景でデスクトップ上に立った。一方、Window Mode でモデルを右クリックしても何も出なかった。理由はコードにあった。

```tsx
// src/renderer/src/components/canvas/live2d.tsx:84
const handleContextMenu = (e: React.MouseEvent) => {
  if (!isPet) {
    return;
  }
```

**右クリックメニューはペットモード専用。** 順序としては「トレイ → Pet Mode → それから右クリック」が正しい。

---

### 12. クリックできない②：Linux では `forward` が効かない

ペットモードにしたものの、**モデルをクリックできない**。`Toggle Mouse Passthrough` を押しても変わらない。

該当箇所を読んだ。

```bash
sed -n '139,260p' src/main/window-manager.ts
sed -n '275,340p' src/main/window-manager.ts
sed -n '295,340p' src/renderer/src/hooks/canvas/use-live2d-model.ts
```

ペットモード進入時（`continueSetWindowModePet`）:

```ts
this.window.setFocusable(false);
if (isMac) {
  this.window.setIgnoreMouseEvents(true);
} else {
  this.window.setIgnoreMouseEvents(true, { forward: true });
}
```

ホバー判定（`updateComponentHover`）:

```ts
const shouldIgnore = this.hoveringComponents.size === 0;
this.window.setIgnoreMouseEvents(shouldIgnore, { forward: true });
```

レンダラー側（`use-live2d-model.ts:314-332`）— **`handleMouseMove` の中**でモデルの当たり判定をして `update-component-hover` を送る設計:

```ts
const currentHitState = model.anyhitTest(modelX, modelY) !== null || model.isHitOnModel(modelX, modelY);
if (currentHitState !== isHoveringModelRef.current) {
  isHoveringModelRef.current = currentHitState;
  electronApi.ipcRenderer.send('update-component-hover', 'live2d-model', currentHitState);
}
```

つまり「クリック透過中でもマウス移動だけは届く」ことが大前提の設計。その前提を作るのが `forward: true` だが、Electron 公式ドキュメントには：

> **`options.forward`** _macOS_ _Windows_
> If true, forwards mouse move messages to Chromium, enabling mouse related events such as `mouseleave`.

**Linux は対象外。** 上流の状況も確認した。

```bash
for r in "electron/electron/issues/16777" "Open-LLM-VTuber/Open-LLM-VTuber/issues/132"; do
  curl -s "https://api.github.com/repos/${r%%/issues*}/issues/${r##*/}" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('===', d['title'])
print('state:', d['state'], '| created:', d['created_at'][:10], '| updated:', d['updated_at'][:10], '| comments:', d['comments'])
"
done
```

```
=== Support the forward option of BrowserWindow.setIgnoreMouseEvents in Linux
state: open | created: 2019-02-06 | updated: 2026-04-02 | comments: 5
=== Add desktop pet mode compatibility for multiple monitors and Linux.
state: closed | created: 2025-02-17 | updated: 2025-11-28 | comments: 0
```

**electron/electron#16777 は2019年2月から7年間 open のまま。** 公式が Linux バイナリを配布していない理由はおそらくこれ。

また、`Toggle Mouse Passthrough` を押しても戻らない理由もコードで確認できた。透過を解除しても `shouldIgnore = this.hoveringComponents.size === 0` にフォールバックし、Linux ではホバーが一度も立たないためこれが常に `true` になる。**復帰手段はトレイ → Window Mode のみ**（こちらは `setIgnoreMouseEvents(false)` を直接呼ぶ）。

---

### 13. 対策1回目：メインプロセスからのカーソルポーリング → 失敗

メインプロセスなら、ウィンドウのクリック透過状態に関係なくカーソル位置を取れるはずだと考え、`screen.getCursorScreenPoint()` を50ms間隔でポーリングしてレンダラーに送る実装を入れた。

デバッグログを仕込んで測定した。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web/release/1.2.1/linux-unpacked
nohup env -u ELECTRON_RUN_AS_NODE PET_DEBUG=1 ELECTRON_ENABLE_LOGGING=1 ./open-llm-vtuber > electron-run.log 2>&1 &
```

結果を集計。

```bash
grep -A2 "^\[pet\] probe {" electron-run.log | grep "cursor:" | sed 's/.*cursor: //' | sort -u
grep -c '"hovering":true' electron-run.log
grep -c "updateComponentHover" electron-run.log
```

```
{ x: 1659, y: 99 },
(ユニーク座標数: 48)

0
0
```

**マウスを動かしたのに、48サンプル全て同じ座標。** レンダラー側のログを見ると、パイプライン自体は健全だった。

```
[pet-probe] {"point":{"x":1659,"y":67},"element":"canvas","insideWrapper":true,
 "canvas":{"w":1919,"h":1079,"cw":1919,"rect":{"x":0,"y":0,"width":1919,"height":1079,...}},
 "hasModel":true,"hasView":true,"hovering":false}
```

モデルもビューも取得できていて、座標さえ正しければ判定は動く状態。**問題はカーソル座標だけ**と絞り込めた。

---

### 14. X11 に直接聞いて確定させる

`getCursorScreenPoint()` が本当に嘘をついているのか、独立した情報源で検証した。`xdotool` は未インストールだったので、`ctypes` から `libX11` の `XQueryPointer` を直接叩くスクリプトを書いた。

```bash
xinput --list --short
```

```
⎡ Virtual core pointer                    	id=2	[master pointer  (3)]
⎜   ↳ Logitech M325                           	id=6	[slave  pointer  (2)]
```

```python
# xpointer.py
import ctypes, sys, time
X = ctypes.CDLL("libX11.so.6")
X.XOpenDisplay.restype = ctypes.c_void_p
d = X.XOpenDisplay(None)
if not d:
    print("XOpenDisplay failed"); sys.exit(1)
X.XDefaultRootWindow.restype = ctypes.c_ulong
X.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
root = X.XDefaultRootWindow(d)
rr = ctypes.c_ulong(); cr = ctypes.c_ulong()
rx = ctypes.c_int(); ry = ctypes.c_int(); wx = ctypes.c_int(); wy = ctypes.c_int()
mask = ctypes.c_uint()
X.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
    ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_uint)]
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 0
seen = []
end = time.time() + dur
while True:
    X.XQueryPointer(d, root, rr, cr, rx, ry, wx, wy, mask)
    p = (rx.value, ry.value)
    if not seen or seen[-1] != p:
        seen.append(p)
    if time.time() >= end:
        break
    time.sleep(0.05)
print("サンプル数(変化点):", len(seen))
print("最初:", seen[0], " 最後:", seen[-1])
print("ユニーク座標数:", len(set(seen)))
```

```bash
python3 xpointer.py 0
```

```
サンプル数(変化点): 1
最初: (1238, 659)  最後: (1238, 659)
ユニーク座標数: 1
```

| 情報源 | 同時刻のカーソル座標 |
|---|---|
| X11（`XQueryPointer`） | **(1238, 659)** ← 実際の位置 |
| Electron `getCursorScreenPoint()` | **(1659, 99)** ← 凍結 |

**`screen.getCursorScreenPoint()` も死んでいた。** クリック透過中は Chromium が入力イベントを一切受け取らないため、内部キャッシュが更新されない。`forward` が効かないのと同じ根が、カーソル取得APIにまで及んでいた。

**これが「Linux でデスクトップペットが作れない」ことの二重の理由。** 1つ目だけなら「メインプロセスでポーリングすればいい」で回避できるが、2つ目があるためその回避策も塞がれている。

---

### 15. 対策2回目：X11 直問い合わせで解決

カーソルの取得元を Electron から X サーバーに差し替えた。`XQueryPointer` を約33Hzでポーリングして stdout にストリームする Python ヘルパーを、メインプロセスから常駐起動する方式。

変更は2ファイル、206行の追加。

**`src/main/window-manager.ts`**
- ペットモード進入時に X11 ヘルパー（`python3 -c '<inline script>'`）を spawn。`asar` パッケージングの影響を避けるため、スクリプトは外部ファイルにせずインラインの文字列として持つ
- stdout を行単位で読み、**最新の1行だけ**を採用（古いサンプルは既に陳腐化しているため）
- 座標をスケールファクタで割って DIP に変換し、`getContentBounds()`（`getBounds()` ではない。GNOME がウィンドウを上部バーの下に押し下げるため、実測で `y: 32` のズレがあった）を引いてビューポート相対座標にしてから送信
- `python3` が無い等で spawn に失敗したら、従来の `getCursorScreenPoint()` 方式へ自動フォールバック
- Window Mode 復帰時・ウィンドウ破棄時にヘルパーを kill

**`src/renderer/src/hooks/canvas/use-live2d-model.ts`**
- `pet-cursor-probe` を購読し、受け取った座標を `document.elementFromPoint` で判定。Live2Dキャンバスの外（入力欄・字幕、zIndex 1000）ならホバー扱い
- キャンバス上なら既存の `anyhitTest` / `isHitOnModel` に通し、**モデルの絵がある画素の上にいるときだけ**ホバー扱い
- 既存の `handleMouseMove` 経路と同じ `isHoveringModelRef` を共有し、状態が変わったときだけ送信（二重発火を防ぐ）
- ドラッグ中はスキップ（ドラッグを中断させないため）
- 解除は `removeListener` ではなく `removeAllListeners`。コールバックが contextBridge を跨いでプロキシされるため、`removeListener` の同一性判定が外れることがある

ビルドと型チェック。

```bash
pkill -f "linux-unpacked/open-llm-vtube[r]"
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use 20
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web
npm run typecheck:node
npm run typecheck 2>&1 | grep -E "window-manager|use-live2d-model" || echo "なし（既存エラーは上流由来）"
npm run build:linux
```

```
> tsc --noEmit -p tsconfig.node.json --composite false
（エラーなし）

なし（既存エラーは上流由来）

  • building        target=AppImage arch=x64 file=release/1.2.1/open-llm-vtuber-1.2.1.AppImage
  • building        target=snap arch=x64 file=release/1.2.1/open-llm-vtuber_1.2.1_amd64.snap
  • building        target=deb arch=x64 file=release/1.2.1/open-llm-vtuber_1.2.1_amd64.deb
```

`npm run typecheck` 全体では上流の WebSDK 等に既存エラーが多数出るが、今回触った2ファイルには出ていない。

```bash
cd release/1.2.1/linux-unpacked
env -u ELECTRON_RUN_AS_NODE ./open-llm-vtuber
```

**トレイ → Pet Mode → モデルの上でクリック → 成功。** モデルの絵がある部分だけ触れて、それ以外は下のデスクトップに抜ける。Windows と同じ挙動を Linux で再現できた。

なお、`pkill -f "linux-unpacked/open-llm-vtuber"` は**自分自身のシェルまで巻き込んで落とす**（`pkill -f` は実行中のコマンドライン全体にマッチするため、そのパターンを含む自分のコマンドにもヒットする）。1文字を文字クラスにして `open-llm-vtube[r]` と書くことで回避した。

---

### 16. Git 状況の確認とバックアップ

改修がどこにも保存されていないことに気づき、状況を確認した。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web
git status --short
git branch --show-current
git log --oneline -1
git remote -v
git diff --stat src/main/window-manager.ts src/renderer/src/hooks/canvas/use-live2d-model.ts
```

```
 M package-lock.json
 M src/main/window-manager.ts
 M src/renderer/src/hooks/canvas/use-live2d-model.ts
main
d176e7d Merge branch 'main' of https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web
origin	https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web.git (fetch)
origin	https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web.git (push)

 src/main/window-manager.ts                        | 155 ++++++++++++++++++++++
 src/renderer/src/hooks/canvas/use-live2d-model.ts |  51 +++++++
 2 files changed, 206 insertions(+)
```

**origin は本家で、push 先が無い。コミットもしていない。** つまりこの改修はローカルの作業ツリーにしか存在せず、`git checkout .` 一発で消える状態だった。

バックエンド側も確認。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber
git check-ignore -v conf.yaml characters/sakura_midori.yaml
```

```
.gitignore:2:conf.yaml	conf.yaml
.gitignore:14:/characters/*	characters/sakura_midori.yaml
```

**`conf.yaml` も `characters/` も本家の .gitignore で除外されている。** 設定類は本家では元から管理対象外で、佐倉みどりの定義を `ConversationalAI/` に置いてシンボリックリンクで貼った設計が結果的に正解だったと確認できた。

パッチとして退避した。

```bash
mkdir -p /mnt/data/git/project-physical-ai/ConversationalAI/patches
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web
git diff -- src/main/window-manager.ts src/renderer/src/hooks/canvas/use-live2d-model.ts \
  > /mnt/data/git/project-physical-ai/ConversationalAI/patches/open-llm-vtuber-web-linux-pet-mode.patch
wc -l /mnt/data/git/project-physical-ai/ConversationalAI/patches/open-llm-vtuber-web-linux-pet-mode.patch
git log --format="%H %ci %s" -1
git apply --check --reverse /mnt/data/git/project-physical-ai/ConversationalAI/patches/open-llm-vtuber-web-linux-pet-mode.patch && echo "OK: パッチは現在のツリーと整合"
```

```
273 .../ConversationalAI/patches/open-llm-vtuber-web-linux-pet-mode.patch
d176e7df2366952e3bacbf12cf9a8b18a4315932 2025-09-05 21:00:45 +0800 Merge branch 'main' of ...
OK: パッチは現在のツリーと整合
```

`package-lock.json` は `npm install` の副産物なので除外した。適用先のベースコミットと適用手順を `patches/README.md` に併記した。

---

## 結果（成功／失敗／保留）

- **成功**：佐倉みどりのペルソナを Open-LLM-VTuber に投入し、キャラクター一覧に認識させた
- **成功**：Live2D の利用条件を確認し、`mao_pro` 採用・`shizuku` 不可を根拠付きで判定した
- **成功**：Linux 向け Electron 版をソースビルドし、Desktop Pet Mode を動作させた。Linux 固有の制約2つを実測で特定し、X11 直問い合わせで回避した
- **成功**：改修をパッチとしてリポジトリに退避した
- **成功（一部確認）**：佐倉みどりを起動時デフォルトにして実際に会話し、関西弁の応答文になることを確認した。会話品質の細部（関西弁の濃さ、「ドクター」→「師匠」の切り替わり、日本語純度）は継続確認が必要
- **保留**：Ollama の `num_ctx` がデフォルト2048で、persona_prompt（約1,700文字）が切り捨てられている可能性。未検証
- **保留**：フォーク作成と上流への PR

## 失敗の原因・学んだこと

- **エラーメッセージの「文体」が犯人を教えてくれることがある。** `bad option:` + exit code 9 という組み合わせは Node.js のもので、Electron のものではなかった。ここから `ELECTRON_RUN_AS_NODE` に辿り着けた。「そのプログラムが出すはずのないエラー」は、実は別のプログラムが動いている合図
- **開発環境が環境変数を汚染する。** VS Code の拡張ホストから起動したシェルは `ELECTRON_RUN_AS_NODE=1` を継承する。Electron アプリを開発するときに Electron ベースのエディタから起動するという、気づきにくい組み合わせだった
- **「動くはずの設計が動かない」ときは、前提となる API のプラットフォーム対応を疑う。** 今回の `forward` は公式ドキュメントに _macOS_ _Windows_ と明記されていた。コードだけ読んでも分からず、ドキュメントに当たって初めて分かった
- **回避策の前提も検証する。** 「メインプロセスならカーソルが取れるはず」は思い込みだった。実測して初めて `getCursorScreenPoint()` も凍っていると分かった。Build Log #009 で「timestamp が合成値だった」のと同じ構造で、**確かめずに使った API が嘘をついていた**
- **独立した情報源で裏を取る。** Electron の値だけ見ていても「凍っている」とは判断できない。X11 に直接聞いて (1238,659) vs (1659,99) という食い違いを出したことで確定した
- **測定の前に「測定できる状態か」を確認する。** 1回目の計測はカーソルが92サンプル全て同一座標で、そもそも判定が走る機会が無かった。マウスを動かしていない状態のログをいくら眺めても何も分からない
- **`pkill -f` は自分自身を殺す。** パターンが自分のコマンドラインにもマッチする。`open-llm-vtube[r]` のように文字クラスで1文字を包むのが定石
- **本家リポジトリをそのまま編集すると、成果が宙に浮く。** origin が本家だと push 先が無く、コミットしても手元にしか残らない。手を入れると決めた時点でフォークすべきだった
- 上流の未解決 issue（7年 open）に当たったときは、「自分の使い方が悪い」のではなく「そこは未対応の領域だ」と切り替える判断が要る。今回は公式が Linux バイナリを配布していないという事実が傍証になった

## 次やること（一歩だけ）

- **佐倉みどりと複数ターン会話して人格を確認する。** すでにデフォルト起動と関西弁の応答文は確認済み。見るのは関西弁の濃さ・脱線の頻度・「ドクター」→「師匠」の切り替わり・日本語純度。TTSが標準語イントネーションになる点は、別の音声モデル／サービスを調査するか判断する

## メモ（動画ネタ・気づき）

- **「Electron アプリが GUI を出さずに黙って終了する」→ 犯人は VS Code の環境変数**、という顛末は短い動画ネタになる。エラーメッセージの文体から犯人を特定する過程が見せ場
- **「Linux でデスクトップペットが作れない二重の理由」** は、Failure Log ではなく本編向けの題材になりそう。7年 open の Electron issue に突き当たり、回避策の前提まで崩れ、最終的に X サーバーへ直接聞いて解決するという流れは、そのまま起承転結になっている
- 「碧」が「あおい」とも「みどり」とも読める問題を、**TTS の誤読リスクを理由にひらがなで解決した**判断は、音声を扱うプロジェクトならではの小ネタ。見栄えより読み上げの確実性を取った
- Live2D のライセンスで **Shizuku だけ「名前や設定を変えるな」という個別条件がある**のは面白い発見。無料素材でもキャラクターごとに条件が違う
- Build Log #009 の「timestamp は合成値だった」と、今回の「getCursorScreenPoint は凍っていた」は同じ教訓の別バージョン。**API が返す値を確かめずに信じると、検証そのものが無意味になる**という点で対になっている

---

## 追記 — 2026-08-10：佐倉みどりを起動時のデフォルトにする

Desktop Pet Mode で毎回 `Switch Character` を操作しなくてもよいように、Open-LLM-VTuber の起動時デフォルトを佐倉みどりへ変更した。

調査の結果、`characters/sakura_midori.yaml` は切替候補として読み込まれる差分設定であり、起動時に自動適用されるものではなかった。バックエンドは起動時に `conf.yaml` を直接読み込み、その `character_config` を接続時にフロントエンドへ送る。そのため、デフォルトを決めるのは `conf.yaml` 側だった。

```bash
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run run_server.py
```

上記で起動するバックエンドには、`--character` のようなキャラクター選択用の起動引数は無い。`conf.yaml` の `character_config` に `ConversationalAI/sakura_midori.yaml` の差分を反映した。

- `conf_name`: `佐倉みどり`
- `conf_uid`: `sakura_midori_001`
- `character_name`: `佐倉みどり`
- `live2d_model_name`: `mao_pro`
- `avatar`: `mao.png`
- `persona_prompt` と `tts_config.edge_tts.voice` も佐倉みどり用の値へ更新

変更前の設定は `Open-LLM-VTuber/conf.yaml.before-sakura-default` に退避した。更新後にYAMLとしての読み込みとアプリの設定検証を行い、どちらも成功した。

起動手順は以下で確定。

```bash
# ターミナル1：バックエンド
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run run_server.py

# ターミナル2：Desktop Pet Mode
cd /home/hiro/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web/release/linux-unpacked
env -u ELECTRON_RUN_AS_NODE ./open-llm-vtuber
```

バックエンドは実行中のターミナルで `Ctrl+C` を押すと停止できる。

**実機確認**：起動直後から佐倉みどりが選択され、応答文も関西弁になっていることを確認した。一方、設定している `ja-JP-NanamiNeural` の音声は標準的な日本語音声で、関西弁のイントネーションにはならない。テキスト上の人格・語尾は反映済みで、方言らしい発音を得るには関西弁対応の音声モデルまたはTTSサービスを別途検討する必要がある。

注意：`conf.yaml` 自体も佐倉みどり、`characters/sakura_midori.yaml` も佐倉みどりを指すため、設定メニューには同名の候補が重複表示される可能性がある。

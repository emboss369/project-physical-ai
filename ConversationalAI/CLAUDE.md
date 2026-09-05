# ConversationalAI — 相棒AI「佐倉みどり」

Open-LLM-VTuber をベースにした、Project Physical AI の相棒AIキャラクター。

## このディレクトリの中身

| ファイル | 役割 |
|---|---|
| `sakura_midori.yaml` | 佐倉みどりのキャラクター設定。**ここが正**で、Open-LLM-VTuber 側の `characters/sakura_midori.yaml` はここへのシンボリックリンク |
| `sakura_midori.v1-full.yaml` | 長文版ペルソナ（1,683字／1,246トークン）の退避。Build Log #012 で短縮版（348字／260トークン）に差し替えた際のバックアップ。現行は絵文字ルール等を足して777字。人格が薄いと感じたらここから1行ずつ戻す |
| `voice/` | 佐倉みどりのリファレンス音声（Irodori-TTS のクローン元）。**ここが正**で、Irodori-TTS-Server 側の `voices/sakura_midori.wav` はここへのシンボリックリンク。出どころは `voice/README.md` |
| `patches/` | 本家 Open-LLM-VTuber に加えた改修の diff バックアップ |
| `start-midori.sh` | 起動スクリプト。TTS → LLM 事前ロード → バックエンド → Electron を一発で立ち上げる（`--check` / `--no-app` / `--no-warm`） |

`sakura_midori.yaml` を編集したら、**必ずパースを通してから起動する**（Build Log #012 で
インデント破損に気づかず起動して落ちた）。

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run python -c "import yaml; yaml.safe_load(open('characters/sakura_midori.yaml'))"
```

本家リポジトリは `conf.yaml` と `characters/*` を `.gitignore` で除外しているため、
設定をあちらに置くとどこにも残らない。必ずこちら側を正にする。

## 現在の構成（Build Log #013 時点）

| 要素 | 設定 |
|---|---|
| LLM | Ollama `qwen3-vl-8k` / temperature 0.9（Build Log #013。`qwen3-vl:8b-instruct` ベース、vision 対応・thinking 無し・`num_ctx 8192`） |
| TTS | **Irodori-TTS**（`Aratako/Irodori-TTS-v4-Small`）を OpenAI 互換サーバー経由（`localhost:8088`）。voice は `sakura_midori`（Build Log #013） |
| ASR | sherpa-onnx（SenseVoiceSmall、CPU推論） |
| Live2Dモデル | `mao_pro`（Live2D 公式サンプルキャラクター「虹色まお」のモデルデータ。後述） |
| 実行形態 | Electron 版をソースビルド（Linux バイナリは公式配布なし） |

### `mao_pro` とは何か

**`mao_pro` はキャラクター名ではなく、モデルデータの識別子。** Live2D 公式が学習・
テスト用に無料配布しているサンプルモデル「**虹色まお**」の、組み込み用データの
ファイル名・フォルダ名（`mao_pro.moc3` / `mao_pro.model3.json` など）を指す。

- 配布元：[Live2D サンプルモデル](https://www.live2d.com/learn/sample/)
- 公式サンプルで利用条件が緩いため、**Open-LLM-VTuber や AITuberKit といった
  AIアバター系のOSSで、動作テスト用の既定 Live2D キャラクターとして
  よく同梱・指定されている**（[Open-LLM-VTuber v1.2.0 リリースノート](http://docs.llmvtuber.com/en/blog/v1.2.0-release/)）
- 参考：[Live2D クリエイターズフォーラム](https://creatorsforum.live2d.com/t/topic/2754)

つまり佐倉みどりは、**「虹色まお」の体を借りて喋っている**状態。人格（`sakura_midori.yaml`）と
声（`voice/sakura_midori.wav`）は自前だが、見た目だけは Live2D 公式の素材を使っている。
アバターを自作する（バックログの「アバター・見た目」）までは、この構成が続く。

呼び分け：**設定ファイルやコード上の識別子は `mao_pro`、日本語の文章で
キャラクターを指すときは「虹色まお」**。GLOSSARY.md に登録済み。

### Live2D の利用条件（守ること）

`mao_pro` は Live2Dオリジナルキャラクターで、個別利用条件が無く、一般ユーザー
（直近売上高1,000万円未満）は営利・非営利を問わず利用できる（Free Material
License Agreement 2.1.3.1）。ただし**著作権表記が必須**（同 2.1.5）。

YouTube 概要欄など長文が書ける場所:

```
This content uses sample data owned and copyrighted by Live2D Inc.
The sample data are utilized in accordance with terms and conditions set by Live2D Inc.
This content itself is created at the author's sole discretion.
```

X など短文しか書けない場所:

```
This content uses sample data owned and copyrighted by Live2D Inc.
```

`shizuku` は**使用不可**。個別利用条件に「名前や設定を変えずに使うこと」と
あり、佐倉みどりとして使うことがこれに反する。`model_dict.json` にも未登録の
まま放置する。

---

## バックログ（未着手、優先度未確定）

### 次にやる候補（着手条件が揃っているもの）

- **佐倉みどりの会話テスト**。Build Log #012 で、Setting → `Character Preset` →
  佐倉みどり を選び、日本語で会話できるところまでは確認済み（短縮版ペルソナ）。

  対応済み：
  - **関西弁を削除**し、標準語のフランク調に統一（口調ルール本体と例文の語尾・
    一人称。長文版 `sakura_midori.v1-full.yaml` も同時に修正）
  - **話者混同**。自分を「みどりちゃん」と呼んで相手扱いする誤りが出た
    （実例：「[smirk] みどりちゃん、頑張ってね！」）。引き金は口癖
    「いつか、みどりちゃんに体を！」＝ペルソナ内で唯一、自分を三人称で呼ぶ表現。
    「自分＝みどり／相手＝ドクター」の対応と、この誤り文そのものを反例として
    明記して解消。**ドクター呼びが定着したことを実機で確認済み**

  **「ドクター」→「師匠」の切り替わりは Build Log #013 で発動を確認済み**
  （実験成功を伝えたら「師匠！めっちゃうれしい😆」と返した）。

  残りの確認ポイント：脱線の頻度、日本語以外や方言が混ざらないか、そして
  **話しかけてから声が返るまでの体感時間**（ASR → LLM → TTS の通し。#007 では
  qwen2.5 が体感5秒未満、qwen3:8b が約5秒遅れだった）

- **起動時デフォルトを佐倉みどりに戻す**。クリーンインストールで `conf.yaml` が
  再生成され、起動時キャラクターは既定の `Mao`（英語ペルソナ）に戻っている。
  `characters/sakura_midori.yaml` は切替候補として読まれるだけで起動時に自動適用
  されない（#010 の調査結果）。毎回 `Character Preset` で切り替えるのが面倒に
  なったら、#010 と同じく `conf.yaml` の `character_config` に反映する

- ~~**Ollama の `num_ctx` 引き上げ**~~ → **Build Log #012 で対応済み。**
  `qwen3-nothink`（`qwen3:8b` ベース、テンプレート改変で thinking 無効化 ＋
  `PARAMETER num_ctx 8192`）を作成し、`/v1` 経由で thinking が出ないこと・
  CONTEXT が 8192 になることを確認した。Modelfile は `~/ollama-modelfiles/`。
  persona も 1,246 → 260 トークンに短縮済み。
  **その後 #013 で `qwen3-vl-8k`（vision 対応）に載せ替えたため、`qwen3-nothink`
  は現在使っていない。** テキスト専用に戻す判断をしたときのために残してある。

  補足：Ollama の既定 `num_ctx` はバージョンで変わる（0.33.3 では 2048 ではなく
  4096 だった）。溢れても**エラーにならず古い履歴が黙って捨てられる**ので、
  実際の値は `ollama ps` の CONTEXT 列で毎回実測する。
  なお `options.num_ctx` は Ollama ネイティブAPI 専用で、Open-LLM-VTuber が使う
  OpenAI 互換API（`/v1`）からは指定できない。**Modelfile に焼くのが唯一の手段。**

- **Open-LLM-VTuber をフォークして開発を始める**。Linux のペットモード対応
  （Build Log #010）を皮切りに、今後も本家に手を入れ続けることになる。現状は
  本家クローンの `main` を直接編集し、diff を `patches/` に退避しているだけで、
  push 先が無い状態。フォークすれば履歴が残り、上流への PR も出せる。
  対象は `Open-LLM-VTuber-Web`（フロントエンド/Electron）と
  `Open-LLM-VTuber`（バックエンド）の2つ

- **Linux ペットモード対応を上流へ PR**。公式は Linux バイナリを配布しておらず、
  この修正はそのまま貢献になる。関連 issue は electron/electron#16777（Linux で
  `setIgnoreMouseEvents` の forward が未対応、2019年から open）。
  フォーク作成が前提

### アバター・見た目

- アバターの見た目デザイン（Hi3Dの「テキストから画像」で検討）。方向性
  （髪型・服装）は未定
- SadTalkerでの音声駆動リップシンク動画生成（後合成方式）。
  RTX5060Ti（Blackwell）はPyTorchのバージョン互換に注意
  （2.7.0+cu128系が必要になる可能性）
- Live2D（2D）→ VRM/Amica（3D）への将来的な移行構想。Live2D は2D表現への
  魅力の薄さと FREE版の機能制限（アートメッシュ100・ブレンドシェイプ用
  パラメータ3等）で保留中。VRoid Studio での3D制作も選択肢。
  「地味な相棒が突然3Dになる」演出として温存。秘匿対応は不要、
  Build Logは正直に書いてよい

### 運用・仕組み

- 当日の収録メモをLLMに渡す仕組みの自動化（MCPツール化）。
  今はやらない。「収録開始時に一言喋って渡す」方式を実際に運用して
  みて、不便を実感してから着手する。人格定義と当日情報は分離し、
  persona_prompt には当日情報を書き足さない

### TTSアップグレード（Build Log #013 で決着）

**Irodori-TTS を採用した。** 以下は採用前の比較検討メモとして残す（他候補へ乗り換える
判断が必要になったときのために消さない）。Irodori-TTS が満たしたのは、ローカル完結・
MIT ライセンス・リアルタイム相当の速度・ゼロショット音声クローン・絵文字による感情制御。

| 採用したもの | 内容 |
|---|---|
| サーバー | https://github.com/Aratako/Irodori-TTS-Server （OpenAI TTS API 互換、`localhost:8088`） |
| モデル | `Aratako/Irodori-TTS-v4-Small`（MIT） |
| 声 | `voice/sakura_midori.wav`（caption `ボーイッシュな女性の声。さっぱりとした話し方。` / seed `1006` で生成） |
| 感情制御 | 絵文字7種を人格定義で指定。`conf.yaml` の `remove_special_char: False` が必須 |
| 注意 | 絵文字は「。」「！」「？」の直前に置く。後ろだと単独チャンクになる（`patches/013-sentence-divider-emoji.patch` で吸収） |

以下は採用前に比較した候補：

| モデル | ライセンス | 特徴・向き不向き |
|---|---|---|
| Qwen3-TTS | Apache-2.0 | ゼロショットボイスクローン、VoiceDesign対応、ストリーミング100ms未満（0.6Bモデル）。日本語の口語表現は自然だが、固有名詞・英字混在（SO-101、LeRobot等プロジェクト固有語）で読み誤りリスクあり → SSML `<phoneme>` タグか前処理変換辞書での補正が必要。リファレンス音声は24kHz以上・静音収録推奨。手軽に試すならこちら |
| CosyVoice 3.0 | Apache-2.0 | クロスリンガルクローンが最強クラス、ライセンス潔癖性重視ならこちら |
| Style-Bert-VITS2 | (要確認) | ゼロショットではなく本格ファインチューニング路線。ita-corpus（感情朗読者用収録台本、github.com/mmorise/ita-corpus）を自分で全部収録して学習させる想定。参考動画: youtube.com/watch?v=aTUSzgDl1iY、リポジトリ: github.com/litagin02/Style-Bert-VITS2。時間はかかるが一番作り込んだ専用ボイスになる |
| Fish Speech | モデルにより異なる（CC-BY-NC-SA-4.0非商用〜条件付き商用可が混在） | バージョンごとにライセンスが変わるため採用時は都度HuggingFaceのLICENSE要確認 |
| Supertonic 3 | (要確認) | 完全ローカル・CPU動作の軽量日本語TTS。VOICEVOXと同じ「低遅延・軽量」枠の新しい選択肢 |

**判断の目安**：手軽に早く試すならQwen3-TTSのゼロショットクローン、本気で
専用ボイスを育てるならita-corpus収録＋Style-Bert-VITS2ファインチューニング、
ライセンスを完全にクリアにしたいならCosyVoice 3.0。VOICEVOXは低遅延・
シンプルAPIの対抗馬として残す。着手は佐倉みどりのキャラクターが固まり、
「本気で声を作り込みたい」となってから

---

## 起動手順

### いつもの起動：スクリプト1本

```bash
~/Develop/project-physical-ai/ConversationalAI/start-midori.sh
```

Irodori-TTS → LLM の事前ロード → バックエンド → Electron（ペットモード）まで一気に立ち上げる。
**Ctrl+C か Electron を閉じると、このスクリプトが起動したサーバーも一緒に止まる。**

| オプション | 動作 |
|---|---|
| （なし） | Electron まで起動 |
| `--check` | 起動せず、3プロセスの生死だけ表示 |
| `--no-app` | Electron を起動しない（ブラウザで使うとき） |
| `--no-warm` | LLM の事前ロードをしない |

性質：

- **すでに動いているサーバーは再利用し、終了時にも止めない。** 自分で起動したものだけ片付ける
- ログは `~/.local/state/sakura-midori/{irodori,vtuber}.log`
- 起動時に `voices/` のリファレンス音声が無ければ警告する（声が毎回変わる状態の検知）
- LLM を事前に VRAM へ載せるので、最初の応答からロード待ちが無い

以下は、スクリプトが何をしているかの内訳。手で追うときや、詰まったときの参照用。

---

**佐倉みどりを起動する = プロセス3つ。** うち Ollama は systemd で自動起動しているので、
実際に手で叩くのは2つ（TTS サーバーとバックエンド）＋ 画面（ブラウザか Electron）。

| # | プロセス | ポート | 手で起動する？ |
|---|---|---|---|
| 1 | Ollama（LLM `qwen3-vl-8k`） | 11434 | **不要**（systemd で自動起動・常駐） |
| 2 | Irodori-TTS-Server（音声） | 8088 | **必要** |
| 3 | Open-LLM-VTuber バックエンド | 12393 | **必要** |
| 4 | 画面（ブラウザ or Electron ペットモード） | — | どちらか |

起動前・起動後の一括確認：

```bash
curl -s http://localhost:11434/api/tags >/dev/null && echo "✅ Ollama"      || echo "❌ Ollama"
curl -s http://localhost:8088/health    >/dev/null && echo "✅ Irodori-TTS" || echo "❌ Irodori-TTS"
curl -s http://localhost:12393          >/dev/null && echo "✅ VTuber"      || echo "❌ VTuber"
```

### 1. Ollama（起動不要・確認のみ）

systemd サービスとして自動起動する。手で起動する必要はない。

```bash
systemctl is-active ollama   # active ならOK
ollama ps                    # 空でも問題ない。最初のリクエストでロードされる
```

止まっていたときだけ `sudo systemctl start ollama`。

### 2. TTS サーバー（先に起動しておく）

```bash
cd ~/development/Irodori-TTS-Server
uv run --no-sync python -m irodori_openai_tts --host 0.0.0.0 --port 8088
curl http://localhost:8088/health   # 別ターミナルで確認
```

**これを起動していないと音声が出ない。** このターミナルは開いたままにする。

### 3. バックエンド

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run run_server.py
```

### 4a. ブラウザで開く

```
http://localhost:12393
```

起動直後のキャラクターは `conf.yaml` の `character_config` 依存で、現在は既定の
`Mao`（英語ペルソナ）。**Setting → `Character Preset` → 佐倉みどり** で切り替える。
毎回の切り替えが面倒になったら、バックログの「起動時デフォルトを佐倉みどりに戻す」を行う。

### 4b. Electron版（Desktop Pet Mode）

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber-Web/release/1.2.1/linux-unpacked
env -u ELECTRON_RUN_AS_NODE ./open-llm-vtuber
```

`env -u ELECTRON_RUN_AS_NODE` は必須。VS Code の拡張ホストから起動すると
`ELECTRON_RUN_AS_NODE=1` を継承し、Electron が GUI を出さず素の Node.js として
起動してしまう（引数なしで即 exit 0、`--no-sandbox` を渡すと `bad option` で
exit 9）。

AppImage は Ubuntu 24.04 に `libfuse2` が無いため直接起動できない。上記の
`linux-unpacked/` 内のバイナリを直接叩く。

ペットモードへの切り替えは**トレイアイコン → Pet Mode**。右クリックの文脈
メニューは `isPet` のときしか出ないので、Window Mode では反応しない。

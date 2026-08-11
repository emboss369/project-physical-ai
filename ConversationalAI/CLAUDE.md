# ConversationalAI — 相棒AI「佐倉みどり」

Open-LLM-VTuber をベースにした、Project Physical AI の相棒AIキャラクター。

## このディレクトリの中身

| ファイル | 役割 |
|---|---|
| `sakura_midori.yaml` | 佐倉みどりのキャラクター設定。**ここが正**で、Open-LLM-VTuber 側の `characters/sakura_midori.yaml` はここへのシンボリックリンク |
| `patches/` | 本家 Open-LLM-VTuber に加えた改修の diff バックアップ |

本家リポジトリは `conf.yaml` と `characters/*` を `.gitignore` で除外しているため、
設定をあちらに置くとどこにも残らない。必ずこちら側を正にする。

## 現在の構成（Build Log #007・#010 時点）

| 要素 | 設定 |
|---|---|
| LLM | Ollama `qwen2.5:latest` / temperature 0.9 |
| TTS | edge_tts `ja-JP-NanamiNeural` |
| ASR | sherpa-onnx（SenseVoiceSmall、CPU推論） |
| Live2Dモデル | `mao_pro`（Live2Dオリジナルキャラクター「Mao Niziiro」） |
| 実行形態 | Electron 版をソースビルド（Linux バイナリは公式配布なし） |

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

- **佐倉みどりの会話テスト**。ペルソナを投入して起動するところまでは完了して
  いるが、まだ一度も喋らせていない。ペットモードで右クリック →
  `Switch Character` → 佐倉みどり で切り替え、新規会話でリセットしてから確認する。
  見るポイント：関西弁の濃さ、脱線の頻度、「ドクター」→「師匠」の切り替わりが
  発動するか、日本語以外が混ざらないか

- **Ollama の `num_ctx` 引き上げ**。Ollama はデフォルトで `num_ctx` が 2048
  トークンに制限されており、モデル自体が128k対応でも黙って切り捨てられる。
  佐倉みどりの persona_prompt は長め（約1,700文字）なので、人格定義が
  途中で欠ける可能性がある。Modelfile で引き上げる：

  ```
  FROM qwen3:8b
  PARAMETER num_ctx 8192
  ```

  ```bash
  ollama create qwen3-8b-8k -f Modelfile
  ```

  作成後 `conf.yaml` の `ollama_llm.model` を `qwen3-8b-8k` に変更する。
  ただし Build Log #007 で qwen3:8b は thinking モードによる約5秒の遅延が
  ネックと判断して見送った経緯があるため、qwen2.5 側で同じことをやるか、
  遅延を許容するかは会話テストの結果を見て決める

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

### TTSアップグレード（調査済み、未着手）

edge_tts → Azure Neural TTS（無料枠月50万文字）が既定路線。その先の本格
アップグレード候補として以下を比較検討済み：

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

### バックエンド

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run run_server.py
```

### Electron版（Desktop Pet Mode）

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

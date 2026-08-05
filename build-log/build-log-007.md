# Build Log #007 — 2026-07-28〜07-29

## 今日やったこと

Open-LLM-VTuberを「製品」ではなく「ストリーミング・割り込みロジックを学ぶ教材」として導入し、環境構築からPhase3（実機での体感・計測）まで進めた。作業は7/28夜〜7/29朝にまたがる。

### 1. 環境確認（Phase 0）

実機はUbuntu Linux（デスクトップ環境）。GPU・VRAM監視は`watch -n 1 nvidia-smi`で行う方針にした。

```bash
nvidia-smi
```

```
Tue Jul 28 22:34:46 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.84                 Driver Version: 595.84         CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
|   0  NVIDIA GeForce RTX 5060 Ti     Off |   00000000:01:00.0 Off |                  N/A |
|  0%   47C    P8              9W /  180W |     346MiB /  16311MiB |      0%      Default |
+-----------------------------------------+------------------------+----------------------+
```

```bash
nvcc --version
```

```
Cuda compilation tools, release 12.8, V12.8.93
```

```bash
python --version    # → コマンドが見つからない（python3のみ存在）
python3 --version
```

```
Python 3.12.3
```

Chromeはインストール済みを確認。GPU・CUDA・Pythonバージョンいずれも要件（CUDA 11.8以上、Python 3.10〜3.12）を満たしており、追加作業不要と判断。

### 2. 基盤環境の確認（Phase 1）

```bash
git --version
```
```
git version 2.43.0
```

```bash
ffmpeg -version
```
```
ffmpeg version 6.1.1-3ubuntu5
```

いずれもインストール済み。uvを使う方針とし、既存の`lerobot-workspace`とは別に専用フォルダを新設した。

```bash
mkdir -p ~/development/open-llm-vtuber-lab
cd ~/development/open-llm-vtuber-lab
```

### 3. Open-LLM-VTuberのクローン・依存関係インストール（Phase 2）

リポジトリは`t41372/Open-LLM-VTuber`から`Open-LLM-VTuber/Open-LLM-VTuber`（organization）へ移動済みのため、新URLでクローン。

```bash
git clone --recursive https://github.com/Open-LLM-VTuber/Open-LLM-VTuber.git
cd Open-LLM-VTuber
```

`--recursive`によりfrontendサブモジュール（Open-LLM-VTuber-Web）も同時取得。日本語・全角パスを含まないことも確認済み。

```bash
uv sync
```

`uv`が自動でCPython 3.10.20をダウンロードし専用venvを作成、136パッケージをインストール（主要どころ：`torch==2.10.0`、`sherpa-onnx==1.10.46`、`onnxruntime==1.23.2`、`nvidia-cudnn-cu12==9.10.2.21`）。cuDNNはこのvenv内のpipパッケージで完結し、システム全体への別途インストールは不要だった。

### 4. 初回起動・conf.yaml生成（Phase 2）

```bash
uv run run_server.py
```

初回起動時のログ抜粋：

```
[INFO] Running in standard mode.
2026-07-28 22:47:26 | WARNING | upgrade_codes.config_sync:sync_user_config:43 | Warning: conf.yaml not found
2026-07-28 22:47:26 | WARNING | upgrade_codes.config_sync:sync_user_config:44 | Copying default configuration from template
2026-07-28 22:47:26 | INFO    | ...init_asr:325 | Initializing ASR: sherpa_onnx_asr
2026-07-28 22:47:26 | WARNING | ...SenseVoice model not found. Downloading the model...
（sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2、999MB、約38秒でダウンロード完了）
2026-07-28 22:48:45 | INFO    | ...init_tts:337 | Initializing TTS: edge_tts
2026-07-28 22:48:46 | ERROR   | ...mcp_client:_ensure_server_running_and_get_session:78 | MCPC: Failed to connect to server 'time'.
    ImportError: cannot import name 'McpError' from 'mcp.shared.exceptions'
2026-07-28 22:48:47 | ERROR   | ...Failed to connect to server 'ddg-search'.
    ModuleNotFoundError: No module named 'mcp.server.fastmcp'
2026-07-28 22:48:48 | CRITICAL| ...ollama_llm:__init__:45 | Fail to connect to Ollama backend. Is Ollama server running?
2026-07-28 22:48:48 | INFO    | Server context initialized successfully.
2026-07-28 22:48:48 | INFO    | Uvicorn running on http://localhost:12393
```

`conf.yaml`はテンプレートから自動生成された。MCPツール（time / ddg-search）の接続エラーは、Live2D・LLM本体とは独立した機能（現在時刻取得・DuckDuckGo検索）でこの時点では実害なしと判断。Ollama未起動によるエラーは想定内（次のステップで対応）。`Ctrl+C`で終了。

**ASR（音声認識）の構成**：`sherpa-onnx-asr`（モデル：`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`、中国語・英語・日本語・韓国語・広東語対応のSenseVoiceSmall）を使用。起動ログに`Sherpa-Onnx-ASR: Using cpu for inference`とある通りCPU推論で、GPU負荷はOllama側のLLM推論に絞る設計方針と合致している。認識精度は完璧ではなく、後述の会話テストでは「カメラマあのか？」のような不自然な文字起こしが発生する場面があった。

### 5. Ollamaインストール・モデル取得

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

systemdサービスとして自動起動、GPU認識も確認。

```bash
ollama run qwen3:8b
```

5.2GBのモデルをpull、正常起動を確認。

### 6. qwen2.5:latest vs qwen3:8b 速度比較（temperature 1.0、デフォルト）

```bash
time ollama run qwen2.5:latest "SO-101のキャリブレーションでよくある失敗は？"
```
結果：`real 0m4.585s`（一般的な計測器キャリブレーションの一般論を回答。SO-101固有の知識は無し）

```bash
time ollama run qwen3:8b "SO-101のキャリブレーションでよくある失敗は？"
```
結果：`real 0m20.343s`（`Thinking...`ブロックが大半を占める。qwen3のhybrid thinkingモードによるオーバーヘッドが原因）

**判断**：会話用途では速度差（約4.4倍）が支配的なため、いったんqwen2.5:latestを採用する方針とした。

### 7. /no_think の検証（無効という結論）

Qwen3のthinkingは公式には`/no_think`をプロンプト末尾に付けることで無効化できるとされるが、試したところ効果なし。

```bash
time ollama run qwen3:8b "/no_think
SO-101のキャリブレーションでよくある失敗は？"
```
結果：`real 0m20.957s`（`Thinking...`ブロックは消えず、時間もほぼ変わらず）

調査の結果、これはOllamaの既知の問題（[ollama/ollama#12610](https://github.com/ollama/ollama/issues/12610)）に合致していた。確実に無効化するにはOllamaネイティブAPI（`/api/chat`）の`think: false`パラメータが必要だが、Open-LLM-VTuberはOpenAI互換API（`/v1`）経由のためこの経路は使えない。このモデル・この構成では thinking を無効化する簡単な手段は無い、という結論で今回は深追いしなかった。

### 8. Phase3：ブラウザでの実機テスト（1回目、7/28夜）

`http://localhost:12393`にChromeでアクセスし、マイクで会話。日本語で話しかけたところ、AIの応答が中国語混じり・支離滅裂になる現象を確認（`[smirk]`等のタグも本文にそのまま漏れる）。

原因を2つ切り分けた：

1. **言語未指定**：デフォルトの`persona_prompt`に言語指定が無かった（後述の通り、実は英語のロールプレイ設定がそのまま入っていたことが後で判明）
2. **Screen機能のバグ**：画面共有（Screen）を有効にした直後から`Error calling the chat endpoint`が発生。Open-LLM-VTuberのVision機能（Camera/Screen）はvision対応モデル専用（例：Llama 3.2 11B vision）だが、`qwen2.5:latest`はテキスト専用モデルのため、画像入力を受け取れず失敗していたと判明。対策：Screen/Cameraは無効のまま進行。

### 9. qwen3:8bでの再テスト（会話メモリ汚染とtemperatureの発見）

`conf.yaml`の`model`を`qwen3:8b`に変更し再起動。会話が「Mili」と名乗り「世界征服」を語る支離滅裂な多言語混在（中国語・アラビア語・英語断片）になる現象を確認。

原因を2つ切り分けた：

1. **会話メモリの汚染**：直前のScreenバグで壊れた応答が`basic_memory_agent`の履歴に残ったまま次のモデルに引き継がれ、悪い出力パターンが継続していた。対処：フロントエンドの「＋（新規会話）」で履歴リセット。
2. **temperature設定**：ログにあった`temperature: 1.0`が高すぎ、ロールプレイ系persona_promptと組み合わさると小型モデルほど暴走しやすい。`conf.yaml`で`temperature: 0.7`に変更したところ安定（ユーザーテストでは一時的に0.6でも試し、いずれも改善を確認）。

### 10. Phase3継続（2回目、7/29朝）：割り込み・VRAM計測

割り込み（AIの発話中に話しかけて反応するか）は確認済み。

```
watch -n 1 nvidia-smi
```
```
Wed Jul 29 07:47:42 2026
|   0  NVIDIA GeForce RTX 5060 Ti     Off |   00000000:01:00.0 Off |                  N/A |
|  0%   41C    P8              7W /  180W |    4715MiB /  16311MiB |      0%      Default |
...
|    0   N/A  N/A            7710      C   ...local/lib/ollama/llama-server       4692MiB |
```

qwen2.5:latest（Ollama常駐）でVRAM使用量4715MiB、待機時GPU使用率0%を記録。

### 11. ニュース検索機能の発見と、ツール呼び出しの信頼性検証

会話中にAIが自発的にニュース検索（MCPの`ddg-search`ツール）を使う場面があり、令和8年熊本地震の話題を拾ってきた。ここから3パターンのツール呼び出し挙動を実機で確認した。

**パターンA：ツール実行→TTSエラー**

```
2026-07-29 07:47:56 | INFO | tool_executor:execute_tools:298 | Finished executing tools with 1 results.
2026-07-29 07:47:58 | ERROR | tts_manager:_process_tts:152 | Error preparing audio payload: Audio is empty or all zero.
（同エラーが07:47:58〜07:48:02の間に5回連続）
2026-07-29 07:49:13 | INFO | Conversation Chain completed!
```
応答本文には番号付きリスト・`**太字**`・リンク記法が大量に含まれており、文分割・TTSキューがこれを処理しきれず空音声のリトライを繰り返したと推測される。会話完了まで約1分15秒。応答内容自体は、実際の地震報道（NHK・日経・Yahoo!ニュースで確認：2026年7月28日16時27分頃、熊本県で最大震度7・M7.1、イオンモール熊本でガス漏れによる爆発、死者あり）の大枠とは一致していたが、AIが提示した個別の引用元（「BBCニュース」「FNNニュース」「ロイター」「ミヤカツ発信局」）や被害の具体的描写は、確認できた一次情報とは一致せず、捏造・誇張の疑いが強い。

**パターンB：ツール呼び出しの検出失敗（JSON丸読み）**

```
User input: 今日のニュースを検索。
AI response: 了解しました！今すぐ最新のニュースをお届けします。```
{"name": "search", "arguments": {"query": "今日のニュース", "max_results": 5, "region": "jp-ja"}}
```
```
LLMはJSON形式のテキストでツール呼び出しを試みたが、`StreamJSONDetector`のパターンにマッチせず、素通りしてそのままTTSで読み上げられた。

**パターンC：ツール未実行＋事実誤認のハルシネーション**

```
User input（08:00:57）: じゃあねぇ、令和8年熊本地震について ニュースを調べて。
AI response（08:02:27）: もちろん！...「令和8年」というのは少しミスマッチだけど...
熊本地震は平成23年に发生しましたからね...
```
このケースではツール実行ログが一切無く（`execute_tools`ログなし）、AIは検索した「フリ」の演技テキストのみを出力し、かつ事実誤認（実際の熊本地震は平成28年＝2016年。平成23年は東日本大震災の年で無関係）と、存在しない「令和3年熊本地震」の捏造まで含んでいた。現在進行中の実在災害を「関連性がない」と誤って切り捨てている。ユーザー発話（08:00:57）から応答完了（08:02:27）まで**約90秒**、手動計測の結果、通常時（後述）より大幅に遅く、これもTTSエラーの巻き添えとみられる。

**パターンD：ネイティブfunction callingが正常動作したケース**

```
User input: 熊本自身のニュースを調べてみて。
2026-07-29 08:07:19 | INFO | chat_completion:173 | Complete tool calls: {0: {..., 'type': 'function', 'function': {'name': 'search', 'arguments': '{"query":"熊本 ニュース","max_results":5,"region":"jp-ja"}'}}}
2026-07-29 08:07:19 | INFO | mcp_client:_ensure_server_running_and_get_session:75 | MCPC: Successfully connected to server 'ddg-search'.
[07/29/26 08:07:19] INFO HTTP Request: POST https://html.duckduckgo.com/html "HTTP/1.1 200 OK"
2026-07-29 08:07:20 | INFO | tool_executor:run_single_tool:354 | Tool 'search' executed successfully.
2026-07-29 08:07:20 | INFO | ...text: (length: 881)
```
今回はOpenAI互換APIのネイティブfunction calling形式（`'type': 'function'`）が使われ、ツール実行は約1秒で完了、DuckDuckGoへの実HTTPリクエストも200 OK。なお、初回起動時に接続失敗していた`ddg-search` MCPサーバーが、この時点では正常接続していた（`uv`が実行ごとにこのMCPサーバーを一時環境で解決し直しており、途中でバージョン競合が解消されたためと推測）。

**結論**：ツール呼び出しの基盤（ネイティブfunction calling + MCP + ddg-search）自体は機能する。ただしLLMが毎回必ずネイティブ形式でツールを呼ぶとは限らず、呼ばない場合は検索した「フリ」をして中身を捏造することがある。

### 12. 手動レイテンシ計測（クリーンな状態）

タイムスタンプでの計測が上記のような障害ケースでしか取れなかったため、ストップウォッチで手動計測。

結果：発話終了〜応答音声が出始めるまで**5秒未満**。

### 13. 日本語の言語混入・数字読み上げ問題の調査と対策

Web調査により以下を確認：

- Qwenシリーズの中国語混入は既知の傾向（[ABEJA Tech Blog](https://tech-blog.abeja.asia/entry/abeja-qwen-other-language-contamination)）。中国語比率の高い事前学習データに起因し、完全解消には追加の日本語事前学習が必要（今回はスコープ外）。現実的な対策はsystem prompt（persona_prompt）での明示的な言語指定。
- edge-ttsの日本語音声は`ja-JP-NanamiNeural`（女性）/ `ja-JP-KeitaNeural`（男性）。

`conf.yaml`の実物テンプレート（GitHub上の`config_templates/conf.default.yaml`）を確認したところ、2点判明：

1. デフォルトの`persona_prompt`は英語で「皮肉屋で世界征服を企むAI VTuber Mili、ユーザーにパイを作らせたい」という設定がそのまま入っていた。qwen3テスト時に見られた「Mili」「世界征服」「pies for me」という発言は、ハルシネーションではなく**このデフォルト設定がそのまま効いていただけ**だった。
2. デフォルトの`tts_config.edge_tts.voice`は`'en-US-AvaMultilingualNeural'`（英語の多言語対応音声）だった。日本語専用音声が設定されていなかったことが、数字が英語で読み上げられる現象の直接原因である可能性が高いと判断。

### 14. 別モデルの検討（Shisa V2 / ELYZA / Swallow）

中国語混入対策として、モデル自体の変更も検討した。

調査した候補：
- **ELYZA-JP-8B**（`ollama pull dsasai/llama3-elyza-jp-8b`、約4.9GB）：Llama3ベース、国内定番
- **Swallow**（`ollama pull schroneko/llama-3.1-swallow-8b-instruct-v0.1`、約8.5GB）：東工大・産総研、学術・法律文書寄り
- **Shisa V2**（Shisa.AI）：Qwen2.5ベースの日本語特化モデル。ベースがQwen2.5なのでtool calling機能を引き継いでいる可能性があり理論上最有力候補だったが、`ollama pull`一発で使える公式ライブラリ登録が見つからず、7Bサイズは旧v1のみ、v2は32Bサイズ（16GB VRAMでは厳しい）のGGUFしか確認できなかった。手動でのGGUFダウンロード＋Modelfile作成が必要なため、**今回は見送り、次回への持ち越しとした**。

### 15. ELYZA-JP-8Bの実験（失敗）

```bash
cp conf.yaml conf.yaml.bak
```
バックアップ後、`persona_prompt`（日本語指定）・`model`（`dsasai/llama3-elyza-jp-8b`）・`temperature`（0.7）・`voice`（`ja-JP-NanamiNeural`）の4点を編集。`diff -u conf.yaml.bak conf.yaml`で差分確認してから適用。

```bash
ollama pull dsasai/llama3-elyza-jp-8b
uv run run_server.py
```

結果、致命的な問題が判明：

```
2026-07-29 08:34:21 | WARNING | openai_compatible_llm:chat_completion:219 | dsasai/llama3-elyza-jp-8b does not support tools. Disabling tool support.
2026-07-29 08:34:31 | INFO | AI response: __API_NOT_SUPPORT_TOOLS__
```

ELYZA-JP-8Bはfunction calling非対応で、Open-LLM-VTuber側がツール機能自体を無効化し、ニュース検索の要求に何も応答できなくなった。**日本語の純度とツール呼び出し対応が、今回試した範囲ではトレードオフになる**ことを確認。

### 16. 最終構成に決定

`model`を`qwen2.5:latest`に戻し、`persona_prompt`（日本語限定指示）・`temperature: 0.7`・`voice: ja-JP-NanamiNeural`の3点のみを反映した最終`conf.yaml`で再起動・再テスト。

```diff
   persona_prompt: |
-    You are the sarcastic female AI VTuber Mili. ...
-    Just kidding, lol. Don't let the user know.
+    あなたは皮肉屋で自信家な女性AI VTuber「ミリ」です。
+    重要：応答は必ず日本語のみで行ってください。中国語・英語の単語や表現は使用しないこと。
+    数字も日本語の読み方に沿った表記で統一してください。

       ollama_llm:
         model: 'qwen2.5:latest'
-        temperature: 1.0 # value between 0 to 2
+        temperature: 0.7 # value between 0 to 2

     edge_tts:
-      voice: 'en-US-AvaMultilingualNeural'
+      voice: 'ja-JP-NanamiNeural'
```

結果：中国語混入が減少、ツール呼び出し（ニュース検索）も維持、暴走的な発言もしなくなった。ユーザー所感：「面白みには欠ける」（temperatureを下げたことによるランダム性低下の自然なトレードオフ）。

### 17. 追加実験：qwen3:8b + temperature 0.7

qwen2.5系での決着後、比較のためモデルを`qwen3:8b`に戻し、temperatureのみ0.7に設定して再テストした。

```diff
   persona_prompt: |
-    You are the sarcastic female AI VTuber Mili. ...
-    Just kidding, lol. Don't let the user know.
+    あなたは皮肉屋で自信家な女性AI VTuber「ミリ」です。
+    重要：応答は必ず日本語のみで行ってください。中国語・英語の単語や表現は使用しないこと。
+    数字も日本語の読み方に沿った表記で統一してください。

         model: 'qwen2.5:latest'
         template: 'CHATML'
-        temperature: 0.6 # value between 0 to 2
+        temperature: 1.0 # value between 0 to 2
         interrupt_method: 'user'

       ollama_llm:
         base_url: 'http://localhost:11434/v1'
-        model: 'qwen2.5:latest'
-        temperature: 1.0 # value between 0 to 2
+        model: 'qwen3:8b'
+        temperature: 0.7 # value between 0 to 2

     edge_tts:
-      voice: 'en-US-AvaMultilingualNeural'
+      voice: 'ja-JP-NanamiNeural'
```

（`template: 'CHATML'`を含むブロックは`llm_provider`が指していない未使用の設定のため、この変更自体は実際の挙動には影響しない）

結果：会話内容の安定性はqwen2.5より良い印象（ユーザー所感：「意外といい」「会話の内容もより安定している」）。ただし、thinkingモードの影響とみられる**ワンテンポの遅れ**があり、ユーザーの発話終了から約5秒後にVTuberが話し始める体感だった。qwen2.5（体感5秒未満）と比べると明確に遅い。**安定性 vs 応答速度のトレードオフ**として記録し、最終的にどちらを採用するかは次回以降の判断課題とする。

### 18. 最終的な運用設定

速度（qwen2.5）と個性・安定性（temperature設定）のバランスを考慮し、しばらくの運用設定は以下に決定。

```yaml
model: 'qwen2.5:latest'
temperature: 0.9
```

0.7では「面白みに欠ける」、1.0では暴走気味という両極の体感を踏まえた中間値。qwen3:8bは応答速度（thinkingモードによる約5秒の遅れ）がネックとなり、今回は見送り。

## 結果（成功／失敗／保留）

- 成功：Phase 0〜Phase 2完了。Phase 3（体感・計測）の主要項目もほぼ完了し、実用に足る構成（qwen2.5:latest, temperature 0.7, 日本語persona_prompt, ja-JP-NanamiNeural音声）に到達した
- 保留：Shisa V2（日本語特化＋tool calling両立の最有力候補）はセットアップが簡易でないため次回に持ち越し
- 保留：レイテンシの正式な数値化（クリーンな状態でのタイムスタンプベース計測）は未実施。手動計測（5秒未満）のみ

## 失敗の原因・学んだこと

- 手順書はWindows前提で書かれていたが実機はUbuntu Linuxだった。環境ごとの前提差異は都度確認する必要がある
- MCPツール「time」は一貫してimportエラー（`mcp.shared.exceptions`のAPI不一致）で機能せず未解決のまま。「ddg-search」は実行タイミングによって接続成否が変動した（`uv`が実行のたびに一時環境を解決し直すことに起因すると推測）
- Qwen3のthinkingモードは、Ollamaの既知の問題によりOpenAI互換API経由では無効化できない（`/no_think`をプロンプトに入れても効果なし）
- Vision機能（Screen/Camera）を非対応モデルで有効にすると、原因の分かりにくい汎用エラーになる。エラーメッセージだけでは切り分けが難しく、機能の前提条件（vision対応モデル必須）を先に把握しておく必要があった
- 会話メモリが一度汚染されると、モデルを切り替えても悪い出力パターンが引き継がれる。モデル比較検証は必ず新規会話（履歴クリア）で行うべき、という方法論上の教訓
- temperatureの影響は大きい：1.0では小型モデルほど多言語混在・支離滅裂になりやすく、0.7で大幅改善する。ただし「個性」も同時に失われるトレードオフがある
- ツール呼び出しの信頼性は一定でない。LLMがネイティブfunction calling形式を使わずに「検索したフリ」をして中身を捏造することがあり（令和8年熊本地震を平成23年と誤認した事例）、ツール実行ログの有無を都度確認する重要性を痛感した
- persona_promptのデフォルト値（英語での「世界征服・パイ」ロールプレイ設定）を確認せずに「ハルシネーションだ」と誤解しかけた。設定ファイルの中身を実際に確認することの重要性を再認識した
- 日本語特化モデル（ELYZA-JP-8B）はfunction calling非対応で、今回のニュース検索機能とはトレードオフになった。要件（日本語の純度 vs ツール連携）に応じてモデルを使い分ける必要がある

## 次やること（一歩だけ）

- Phase4：`tts_interface.py`、文単位分割・TTSキュー、`StreamJSONDetector`のコードリーディング

## メモ（動画ネタ・気づき）

- 「AIがニュース検索した“フリ”をして中身を捏造する」実例（令和8年熊本地震を平成23年と誤認）は、AIの信頼性・ツール呼び出し検証の重要性を語る具体例として使えそう
- persona_promptのデフォルト値（世界征服・パイ）を確認せず「ハルシネーションだ」と早合点しかけた顛末は、「設定ファイルは中身を見ろ」という教訓込みで動画ネタになりそう
- 「日本語の純度」と「ツール呼び出し対応」のトレードオフは、ローカルLLM選定というテーマで汎用性のある学びとして展開できそう

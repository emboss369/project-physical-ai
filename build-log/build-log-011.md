# Build Log #011 — 2026-08-11 to 2026-08-13

## 今日やったこと

* Anthropicより、見に覚えのない 73,338円 の請求。いつも22ドルはずなのに、なぜかMAXプランに切り替わっていて、連続して5回の「Auto recharge extra usage, Individual plan」が行われている。
* 8月7日(金) 20:03 に最初の引き落としMaxプランへの変更が行われている
* 8月7日(金) 21:08 に $57.23 のオートリチャージ
* 8月7日(金) 21:54 に $47.85 のオートリチャージ
* 8月7日(金) 22:09 に $46.60 のオートリチャージ
* 8月7日(金) 22:28 に $44.28 のオートリチャージ
* 8月7日(金) 22:42 に $50.72 のオートリチャージ

このように、不審なオートリチャージが短時間に繰り返された。ブラウザの履歴を確認し、この時間帯にブラウザを開いていないので、Maxプラン変更の操作もしていないのは明らか。また、「自動チャージ」もオフであるため、オートリチャージも発生するのはおかしい。明らかにシステムのバグではないだろうか。

というわけで、昨日 カード会社に相談したが、カードを止めましょうか、としか言われない。
翌日まで待ったがAnthropic社からは回答ない。安全のため、カード会社に再度連絡し、カードを止めてもらった。また、この不審な請求についてはカード会社で調査をしてもらえることになった。どのような結果になるかわからないが、なにもしないよりはマシだろう。

とりあえず、こんな怖いサービスを使うのはもう嫌なので、ChatGPTに戻ろうかな、とも思い、ChatGPTと再契約。

使ってて思うのはやっぱりChatGPTってあまり頭良くなくってちょっと話し相手にならない。そっか、ChatGPTってイマイチだよなと思ってAnthropicのClaudeに乗り換えたんだった。Claudeの力の高さに改めて気付かされる。

というわけで、Claudeが不正請求してくるため、今後はAnthropic抜きで作業を進めることにしましょう。

2026/08/11 

## Claude Codeからローカル環境へ移行した

はい、このような経緯があり、急に高額請求されるようなバグを内包したサービスはもう使いたくはありません。せっかく高性能なGPUを所有しているのですから、しっかり24時間働いてもらいましょう、ということで、ローカルLLMコーディング環境を構築していきたいと思います。

## Step 1 vLLM

vLLM（Very Large Language Model）は、大規模言語モデル（LLM）を高速で効率的に推論するためのオープンソースライブラリです。これを導入しましょう。

- 参考サイト
    - https://qiita.com/softbase/items/585ffa3ce845d4caa622


```text
Ubuntu
└── /opt/ai/
        ├── vllm/
        ├── models/
        └── logs/
```

インストール

```bash
sudo mkdir -p /opt/ai/vllm
sudo chown -R $USER:$USER /opt/ai/vllm
cd /opt/ai/vllm
# Python 3.12 でプロジェクトを初期化
uv init -p 3.12
# ディレクトリ名（vllm）から自動設定されたプロジェクト名が、インストールしようとしたパッケージ名（vllm）と重複するので名前を変えとく
sed -i 's/name = "vllm"/name = "vllm-app"/' pyproject.toml
# vLLM インストール（自動的に依存する PyTorch もインストールされます）
uv add vllm

# うまく行かず、以下の方法に切り替えた
# まず、VSCodeのターミナルを使わないようにした。
# 普通にUbuntuの端末を起動して以下のコマンドを実行

sudo chown -R hiro:hiro /opt/ai
cd /opt/ai
uv venv
source .venv/bin/activate
uv pip install vllm huggingface_hub
```

## Qwen3-Coder-14Bをローカルに配置する

```bash
cd /opt/ai
uv venv
source .venv/bin/activate
mkdir -p /opt/ai/models
mkdir -p /opt/ai/cache
mkdir -p /opt/ai/logs
mkdir /opt/ai/scripts
hf download Qwen/Qwen3.5-9B --local-dir /opt/ai/models/Qwen3.5-9B
```

## 起動テスト

```bash
vllm serve \
  /opt/ai/models/Qwen3.5-9B \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --gpu-memory-utilization 0.85 \
  --max-model-len 16384
```

おっとこれは動作しません。ダウンロードしたモデルは量子化前でした。
AWQ 4bit量子化済みで、vLLM対応のモデルが。ありました。

```bash
hf download \
    QuantTrio/Qwen3.5-9B-AWQ \
    --local-dir /opt/ai/models/Qwen3.5-9B-AWQ
```


実行してみましょう。

```bash
vllm serve \
    /opt/ai/models/Qwen3.5-9B-AWQ \
    --quantization awq \
    --host 0.0.0.0 \
    --port 8000 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 16384
```

これもうまく行かない。エラーで起動しません。

次はQwen2.5-Coder-14Bを試してみる。

```bash
hf download \
  Qwen/Qwen2.5-Coder-14B-Instruct-AWQ \
  --local-dir /opt/ai/models/Qwen2.5-Coder-14B-Instruct-AWQ
```

ようやく動いた構成です。

```bash
VLLM_USE_FLASHINFER_SAMPLER=0 vllm serve /opt/ai/models/Qwen2.5-Coder-14B-Instruct-AWQ \
  --served-model-name qwen \
  --quantization awq \
  --max-model-len 8192 \
  --cpu-offload-gb 4 \
  --kv-cache-memory 1610612736 \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json \
  --enforce-eager \
  --attention-backend FLASH_ATTN
  ```


## トラブルシューティングの経緯（問題と解決策）

### 第1の障害：FlashInfer (Sampler) の実行エラー

原因: vLLM v0.27.0 では、サンプリング処理にデフォルトで FlashInfer が使われますが、CUDAドライバー/PyTorchとのバージョンミスマッチ（SM 12.x requires CUDA >= 12.9 等）によりカーネルコンパイルでエラーが発生していました。

解決策: VLLM_USE_FLASHINFER_SAMPLER=0 を環境変数として付与し、旧来のサンプラーへフォールバックさせました。

### 第2の障害：KVキャッシュのメモリ不足

原因: 最大コンテキスト長 max-model-len 8192 を処理するには最低 1.5 GiB のKVキャッシュ領域が必要でしたが、手動指定値（1546901812 bytes ≒ 1.44 GiB）がわずかに不足していました。

解決策: --kv-cache-memory を 1610612736 (1.5 GiB) に増やしたことで、必要メモリ条件をクリアしました。

## パラメータ完全解説

実行したコマンドの各要素の役割と、今回の環境（VRAM領域の節約・CPUオフロード等）における意味は以下の通りです。

| パラメータ / 設定項目 | 解説・今回の役割 |
| --- | --- |
| `VLLM_USE_FLASHINFER_SAMPLER=0` | **[環境変数]** FlashInferによるサンプリングを無効化。GPU/CUDA互換性エラーを回避するための必須フラグです。 |
| `vllm serve /opt/ai/models/...` | ロードするモデルのローカルパスを指定してAPIサーバーを起動します。 |
| `--served-model-name qwen` | API呼び出し時（OpenAI互換エンドポイント等）に指定するモデル表示名。 |
| `--quantization awq` | AWQ（Activation-aware Weight Quantization）量子化モデルとしてロードし、VRAM消費量を大幅に削減します。 |
| `--max-model-len 8192` | モデルが一度に処理できる最大トークン数（入力＋出力の合計）。 |
| `--cpu-offload-gb 4` | モデル重みの一部（4GB分）をシステムRAM（CPU）へ退避させ、VRAM不足（OOM）を防ぎます。 |
| `--kv-cache-memory 1610612736` | KVキャッシュ（会話文脈の保持領域）のサイズをバイト単位で直接指定（約1.5 GiB）。`max-model-len 8192` を動かすギリギリのラインに最適化されています。 |
| `--enable-auto-tool-choice` | 関数呼び出し（Tool Calling / Function Calling）の自動判定機能を有効化します。 |
| `--tool-call-parser llama3_json` | ツール呼び出しの出力フォーマットを解析するパーサーを指定します。 |
| `--enforce-eager` | CUDA Graphsの事前キャプチャやコンパイルをスキップ（イガー実行）し、起動時のVRAMオーバヘッドと準備時間を削減します。 |
| `--attention-backend FLASH_ATTN` | アテンション計算のバックエンドに FlashAttention-2 を使用し、高速化を図ります。 |

これで安定した推論サーバーとして動作する状態になりました！

次回からこの安定した設定をコマンド一発起動する方法


```bash
cat << 'EOF' > /opt/ai/start_vllm.sh
#!/bin/bash

# 仮想環境のアクティベート（未有効化の場合に対応）
if [ -d "/opt/ai/.venv" ]; then
    source /opt/ai/.venv/bin/activate
fi

# 環境変数の設定
export VLLM_USE_FLASHINFER_SAMPLER=0

# vLLM 起動コマンド
vllm serve /opt/ai/models/Qwen2.5-Coder-14B-Instruct-AWQ \
  --served-model-name qwen \
  --quantization awq \
  --max-model-len 8192 \
  --cpu-offload-gb 4 \
  --kv-cache-memory 1610612736 \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json \
  --enforce-eager \
  --attention-backend FLASH_ATTN
EOF
```

```bash
chmod +x /opt/ai/start_vllm.sh
```


# vLLMは動くようになった。しかし、OpenCodeでうまく動かない

さてvLLMが動くようになったのでOpenCodeに設定して使ってみると、無限に問い合わせを行って、ずーっと同じ出力を繰り返して止まりません。

Geminiに調べてもらったところ、どうも「OpenCode + vLLM + Qwen シリーズ（Qwen2.5/Qwen3）の組み合わせで、ツール呼び出し（Tool Call）のパース失敗や自問自答の無限ループ（Build / Compaction）が発生する」 という事象は、非常に多くのユーザーが直面している既知の課題のようです。

あーあ、なんだかんだで1日溶かしてしまいました。この組み合わせは諦めてllamaで動かしましょう。


# vLLM を諦め、llamaを使っている記事のとおりに進めることとする。

Zennに同じく16GBのVRAMでローカルLLMを構築している記事を見つけた。

https://zenn.dev/syoyo/articles/78fd97b3630b9b

このZennの記事によると、モデルには

https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF

を使っているとのこと。上記URLに、この詳しいセットアップ方法は以下に記載があるとのことだったのでそちらを参照する。

https://unsloth.ai/docs/models/tutorials/qwen3-coder-how-to-run-locally

これを見ながら、セットアップを進める。具体的には以下の手順で、セットアップできた。

## 検証環境

以下に、今回の検証環境について記載します。

### 検証環境スペック

**ハードウェア**

* **CPU:** AMD Ryzen 7 9800X3D
* **GPU:** NVIDIA GeForce RTX 5060 Ti (VRAM 16GB)
* **RAM:** 32GB (DDR5-5600)
* **Storage:** 1TB NVMe Gen4 SSD
* **OS:** Windows 11 Pro (WSL2 / Ubuntu)

---

### ソフトウェア・推論構成

| 項目 | 設定・使用ツール |
| --- | --- |
| **推論エンジン** | `llama.cpp` (CUDA対応 / 静的ビルド) |
| **使用モデル** | `Qwen3-Coder-30B-A3B-Instruct-GGUF` (量子化: `Q4_K_M`) |
| **開発クライアント** | `OpenCode` / `VS Code` + `Continue` 拡張機能 |

---

### モデル実行パラメータ (`llama-server`)

| パラメータ | 設定値 | 目的・効果 |
| --- | --- | --- |
| **コンテキスト長 (`-c`)** | `16384` (16k) | 長文コード解析・長文プロンプト対応 |
| **GPUオフロード (`-ngl`)** | `40` | 30Bモデルを VRAM 16GB 内に収める調整 |
| **Flash Attention (`-fa`)** | `on` | 推論速度向上＆VRAM消費量の削減 |
| **KVキャッシュ量子化** | `q8_0` (8-bit) | コンテキスト拡張時の VRAM 圧迫を約 50% 削減 |

---

> **アドバイス**
> VRAM 16GB 環境で 30B クラスのコード生成モデルを実用的な速度で動かすにあたり、**「GPUオフロード層数の調整（`-ngl 40`）」** と **「Flash Attention ＋ 8-bit KVキャッシュによるVRAM節約」** が構成のキーポイントになります。

## llamaコードの取得

では、この構成で使えるようにセットアップしていきましょう。

llama.cpp を GPU（CUDA）対応で動作させるため、必要なツール（git, cmake, build-essential）をインストールし、ソースコードをダウンロードします。

ターミナルを開き、以下のコマンドを順番に実行してください。


```bash
sudo apt update && sudo apt install -y git build-essential cmake
cd /opt/ai/

sudo git clone https://github.com/ggml-org/llama.cpp /opt/ai/llama.cpp
```

## 静的ライブラリ（BUILD_SHARED_LIBS=OFF）および CUDA 有効で設定生成


```bash
sudo CUDACXX=/usr/local/cuda/bin/nvcc PATH=$PATH:/usr/local/cuda/bin \
  cmake /opt/ai/llama.cpp -B /opt/ai/llama.cpp/build \
    -DBUILD_SHARED_LIBS=OFF \
    -DGGML_CUDA=ON
```

## 並列コンパイルの実行

```bash
sudo cmake --build /opt/ai/llama.cpp/build --config Release -j$(nproc) --target llama-cli llama-server llama-gguf-split
```
## バイナリのコピーと確認
ビルドされた実行ファイルを /opt/ai/llama.cpp/ の直下にコピーします。

```bash
sudo cp /opt/ai/llama.cpp/build/bin/llama-* /opt/ai/llama.cpp/
```

## モデルファイルの取得

```bash
hf download \
unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf \
--local-dir /opt/ai/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M
```

次のマンドは、Unsloth が推奨する **Qwen3-Coder-30B 向けローカル動作最適化構成**（VRAM節約・高速化・サンプリング調整）を反映した `llama-server` の実行指定です。

| パラメータ | 指定値 | 主な役割・効果 |
| --- | --- | --- |
| `$LLAMA_SERVER` | パス変数 | ビルド済み `llama-server` 実行バイナリを呼び出し |
| `-m "$MODEL_PATH"` | GGUFパス | 読み込むモデルファイル（`Qwen3-Coder-30B...gguf`）の指定 |
| `--host 0.0.0.0` | IP | 外部機器やローカルホストからの全接続を受け付け |
| `--port 8000` | ポート | OpenAI 互換 API サーバーとしての受付ポート指定 |
| **`-ngl 40`** | レイヤー数 | 40 レイヤー分を GPU（VRAM）へオフロードし、溢れた分を CPU/RAM へ退避 |
| **`-fa on`** | `on` | **Flash Attention** を有効化（アテンション計算の VRAM 消費削減と計算高速化） |
| **`-c 16384`** | トークン数 | コンテキストウィンドウサイズを 16k トークンに設定 |
| **`--cache-type-k/v`** | `q8_0` | KV キャッシュを 8-bit 量子化し、コンテキスト領域の VRAM 消費を約半分に抑制 |
| `--temp` | `0.7` | 生成のランダム性を調整（コード生成に適した安定度） |
| `--min-p` | `0.01` | 確率が極端に低いトークンを除外するフィルタリング |
| `--top-p` | `0.8` | 累積確率上位 80% のトークン群から選択 |
| `--alias` | `qwen` | クライアント（OpenCode 等）から呼び出す際のモデル識別名 |

---

### 詳細解説

**1. ネットワーク・サーバー基盤**

* **`--host 0.0.0.0` / `--port 8000**`
`0.0.0.0` を指定することで、同一マシン上の `localhost` だけでなくコンテナや別端末からのアクセスを許可します。OpenAI 互換のエンドポイント (`http://localhost:8000/v1`) として待機します。
* **`--alias qwen`**
API リクエストで `"model": "qwen"` と指定された際に、ロード中の Qwen3-Coder を割り当てるエイリアス名です。

**2. VRAM と計算処理の最適化（16GB VRAM 環境向け）**

* **`-ngl 40` (`--n-gpu-layers 40`)**
Qwen3-Coder-30B の全レイヤー（約 48〜60 レイヤー前後）のうち、40 レイヤーを VRAM に載せ、残りをシステム RAM (CPU) に分散します。全層オフロード（`-ngl 99`）による 17.5GB 以上の VRAM 超過（Out of Memory）を防ぎます。
* **`-fa on` (`--flash-attn on`)**
Unsloth のチュートリアルにおいて最も推奨される設定の一つです。入力長が伸びた際のアテンション行列のメモリ保持量を物理的に削減し、推論の処理速度（tokens/sec）を向上させます。

**3. コンテキストと KV キャッシュの量子化**

* **`-c 16384` (`--ctx-size 16384`)**
一度に処理できる入力＋出力の最大トークン数を 16,384 に拡張します。コードベース全体の解析や長文プロンプトの読み込みに対応させます。
* **`--cache-type-k q8_0` / `--cache-type-v q8_0**`
通常 FP16 で保持される Key/Value キャッシュを 8-bit（Q8_0）に圧縮して保存します。精度落としを最小限に留めつつ、コンテキスト拡張（16k）に伴う VRAM 圧迫を約 50% カットします。

**4. サンプリングパラメータ（Qwen 推薦値）**

* **`--temp 0.7` / `--top-p 0.8` / `--min-p 0.01**`
Qwen チームおよび Unsloth が提示するコーディングタスク向けのサンプリング設定です。高い決定性（不正確なコードを出力させない）を保ちつつ、適切な柔軟性を持たせることで構文エラーやロジック崩壊を防ぎます。


```bash
sudo cat << 'EOF' > /opt/ai/start_llama_server.sh
#!/bin/bash

LLAMA_SERVER="/opt/ai/llama.cpp/llama-server"
MODEL_PATH="/opt/ai/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"

$LLAMA_SERVER \
  -m "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8000 \
  -ngl 40 \
  -fa on \
  -c 16384 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --temp 0.7 \
  --min-p 0.01 \
  --top-p 0.8 \
  --alias qwen
EOF
```

スクリプトファイルに実行権限を与えます。

```bash
sudo chmod +x /opt/ai/start_llama_server.sh
```

それでは実行してみましょう。

```bash
/opt/ai/start_llama_server.sh
```

以下のような出力が確認できれば起動成功です。

```log
$ /opt/ai/start_llama_server.sh
0.00.152.653 I cmn  common_param: common_params_print_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
0.00.222.532 W srv  llama_server: -----------------
0.00.222.534 W srv  llama_server: CORS is set to allow all origins ('*') and no API key is set
0.00.222.535 W srv  llama_server: this can be a security risk (cross-origin attacks)
0.00.222.535 W srv  llama_server: more info: https://github.com/ggml-org/llama.cpp/pull/25655
0.00.222.535 W srv  llama_server: -----------------
0.00.223.692 I srv    load_model: loading model '/opt/ai/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf'
0.00.381.337 W common_fit_params: failed to fit params to free device memory: n_gpu_layers already set by user to 40, abort
0.00.451.351 W load: control-looking token: 128247 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.01.661.200 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 16384, kv_unified = 'true'
0.01.662.734 I srv  llama_server: model loaded
0.01.662.736 I srv  llama_server: listening on http://0.0.0.0:8000
```

次に、OpenCodeの設定ファイルを作成します。

```bash
mkdir -p ~/.config/opencode
```
```bash
cat << 'EOF' > ~/.config/opencode/opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "llama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "llama-server",
      "options": {
        "baseURL": "http://localhost:8000/v1"
      },
      "models": {
        "qwen": {
          "name": "Qwen3-Coder-30B",
          "limit": {
            "context": 16384,
            "output": 4096
          }
        }
      }
    }
  },
  "model": "llama/qwen",
  "compaction": {
    "auto": false
  }
}
EOF
```


## 試してみる

プロジェクトのフォルダでOpenCodeを起動します。

```bash
opencode
```

試しに関数を作ってもらいましょう。

```text
Pythonで引数のリストから素数だけを抽出する関数を作成してください。
def extract_primes(numbers):
    def is_prime(n):
        if n < 2:
            return False
        if n == 2:
            return True
        if n % 2 == 0:
            return False
        for i in range(3, int(n**0.5) + 1, 2):
            if n % i == 0:
                return False
        return True
    
    return [n for n in numbers if is_prime(n)]
▣  Build · Qwen3-Coder-30B · 9.8s
```

成功です。16kコンテキストへの拡張および Flash Attention 適用を含め、理想的な状態で稼働しています！
しばらくOpenCodeを使ってみましょう。


## VS Code に Continue 拡張機能を導入し、ローカルの llama-server に接続して使う

VS Code に Continue 拡張機能を導入し、稼働中の `llama-server` に接続する手順です。

---

### ステップ 1：VS Code に Continue 拡張機能をインストール

1. VS Code を開き、左サイドバーの **拡張機能アイコン**（`Ctrl+Shift+X` / `Cmd+Shift+X`）をクリックします。
2. 検索窓に **`Continue`** と入力します。
3. **`Continue - Codegen`**（作者: Continue）を選択し、**[インストール]** をクリックします。

※ https://marketplace.visualstudio.com/items?itemName=Continue.continue 

---

### ステップ 2：Continue の設定ファイル (`config.yaml`) を開く

1. インストール完了後、左サイドバーに追加された **Continue アイコン** をクリックします。
2. パネル右の ** Main Config ** をクリックします。
3. Configsメニューで ** 歯車アイコン *** をクリックします。
4. Main Configの ** 歯車アイコン *** をクリックします。
3. 設定ファイル `~/.continue/config.yaml` がエディタで開きます。

---

### ステップ 3：`config.yaml` にローカル `llama-server` を追加

`"models"` 配下に、以下のように `openai` プロバイダー経由の設定を追記します。

```yaml
  - name: Local Qwen3-Coder 30B
    provider: openai
    model: qwen
    apiBase: http://localhost:8000/v1
    apiKey: x
    roles:
      - chat
      - edit
      - apply
      - autocomplete
```

---

### ステップ 4：動作確認と基本的な使い方

`start_llama_server.sh` が起動している状態で、以下の機能をテストします。

* **チャットパネル (`Ctrl+L` / `Cmd+L`)**
* コードを選択して `Ctrl+L` を押すと、Continue チャット画面にコードが読み込まれます。
* 「この処理を解説して」「型ヒントを追加して」などの指示を送ります。


* **インライン編集 (`Ctrl+I` / `Cmd+I`)**
* コードエディタ上でリファクタリングしたい範囲を選択し、`Ctrl+I` を押します。
* プロンプト入力欄が表示されるため、「エラーハンドリングを追加して」などと入力すると、差分（Diff）がインライン表示されます。

### 💡 今回の教訓・学びまとめ

1. **クラウドAI依存の脆弱性とローカル環境の価値**
SaaS側の予期せぬ料金トラブルや仕様変更に対して、手元に「自前で動く高性能なローカルLLM環境」を持っておくことは最高の保険になる。RTX 5060 Ti（VRAM 16GB）クラスのGPUがあれば、開発の大部分を自給自足できる。
2. **コーディングエージェント用途における推論エンジンの選定**
vLLM は爆速推論に優れるものの、OpenCode 等の CLI エージェントツールと組み合わせた際、モデルやパーサー（`llama3_json` 等）の相性問題でツール呼び出し（Tool Call）の無限ループや失敗が発生しやすい。一方、`llama.cpp` (`llama-server`) は OpenAI 互換 API や JSON 構造化出力の安定性が非常に高く、エージェント環境のバックエンドとして極めて扱いやすい。
3. **VRAM 16GB で 30B モデルを実用化する「VRAM節約3種の神器」**
16GB VRAM という制約下で 30B クラス（Qwen3-Coder-30B）を長文コンテキスト（16k）で動かすための鍵は以下の3点：
* **層指定オフロード (`-ngl 40`)**: 全層ではなくVRAM容量に合わせて層数を手動制御する。
* **Flash Attention (`-fa on`)**: アテンション計算のメモリ消費を劇的に抑え、処理速度を向上。
* **8-bit KVキャッシュ (`--cache-type-k/v q8_0`)**: 文脈保持領域（KVキャッシュ）の VRAM 消費を約半分に削る。


4. **コンテキスト枠は「サーバー」と「クライアント」の双方で揃える**
`llama-server` 側で `-c 16384` に拡張しても、OpenCode 側の `opencode.json` や Continue 側の `config.yaml` で `context: 16384` を指定しないとトークン切れエラー（8192制限等）が発生する。両者の設定値を正しく一致させることがトラブル回避の基本。
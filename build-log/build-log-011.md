# Build Log #011 — 2026-08-11

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

とりあえず、こんな怖いサービスを使うのはもう嫌なので、ChatGPTに戻ろうかな、とも思いChatGPTと再契約。

使ってて思うのはやっぱりChatGPTってあまり頭良くなくって、話し相手にならない。そっか、生成AIってこんな感じでいまいちな返答しかしなかったよなと、Anthropicの能力の高さに改めて気付かされる。

というわけで、今後はnthropic抜きで作業を進めることにしましょう。

## Claude Codeからローカル環境へ移行したい

はい、このような経緯があり、急に高額請求されるようなバグを内包したサービスはもう使いたくはありません。せっかく高性能なGPUを所有しているのですから、しっかり24時間働いてもらいましょう、ということで、ローカルLLMコーディング環境を構築していきたいと思います。

## Step 1 vLLM

vLLM（Very Large Language Model）は、大規模言語モデル（LLM）を高速で効率的に推論するためのオープンソースライブラリです。これを導入しましょう。

- 参考サイト
    - https://qiita.com/softbase/items/585ffa3ce845d4caa622


```text
Ubuntu
│
├── systemd
│      └── vllm.service
│
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

まずは保守的に

```sh
export VLLM_USE_FLASHINFER_SAMPLER=0

vllm serve \
  /opt/ai/models/Qwen2.5-Coder-14B-Instruct-AWQ \
  --served-model-name qwen \
  --quantization awq \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.95 \
  --enforce-eager \
  --attention-backend FLASH_ATTN
```

vllm serve \
  /opt/ai/models/Qwen2.5-Coder-14B-Instruct-AWQ \
  --served-model-name qwen \
  --quantization awq \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.95 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --attention-backend FLASH_ATTN


hf download \
  nicklas373/Qwen3.5-9B-AWQ \
  --local-dir /opt/ai/models/Qwen3.5-9B-AWQ
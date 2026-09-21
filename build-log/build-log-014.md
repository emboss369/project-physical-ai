# Build Log #014 — 2026-09-16

## 今日やったこと

#011 で立てたローカル LLM 環境（`llama.cpp` + `Qwen3-Coder-30B-A3B-Instruct` Q4_K_M）の `llama-server` 起動スクリプトを見直し、安定させた。

<!-- TODO: 何が不安定だったかを1〜2行で。例：長い入力で OOM で落ちる / 応答が途中で途切れる / 速度が不安定 など -->

変更の中心は **「層単位の GPU オフロード」から「MoE のエキスパート重みだけを CPU に逃がす」方式への切り替え。** Attention を含む全層を GPU に置いたまま、VRAM に収まらない分だけをエキスパート単位で CPU RAM に残す。

**今日の結論を一行で：MoE モデルは `-ngl` で層を削るより、`--n-cpu-moe` でエキスパートを CPU に逃がすほうが VRAM の使い方として筋がいい。**

---

### 1. 変更後の起動スクリプト

```bash
$ cat /opt/ai/start_llama_server.sh
#!/bin/bash

LLAMA_SERVER="/opt/ai/llama.cpp/llama-server"
MODEL_PATH="/opt/ai/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"

$LLAMA_SERVER \
  -m "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8000 \
  -ngl 999 \
  --n-cpu-moe 14 \
  -fa on \
  -c 49152 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --no-mmap \
  --temp 0.7 \
  --min-p 0.01 \
  --top-p 0.8 \
  --alias qwen
```

### 2. 変更点

| パラメータ | #011 | 変更前（今日の朝） | 今日 | 狙い |
|---|---|---|---|---|
| `-ngl` | `40` | <!-- TODO --> | `999` | 全層を GPU 対象にする（Attention 層を含む全レイヤーを GPU に優先配置） |
| `--n-cpu-moe` | なし | なし | `14`（初期値 `20` から調整） | エキスパート重みの一部（14層分）だけを CPU RAM に残す |
| `--cache-type-k/v` | `q8_0` | `q4_0` | `q8_0` | VRAM に余裕ができた分、精度劣化の少ない q8_0 に戻す |
| `-c` | `16384` | <!-- TODO --> | `49152` | 48k コンテキスト |
| `--no-mmap` | なし | なし | あり | CPU 側常駐のエキスパート分を含め、システム RAM を無駄なく使う |

<!-- TODO: 「変更前」列を埋める。q4_0 にしたのはいつ・なぜか（-c を伸ばすためか）も一言あると後で読み返して分かる -->

### 3. なぜ `-ngl` を削るのをやめたのか

`Qwen3-Coder-30B-A3B` は MoE（Mixture of Experts）モデルで、名前の **30B が総パラメータ、A3B が1トークンあたり実際に動く（Active）3B** を指す。重みの大半はエキスパート（FFN）で、各トークンで使われるのはそのうちの一部だけ。

#011 の `-ngl 40` は「48層のうち40層を GPU、残り8層を丸ごと CPU」という分け方だった。丸ごと、なので**毎トークン必ず通る Attention まで CPU に落ちる。** ここが遅さの原因になる。

`-ngl 999 --n-cpu-moe 14` は「全層の Attention・norm 等は GPU、先頭14層分のエキスパート重みだけ CPU」という分け方。CPU に残るのは**スパースにしか使われないエキスパート**なので、CPU を通る計算量が同じ VRAM 節約量でも小さくて済む——というのが `--n-cpu-moe` の設計意図（llama.cpp の 2025年8月頃に入ったオプション）。

### 4. `--n-cpu-moe` の値の決め方

初期値は `20` で起動し、`nvidia-smi` の VRAM 使用量を見ながら詰めて `14` に落ち着いた。値が小さいほど GPU に載るエキスパートが増えて速くなるが、VRAM を食う。

<!-- TODO: 実測値。20 のときの VRAM 使用量 / 14 のときの VRAM 使用量 / 空き。可能なら tok/s（prompt eval / eval）も -->

```text
$ nvidia-smi
（TODO: 貼る）
```

### 5. KV キャッシュを q8_0 に戻す

q4_0 の KV キャッシュは VRAM を節約できるが、精度劣化がある。エキスパートを CPU に逃がしたことで VRAM に余裕ができたので、#011 の構成と同じ q8_0 に戻した。「問題ないはず」の段階で、精度差を自分で比較したわけではない。

### 6. `--no-mmap`

既定では GGUF を mmap で読み、必要なページを OS に任せて RAM に載せる。`--no-mmap` にすると起動時に全部を RAM に読み込む。CPU 側に常駐させるエキスパート分を含めてシステム RAM を無駄なく使えて、速度面のデメリットはほぼ無い**との報告がある**（自分では未計測）。代わりに起動は遅くなる。

### 7. 起動前に Ollama を降ろす

相棒AI（#013）と今日の構成は、VRAM 16GB に両方は載らない。同居は最初から考えない。

問題は**同時起動ではなく「終わったつもりで残っている」ケース。** Open-LLM-VTuber を `Ctrl+C` で止めても、`keep_alive: -1` のせいで Ollama は `qwen3-vl-8k` の 6.5GB を握ったまま（#013 節30）。その状態で `start_llama_server.sh` を叩くと、`-ngl 999` は「載るだけ載せる」ので OOM で落ちるか、**エラーにならずに静かに遅くなる**。「安定させたはずなのに遅い」と思ったら Ollama が残っていた、という事故が起こりうる。

#013 の学び「エラーにならない失敗こそ自動で見張る」をそのまま適用して、スクリプトの先頭で `ollama ps` を見て、残っていれば `ollama stop` するようにした。

```bash
# 相棒AI（Open-LLM-VTuber）側の Ollama は keep_alive: -1 で、アプリを終了しても
# モデルを VRAM に握り続ける（Build Log #013 節30）。残っていると -ngl 999 が
# 静かに CPU に溢れるので、起動前に必ず降ろす。
if command -v ollama >/dev/null 2>&1; then
  ollama ps 2>/dev/null | awk 'NR>1 && NF {print $1}' | while read -r model; do
    echo "[start_llama_server] Ollama が ${model} を保持中。ollama stop します"
    ollama stop "$model"
  done
fi
```

逆方向（llama-server が動いたまま相棒AIを起動する）は `start-midori.sh` 側に同じ仕込みがまだ無い。次回。

---

## 今日の学び

- **MoE モデルの VRAM 調整は `-ngl` ではなく `--n-cpu-moe`。** 層単位で切ると Attention まで CPU に落ちる。エキスパート単位で切れば、毎トークン通る部分は GPU に残せる
- **「30B-A3B」の A3B を読めていなかった。** #011 では 30B を dense モデルと同じ感覚で扱って `-ngl 40` にしていた。名前にヒントがあった
- **VRAM 16GB は「どちらか一方」。** 相棒AIとコーディング用 LLM は同居しない。同居しないなら、切り替え時に前のプロセスが残っていないかをスクリプトで見張る
- **VRAM が空いたら、削った精度を戻す。** KV キャッシュの q4_0 は「仕方なく」の設定だった。余裕ができたときに元に戻す判断をセットにしておく

## まだ測っていないこと

1. **`--n-cpu-moe 14` での実測 VRAM と tok/s。** 「安定した」の根拠を数字で残す。#011 の `-ngl 40` 時と比較する
2. **KV キャッシュ q4_0 と q8_0 の差が体感できるか。** コーディング用途で違いが出るのか、自分で見ていない
3. **`--no-mmap` の起動時間と RAM 常駐量。** `free -h` で確認する
4. **クライアント側のコンテキスト設定。** #011 の教訓どおり、`-c 49152` にした分を OpenCode / Continue 側の設定にも揃える必要がある。<!-- TODO: 揃えたか -->
5. **逆方向の仕込み。** `start-midori.sh` 側で、`llama-server` が動いていたら止める（または警告する）処理。今日は llama-server 側にしか入れていない

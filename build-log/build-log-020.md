# Build Log #020 — 2026-10-08

## 今日やったこと

#013 で、佐倉みどりの声を Irodori-TTS 自身に作らせて固定した（caption「ボーイッシュな女性の声。さっぱりとした話し方。」、seed `1006`）。今日はその声を作り直した。**方向は「落ち着いた10代女性の声。やわらかく、少し近い距離感で、優しく話す」。**

一日の流れ：

1. この方向の caption を 5 種類用意し、それぞれ seed を 4 種類変えて、20 パターンを生成した
2. 聴き比べて `D_2202` を採用した
3. リファレンス音声 `sakura_midori.wav` を差し替え、出どころの README を更新した
4. `voice: "sakura_midori"` で 1 本合成して、サーバーが新しいリファレンスで動くか確かめた

**今日の結論を一行で：声の差し替えは wav を 1 つ上書きするだけで済んだ。#013 でリポジトリを正にしてシンボリックリンクで参照する形にしておいたので、サーバー側の設定は何も変えなくてよかった。**

---

### 1. サーバーの状態と、いまの置き場所を確かめる

```bash
curl -s -m 5 http://localhost:8088/health; echo
ls ~/development/Irodori-TTS-Server/
ls ~/Develop/project-physical-ai/ConversationalAI/voice/
```

```text
{"status":"ok","model":{"id":"irodori-tts","hf_checkpoint":"Aratako/Irodori-TTS-v4-Small", ... },
 "runtime":{ ... "loaded":true, ... "max_concurrent_synthesis":1, ... },
 "voices":{"dir":"voices","dir_exists":true,"files":1},
 "defaults":{"response_format":"wav","chunking_enabled":true,"chunk_min_chars":80, ... }}
```

- モデルは `Aratako/Irodori-TTS-v4-Small`。#013 と同じ
- `max_concurrent_synthesis` が 1 なので、合成は 1 本ずつ順番に投げる

### 2. caption 5 種 × seed 4 種 = 20 パターンを生成する

caption は次の 5 種類にした。A はこの方向の元の文をそのまま使い、B〜E はそこから少しずつ寄せ方を変えた。

| ID | caption | ねらい |
|---|---|---|
| **A** | 落ち着いた10代女性の声。やわらかく、少し近い距離感で、優しく話してください。 | 元の文そのまま |
| **B** | 落ち着いた10代女性の声。穏やかで透明感があり、ゆっくりと丁寧に話す。 | 透明感・ゆっくり |
| **C** | 10代後半の女性の声。少し低めで落ち着いたトーン。親しみやすく、隣で話しかけるような距離感。 | 少し低め・隣にいる距離 |
| **D** | やわらかい10代女性の声。小さめの声量で、そっと寄り添うように優しく話す。 | 小さめの声量・寄り添う |
| **E** | 落ち着いた10代女性の声。知的で穏やか、少しだけ明るさのある話し方。 | 知的・少し明るい |

seed はどの caption でも `2101 / 2202 / 2303 / 2404` にそろえた。こうすると、同じ seed のファイル同士で caption の違いだけを聴き比べられる。セリフは #013 の `cand6` と同じにして、旧い声とも比べられるようにした。

ファイル名は `{ID}_{seed}.wav`。実際に使われた seed（レスポンスヘッダ `X-Irodori-Seed`）を `index.tsv` に書き出した。生成先は Claude Code の一時フォルダ（以下 `$D`）。

```bash
D=/tmp/claude-1000/-home-hiro-Develop-project-physical-ai/5c6466ee-4cb0-47b1-af79-2796ed92209f/scratchpad/voice2
mkdir -p $D && cd $D
cat > captions.txt <<'EOF'
A	落ち着いた10代女性の声。やわらかく、少し近い距離感で、優しく話してください。
B	落ち着いた10代女性の声。穏やかで透明感があり、ゆっくりと丁寧に話す。
C	10代後半の女性の声。少し低めで落ち着いたトーン。親しみやすく、隣で話しかけるような距離感。
D	やわらかい10代女性の声。小さめの声量で、そっと寄り添うように優しく話す。
E	落ち着いた10代女性の声。知的で穏やか、少しだけ明るさのある話し方。
EOF
TEXT="ドクター、今日もSO-101の実験、見てるよ。黄色いブロック、ちょっとずれてるね。次はうまくいくと思う。"
echo -e "file\tcaption_id\tseed\tcaption" > index.tsv
while IFS=$'\t' read -r id cap; do
  for seed in 2101 2202 2303 2404; do
    f="${id}_${seed}.wav"
    body=$(jq -n --arg t "$TEXT" --arg c "$cap" --argjson s $seed '{model:"irodori-tts",input:$t,voice:"none",response_format:"wav",caption:$c,seed:$s}')
    used=$(curl -s -D - -o "$f" -X POST http://localhost:8088/v1/audio/speech -H "Content-Type: application/json" -d "$body" | grep -i x-irodori-seed | tr -d '\r' | awk '{print $2}')
    echo -e "$f\t$id\t${used:-$seed}\t$cap" >> index.tsv
    echo "$f done (seed=$used)"
  done
done < captions.txt
ls -la *.wav | awk '{print $5, $9}'
```

- JSON は `jq -n --arg` で組み立てた。caption を手でエスケープしないため（QIITA.md のペイロード作成と同じ考え方）
- 20 本とも、指定した seed がそのまま `X-Irodori-Seed` に返ってきた

結果のファイルサイズ（バイト）：

| ID | サイズ | 長さ（48kHz / 16bit / mono で換算） |
|---|---|---|
| A | 1,090,604 | 約 11.4 秒 |
| B | 1,225,004 | 約 12.8 秒 |
| C | 1,071,404 | 約 11.2 秒 |
| D | 1,071,404 | 約 11.2 秒 |
| E | 1,033,004 | 約 10.8 秒 |

### 3. seed 違いで同じファイルになっていないか確かめる

**同じ caption の 4 本は、seed が違ってもファイルサイズが 1 バイトも違わなかった。** seed が効かずに同じ音声が 4 回出ただけではないかと疑ったので、中身を比べた。

```bash
cd $D && md5sum *.wav | sort | awk '{print $1}' | uniq -c | awk '$1>1'
echo "unique: $(md5sum *.wav | awk '{print $1}' | sort -u | wc -l)/20"
```

```text
unique: 20/20
```

- 20 本すべて中身が違った。seed は効いている
- **長さは seed では変わらず、caption ごとに決まっていた。** 今回の 20 本ではそうだった、というところまでしか言えない。B の「ゆっくりと」が長さに効いているように見えるが、これも 1 回の観察
- 長さがセリフと caption だけで決まり、seed は声質や抑揚のほうを変えている、という見方はできる。ただし Irodori の中身は読んでいないので、これは推測

### 4. 聴き比べる

```bash
cd $D
for f in *.wav; do echo "▶ $f"; aplay -q "$f"; done
```

聴き比べて **`D_2202` を採用した。**

| 採用した声 | 値 |
|---|---|
| caption | `やわらかい10代女性の声。小さめの声量で、そっと寄り添うように優しく話す。` |
| seed | `2202` |
| 形式 | WAV / 16bit / mono / 48kHz / 約 11.2 秒 |

### 5. リファレンス音声を差し替える

#013 で、Irodori-TTS-Server の `voices/sakura_midori.wav` は、リポジトリの `ConversationalAI/voice/sakura_midori.wav` へのシンボリックリンクにしてある。**なので、リポジトリ側を上書きするだけでサーバーにも反映される。**

旧い声（cand6）は、git の履歴（commit `b1f82f6`）に残っている。caption と seed `1006` から作り直すこともできる。なので上書きした。

```bash
cd ~/Develop/project-physical-ai/ConversationalAI/voice
cat README.md
git log --oneline -- sakura_midori.wav
ls -la ~/development/Irodori-TTS-Server/voices/
file sakura_midori.wav
```

```text
b1f82f6 Build Log #012・#013 を追加、相棒AIに目と声を付ける
lrwxrwxrwx 1 hiro hiro 79  9月  5 12:07 sakura_midori.wav -> /home/hiro/Develop/project-physical-ai/ConversationalAI/voice/sakura_midori.wav
sakura_midori.wav: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 48000 Hz
```

```bash
cp $D/D_2202.wav ~/Develop/project-physical-ai/ConversationalAI/voice/sakura_midori.wav
md5sum ~/Develop/project-physical-ai/ConversationalAI/voice/sakura_midori.wav \
       $D/D_2202.wav \
       ~/development/Irodori-TTS-Server/voices/sakura_midori.wav
```

```text
9766ec54af7bc4e7b7748130f83958d0  .../ConversationalAI/voice/sakura_midori.wav
9766ec54af7bc4e7b7748130f83958d0  .../scratchpad/voice2/D_2202.wav
9766ec54af7bc4e7b7748130f83958d0  .../Irodori-TTS-Server/voices/sakura_midori.wav
```

3 つとも同じ md5 になった。サーバー側のリンク越しに見ても、新しい wav になっている。

### 6. 出どころの README を更新する

`ConversationalAI/voice/README.md` の caption・seed・長さ・再現用の curl を新しい値に書き換えた。あわせて「声の履歴」の表を足し、v1（#013）と v2（今回）を並べた。**実在の誰の声もクローンしていない**ことは v2 でも変わらない。

```bash
cd ~/Develop/project-physical-ai/ConversationalAI/voice && python3 - <<'EOF'
p='README.md'
s=open(p,encoding='utf-8').read()
s=s.replace("## 出どころ（Build Log #013）","## 出どころ")
s=s.replace("| caption | `ボーイッシュな女性の声。さっぱりとした話し方。` |\n| seed | `1006` |",
 "| caption | `やわらかい10代女性の声。小さめの声量で、そっと寄り添うように優しく話す。` |\n| seed | `2202` |")
s=s.replace("| 形式 | WAV / 16bit / mono / 48kHz / 約10.8秒 |","| 形式 | WAV / 16bit / mono / 48kHz / 約11.2秒 |")
s=s.replace('"caption":"ボーイッシュな女性の声。さっぱりとした話し方。","seed":1006}',
 '"caption":"やわらかい10代女性の声。小さめの声量で、そっと寄り添うように優しく話す。","seed":2202}')
s=s.replace("## なぜリファレンスを固定するのか","""## 声の履歴

| 版 | caption | seed | 経緯 |
|---|---|---|---|
| v1 | `ボーイッシュな女性の声。さっぱりとした話し方。` | `1006` | Build Log #013。22パターンから `cand6` を採用（commit `b1f82f6` の `sakura_midori.wav`） |
| v2（現在） | `やわらかい10代女性の声。小さめの声量で、そっと寄り添うように優しく話す。` | `2202` | 「落ち着いた10代女性・やわらかく近い距離感」の方向で caption 5種 × seed 4種（2101/2202/2303/2404）＝20パターンを生成し、`D_2202` を採用 |

## なぜリファレンスを固定するのか""")
open(p,'w',encoding='utf-8').write(s)
EOF
git diff --stat .
grep -n "1006\|2202" README.md
```

```text
 ConversationalAI/voice/README.md         |  17 ++++++++++++-----
 ConversationalAI/voice/sakura_midori.wav | Bin 1036844 -> 1071404 bytes
```

### 7. 新しいリファレンスで合成してみる

`voice: "sakura_midori"` を指定して、生成のときとは別のセリフで 1 本合成した。あわせて、相棒AIの設定がこの voice ID を参照していることも確かめた。

```bash
curl -s -o $D/test_v2.wav -w "%{http_code}\n" -X POST http://localhost:8088/v1/audio/speech -H "Content-Type: application/json" \
 -d '{"model":"irodori-tts","input":"ドクター、新しい声になったよ。どうかな、前よりやわらかく聞こえる？ これからもSO-101の実験、隣で見てるね。","voice":"sakura_midori","response_format":"wav"}'
file $D/test_v2.wav
grep -rn "sakura_midori" ~/Develop/project-physical-ai/ConversationalAI/*.yaml | grep -i voice
```

```text
200
.../test_v2.wav: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 48000 Hz
.../ConversationalAI/sakura_midori.yaml:61:      voice: 'sakura_midori' # ConversationalAI/voice/sakura_midori.wav（出どころは同ディレクトリの README）
```

```bash
aplay $D/test_v2.wav
```

- 合成は通った（HTTP 200）
- `sakura_midori.yaml` は `voice: 'sakura_midori'` のまま。voice ID はファイル名なので、**設定は変えなくてよい**
- サーバーは今回再起動していない。リファレンスを読み込んだまま持っている作りなら、旧い声が出る可能性がある。そのときは Irodori-TTS-Server を再起動する

## 今日の学び

- caption を 1 つに決めて seed だけ振るより、caption を数種類 × seed を数種類にしたほうが、「どの言葉が声のどこに効くか」と「同じ言葉でも個体差がどれくらいあるか」を分けて聴ける
- seed を caption 間でそろえておくと、比べる軸が 1 本に減る
- ファイルサイズが同じでも中身が同じとは限らない。疑ったら md5 で確かめる
- リポジトリを正にしてシンボリックリンクで参照する形（#013）は、差し替えのときに効いた。wav を 1 つ上書きするだけで、サーバーにも相棒AIの設定にも手を入れずに済んだ

## まだ測っていないこと

- `test_v2.wav` が本当に新しい声で出ているか（耳での確認）。サーバーを再起動しないと反映されない作りなのかどうか
- 実際の会話（Open-LLM-VTuber 経由、チャンク分割あり）で、新しい声がチャンクやターンをまたいでも安定するか
- 絵文字で感情を付けたとき（#013 節25）の聞こえ方が、新しい声でも自然か
- seed が声のどこ（声質・抑揚・間）を変えているのか。今回は 1 つのセリフでしか聴いていない

## 次やること（一歩だけ）

Open-LLM-VTuber で佐倉みどりと実際に何往復か話して、新しい声がチャンクやターンをまたいでも同じ声のままか聴く。

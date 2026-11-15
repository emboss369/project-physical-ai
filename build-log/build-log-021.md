# Build Log #021 — 2026-10-16

## 今日やったこと

しばらくアーム（SO-101）を使えないので、佐倉みどりのほうを進めた。目指す完成形はこう：

- 画面を操作しながら、佐倉みどりと会話して説明する動画（10分程度）を録る。佐倉みどりには事前にスクリプトを渡しておく
- 佐倉みどりのセリフの部分だけ、あとから生成AIで作ったリアル寄りの佐倉みどり画像でリップシンク動画を作る
- それを Windows の Camtasia で、元の画面録画に合成する

問題は合成の手間。佐倉みどりの発話ごとに短い動画が何十本もでき、それを1本ずつセリフに合わせて Camtasia に並べることになる。**今日はこの並べる作業を自動化する仕組みを作り、リップシンクに使う InfiniteTalk を ComfyUI で動かす準備をした。**

一日の流れ：

1. 合成の方式を決めた（Camtasia を自動操作するのではなく、録画と同じ長さの1本の動画にする）
2. 発話区間を切り出す `segment.py` と、リップシンク動画を並べる `compose.py` を作り、ダミーの録画で確かめた
3. ComfyUI に kijai さんの WanVideoWrapper を入れ、InfiniteTalk 用のモデルを一式ダウンロードした
4. サンプルワークフローを読み込んだら、ノードが2つ足りなかった。ComfyUI-MelBandRoFormer を追加で入れた
5. 実行したら音声の特徴量を作るノードで落ちた。transformers 5 系との相性の問題だったので、WanVideoWrapper の1ファイルにパッチを当てた
6. 最初の1本が生成できた。とても自然な動画になった。約11秒の動画に17分37秒かかった
7. 生成サイズを 640×640 から 480×480 に下げたら、8分37秒になった（約2倍速）

**今日の結論を一行で：Camtasia 側を自動化しなくても、「録画と同じ長さで、喋っていない間はブルーバック」の動画を1本作れば、Camtasia では 0:00 に置くだけで全セリフが同期する。**

---

### 1. 合成の方式を決める

Camtasia にクリップを時刻指定で自動配置する方法も考えた。Camtasia のプロジェクトファイル（.tscproj）は中身が JSON なので、理屈の上では生成できる。ただ公式に仕様が公開された形式ではなく、バージョンが変わると壊れる恐れがある。

そこで **ffmpeg で「録画と同じ長さの佐倉みどり映像」を1本作る**ことにした。

```text
[Ubuntu] OBS録画 ─┬─ トラック1: 自分のマイク
                  ├─ トラック2: 佐倉みどりの音声だけ
                  └─ 画面
        │
        ▼ segment.py（ffmpeg の silencedetect）
   seg_001.wav  seg_002.wav ...  ＋ segments.csv（開始・終了の秒数）
        │
        ▼ InfiniteTalk（ComfyUI）でリップシンク
   seg_001.mp4  seg_002.mp4 ...
        │
        ▼ compose.py
   midori_full.mp4（録画と同じ長さ。喋っていない間はブルーバック）
        │
        ▼ [Windows] Camtasia：画面録画と midori_full.mp4 を両方 0:00 に置き、ブルーバックを抜く
```

決めたこと：

- **佐倉みどりの声を OBS の別トラックに録る。** 別トラックになっていれば、無音検出だけで発話区間が正確に取れる。録り方（PipeWire の仮想シンクなど）はまだ試していない
- **隙間は待機動画ではなくブルーバックだけにする。** 喋っているときだけ表示されればよい。Camtasia で背景を透過にする
- **グリーンバックではなくブルーバック。** 名前が「みどり」なので、緑の髪や服になりやすい。逆に、青い目や青い小物は一緒に抜けてしまうので避ける
- **出入りはフェードさせる**

### 2. 発話区間を切り出す：`segment.py`

`ConversationalAI/video/segment.py` を作った。

```bash
python segment.py recording.mkv work/ --track 1
```

- `--track` は 0 始まりの音声トラック番号（OBS のトラック2 なら 1）
- 出力は `work/seg_NNN.wav`（16kHz mono）、`segments.csv`（name / start / end / duration）、`recording_duration.txt`
- **Open-LLM-VTuber は1文ずつ TTS で生成して再生する**ので、1回の返答の途中にも短い無音が入る。`--merge-gap`（既定 1.0 秒）より短い隙間は、同じ発話としてまとめる
- 区間の前後に `--pad`（既定 0.2 秒）の余白を足す。`--noise`（既定 -45dB）より小さい音を無音とみなす。この値は実際の録画で合わせる必要がある

### 3. リップシンク動画を並べる：`compose.py`

`ConversationalAI/video/compose.py` を作った。

```bash
python compose.py work/ midori_full.mp4 --recording recording.mkv --track 1
```

- `segments.csv` の時刻どおりに `seg_NNN.mp4` を置き、隙間はブルーバック（`--bg`、既定 `0x0000FF`）で埋める
- **時刻はフレーム番号に丸めてから計算する。** 区間ごとに秒で丸めると、30分つないだときに誤差が積もるため
- リップシンク動画が区間より長ければ切り、短ければ最後のフレームで延ばす。0.5秒以上ずれたら警告を出す
- 前後にフェード（`--fade`、既定 0.3 秒）を付ける。ffmpeg の `fade` は `color` を指定できるので、ブルーバックの色からフェードさせている
- `seg_NNN.mp4` がまだ無い区間はブルーバックのまま残して警告を出す。生成の途中でも結合して確認できる
- `--recording` を付けると、佐倉みどりの音声トラックも入れる。Camtasia で元の録画と波形を並べれば、同期を目で確かめられる
- 出力は 25fps が既定（InfiniteTalk の出力に合わせた）
- 中間ファイルは同じ設定の MPEG-TS で書き出し、最後に再エンコードなしで連結する

### 4. ダミーの録画で確かめる

30秒のダミー録画を作った。マイクトラックはノイズ、佐倉みどりのトラックには 2〜4秒・4.4〜6秒・12〜15秒・20〜27秒 に音を入れた。4秒からの 0.4 秒の無音は、文と文の間のつもり。リップシンク動画の代わりに、長さを少しずつずらした正方形のテスト映像を使った。2本目はわざと消して、動画が無い区間の動きも見た。

```text
3 区間 / 発話合計 15.2 秒 / 録画 30.0 秒 → work
name,start,end,duration
seg_001,1.843,6.237,4.394
seg_002,11.828,15.223,3.395
seg_003,19.839,27.228,7.389
⚠ 動画が無くブルーバックのままの区間: seg_002
→ out.mp4（30.04 秒 / 録画 30.02 秒）
```

- 0.4 秒の無音を挟んだ 2〜6秒は、1区間にまとまった
- 30秒の結合は約1.6秒で終わった
- 出力は 751 フレーム（25fps）。録画の長さ 30.02 秒をフレームに丸めた値と合っている

フレームを並べて目で確かめた。区間の始まりが 46 フレーム目のところ：

| フレーム | 見え方 |
|---|---|
| 44 | ブルーバック（区間の手前） |
| 47 → 54 | フェードイン |
| 100 | 全面表示 |
| 153 | フェードアウト中 |
| 157 | ブルーバックに戻る |
| 300 | ブルーバック（seg_002 の動画が無い区間） |
| 496 | ブルーバック（seg_003 の先頭フレーム＝フェード開始） |

**注意点：このフェードは「ブルーバックの色へ」のフェードで、本当の透明度の変化ではない。** 途中のフレームは青みがかった佐倉みどりになり、それを Camtasia のキーイングが半分抜く形になる。色の出方は本番の素材で見るまで分からない。不自然なら `--fade 0` にして、Camtasia のトランジションでフェードさせる。

### 5. InfiniteTalk を ComfyUI で動かす準備

リップシンクには InfiniteTalk を使う。Wan2.1 I2V 14B を土台にした音声駆動のモデル。#016 で入れた ComfyUI に、kijai さんの [ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) を入れて動かす。

| 項目 | 状態 |
|---|---|
| ComfyUI | v0.37.0（commit `b0f4b7b2`、#016 のまま） |
| ComfyUI-WanVideoWrapper | commit `088128b`（2026-05-24） |
| Python（venv） | 3.11.17（#016 の 3.12.3 から変わっていた。`venv_312_backup` が残っているので、venv を作り直したらしい） |
| PyTorch（venv） | 2.11.0+cu128（導入後も変わらず、CUDA 有効） |
| transformers（venv） | 5.17.0（ComfyUI v0.37.0 の requirements で入るもの。節8で効いてくる） |
| GPU / RAM | RTX 5060 Ti（16GB） / 30GB |

#### ノードを入れる

```bash
cd ~/development/ComfyUI/custom_nodes
git clone https://github.com/kijai/ComfyUI-WanVideoWrapper
cd ComfyUI-WanVideoWrapper
source ../../venv/bin/activate
pip install -r requirements.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

最後の行は、PyTorch が入れ替わっていないかの確認。Blackwell（RTX 5060 Ti）では、ここが別のバージョンになると GPU で動かなくなる。requirements.txt に torch は含まれていない。入った主なパッケージは gguf 0.19.0 / diffusers 0.40.0 / peft 0.21.0 / accelerate 1.15.0。

#### モデルをダウンロードする（合計 約24GB）

公式サンプル `example_workflows/wanvideo_2_1_14B_I2V_InfiniteTalk_example_03.json` が使っているモデルに合わせた。VRAM 16GB と RAM 30GB で動かすため、本体は量子化版（GGUF）にした。

```bash
cd ~/development/ComfyUI/models
mkdir -p wav2vec2

# 本体：Wan2.1 I2V 14B 480p（GGUF Q5_K_M）
hf download city96/Wan2.1-I2V-14B-480P-gguf wan2.1-i2v-14b-480p-Q5_K_M.gguf --local-dir diffusion_models/WanVideo
# InfiniteTalk（1人用、GGUF Q6_K）
hf download Kijai/WanVideo_comfy_GGUF InfiniteTalk/Wan2_1-InfiniteTalk_Single_Q6_K.gguf --local-dir diffusion_models/WanVideo
# 高速化 LoRA（6ステップで生成できる）
hf download Kijai/WanVideo_comfy Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors --local-dir loras/WanVideo
# VAE・テキストエンコーダ（fp8）
hf download Kijai/WanVideo_comfy Wan2_1_VAE_bf16.safetensors --local-dir vae
hf download Kijai/WanVideo_comfy umt5-xxl-enc-fp8_e4m3fn.safetensors --local-dir text_encoders
# CLIP Vision
hf download Comfy-Org/Wan_2.1_ComfyUI_repackaged split_files/clip_vision/clip_vision_h.safetensors --local-dir clip_vision
mv clip_vision/split_files/clip_vision/clip_vision_h.safetensors clip_vision/
# 音声特徴量 wav2vec2・ボーカル分離
hf download Kijai/wav2vec2_safetensors wav2vec2-chinese-base_fp16.safetensors --local-dir wav2vec2
hf download Kijai/MelBandRoFormer_comfy MelBandRoformer_fp16.safetensors --local-dir diffusion_models/MelBandRoFormer
```

| ファイル | 置き場所（`ComfyUI/models/` 以下） | サイズ（バイト） |
|---|---|---|
| wan2.1-i2v-14b-480p-Q5_K_M.gguf | diffusion_models/WanVideo/ | 12,743,654,784 |
| Wan2_1-InfiniteTalk_Single_Q6_K.gguf | diffusion_models/WanVideo/InfiniteTalk/ | 2,044,273,312 |
| lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors | loras/WanVideo/Lightx2v/ | 738,005,744 |
| Wan2_1_VAE_bf16.safetensors | vae/ | 253,806,278 |
| umt5-xxl-enc-fp8_e4m3fn.safetensors | text_encoders/ | 6,731,333,792 |
| clip_vision_h.safetensors | clip_vision/ | 1,264,219,396 |
| wav2vec2-chinese-base_fp16.safetensors | wav2vec2/ | 190,115,368 |
| MelBandRoformer_fp16.safetensors | diffusion_models/MelBandRoFormer/ | 456,479,072 |

- 本体だけ先に自分のターミナルでダウンロードし、サイズと SHA-256（`f4d22357…3d31`）が Hugging Face の値と一致するのを確かめた。残りは Claude Code にダウンロードしてもらった
- **本体を GGUF にしたら、InfiniteTalk も GGUF にする。** サンプルのメモに「GGUF と非 GGUF は混ぜられない」とある。量子化の段階（Q5 と Q6 など）が違うのは問題ない
- 品質に不満が出たら、本体を Q6_K（14.2GB）に上げる。Q8_0（18.1GB）は VRAM に収まらないので、ブロックスワップ（モデルの一部をメインメモリに逃がす機能）が多めに必要になる

### 6. サンプルワークフローを読み込む

ComfyUI を起動し、`custom_nodes/ComfyUI-WanVideoWrapper/example_workflows/wanvideo_2_1_14B_I2V_InfiniteTalk_example_03.json` をブラウザにドラッグする。

サンプルは作者の Windows 環境のファイル名（`WanVideo\...`）になっているので、ローダーのノードごとにファイルを選び直す。

| ノード | 選ぶファイル・設定 |
|---|---|
| WanVideoModelLoader | `wan2.1-i2v-14b-480p-Q5_K_M.gguf`。**attention_mode を `sageattn` → `sdpa` に変更**（SageAttention は入っていないため） |
| MultiTalkModelLoader | `Wan2_1-InfiniteTalk_Single_Q6_K.gguf` |
| WanVideoLoraSelect | `lightx2v_..._rank64_bf16.safetensors` |
| WanVideoVAELoader | `Wan2_1_VAE_bf16.safetensors` |
| WanVideoTextEncodeCached | `umt5-xxl-enc-fp8_e4m3fn.safetensors` |
| CLIPVisionLoader | `clip_vision_h.safetensors`。**ComfyUI の表示言語が日本語だと、このノードは「CLIPビジョンを読み込む」と表示される** |
| Wav2VecModelLoader | `wav2vec2-chinese-base_fp16.safetensors` |
| MelBandRoFormerModelLoader | `MelBandRoFormer/MelBandRoformer_fp16.safetensors`（次の節7を参照） |

WanVideoTorchCompileSettings でエラーが出たら、そのノードの接続を外す（初回のコンパイルに時間がかかるだけで、外しても動く）。

### 7. MelBandRoFormer のノードが足りなかった

読み込んだワークフローで、**MelBandRoFormerModelLoader だけファイルの選択欄がドロップダウンにならず、ただのテキストボックスになっていた。** 既定値は `MelBandRoFormer\MelBandRoformer_fp16.safetensors`。

原因は、テキストを書き換えるかどうかではなかった。**このノード自体が入っていなかった。** ComfyUI は、ノードの実体が無いと、ワークフローに保存されていた値をただのテキストとして表示する。ワークフローに出てくるノードの種類を、入っているカスタムノードと照合した。

```text
MISSING GetNode
MISSING MelBandRoFormerModelLoader
MISSING MelBandRoFormerSampler
MISSING SetNode
```

- SetNode / GetNode は KJNodes の画面側（JavaScript）だけで動くノードなので、Python 側に無いのは問題ない
- MelBandRoFormer の2ノードは、別のカスタムノード `ComfyUI-MelBandRoFormer` に入っている（ワークフローの `cnr_id` にもそう書いてある）

```bash
cd ~/development/ComfyUI/custom_nodes
git clone https://github.com/kijai/ComfyUI-MelBandRoFormer
cd ComfyUI-MelBandRoFormer
~/development/ComfyUI/venv/bin/pip install -r requirements.txt
```

- commit `92c8685`（2026-01-31）。依存は `rotary_embedding_torch` と `einops` だけで、PyTorch は 2.11.0+cu128 のまま
- このノードは `models/diffusion_models` からファイルを探す。ComfyUI を再起動すると選択式になり、`MelBandRoFormer/MelBandRoformer_fp16.safetensors` が選べるはず（Linux なので区切りは `/`）。再起動後の表示はまだ確かめていない
- MelBandRoFormer はボーカル分離（声と伴奏を分ける）のモデル。Irodori-TTS の音声は声だけなので本来は要らないが、サンプルをそのまま動かすために入れた

### 8. MultiTalkWav2VecEmbeds が `'NoneType' object is not subscriptable` で落ちた

ワークフローを実行すると、音声から特徴量を作るノード（MultiTalkWav2VecEmbeds）で止まった。

```text
  File ".../ComfyUI-WanVideoWrapper/multitalk/nodes.py", line 248, in process
    audio_emb = torch.stack(embeddings.hidden_states[1:], dim=1).squeeze(0)
                            ~~~~~~~~~~~~~~~~~~~~~~~~^^^^
TypeError: 'NoneType' object is not subscriptable
```

ログを見ると、そこまでは通っていた：

- wav2vec2 モデルは読み込めていた。`UNEXPECTED` の警告が出るが、事前学習用の重みを読み飛ばしているだけで無害
- MelBandRoFormer のボーカル分離も最後まで通っていた（`Processing chunks: 5/5`）

**原因は、WanVideoWrapper と transformers 5 系の相性だった。設定やモデルの間違いではない。**

1. WanVideoWrapper の `multitalk/wav2vec2.py` は、transformers の `Wav2Vec2Model` を継承して `forward` を自前で書いている。その中でエンコーダ（`self.encoder`）を直接呼び、`output_hidden_states=True` で各層の出力（`hidden_states`）を受け取る前提になっている
2. transformers 5.17.0 の `Wav2Vec2Encoder.forward` は引数が `**kwargs` に変わっていて、戻り値は `BaseModelOutput(last_hidden_state=...)` だけ。各層の出力を集めなくなっていた（手元のライブラリのソースで確認）
3. そのため `hidden_states` が `None` になり、`[1:]` で落ちる

上流にも同じ報告があった：[kijai/ComfyUI-WanVideoWrapper#2052](https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/2052)（2026-09-22、未解決）。手元の `088128b` が最新で、修正はまだ入っていない。

直し方は2つ考えた。

| 案 | 内容 | 判断 |
|---|---|---|
| **A** | `wav2vec2.py` で、エンコーダの各層にフック（`register_forward_hook`）を付けて出力を集める。issue の報告者が GPU で確認した方法 | **採用。** 変わるのは WanVideoWrapper の1ファイルだけ。transformers 4 でも 5 でも動く |
| B | transformers を 4.x に戻す | ComfyUI 本体や他のカスタムノードが 5 系前提で動いている可能性があり、影響範囲が読めない |

パッチの中身：

- 新しく `_run_encoder` を足し、`forward` と `encode` の2か所のエンコーダ呼び出しをこれに置き換えた
- エンコーダが `hidden_states` を返せば（transformers 4）それを使う。返さなければ（transformers 5）、各層のフックで集めた出力を使う
- 差分は `ConversationalAI/video/wanvideowrapper-wav2vec2-transformers5.patch` に控えた。WanVideoWrapper を `git pull` すると衝突しうるので、上流が直したら `git checkout multitalk/wav2vec2.py` で戻す。直っていなければ `git apply` で当て直す

ComfyUI を起動せずに単体で確かめた。transformers 5 の標準の `Wav2Vec2Model` は、最上位から `output_hidden_states=True` で呼べば各層の出力を返す。それを正解として比べた（3秒のランダムな音声、CPU）。

```text
hidden_states: tuple 13 ref: 13
max diff layers[1:]: 0.0
last_hidden_state diff: 0.0
node の audio_emb 形状 (seq_len=75): (12, 75, 768)
```

- `hidden_states` は13個（入力＋12層）で、標準モデルと同じ数
- ノードが使う `hidden_states[1:]`（12層分）も最終出力も、標準モデルとの差は 0.0（完全一致）
- ノードと同じ呼び方（3秒×25fps＝75フレーム）で、`audio_emb` は `(12, 75, 768)` になった

### 9. 最初の1本を生成する

パッチを当てて ComfyUI を再起動し、ワークフローを実行し直したら、**最後まで通った。出てきた動画はとても自然だった。**

| | ファイル | 中身 |
|---|---|---|
| 入力画像 | [images/021-infinitetalk-input.png](images/021-infinitetalk-input.png) | `ComfyUI/input/doll_00258_.png`。#016 の ComfyUI で作った人物画像。832×480。背景は青みがかったグレーで、クロマキー用の純色ブルーではない |
| 入力音声 | `ConversationalAI/voice/sakura_midori.wav` | 佐倉みどりの声のリファレンス（#020 の v2、約11.2秒）。`ComfyUI/input/sakura_midori.wav` と中身が同じことを `cmp` で確かめた |
| 出力動画 | [images/021-infinitetalk-output.mp4](images/021-infinitetalk-output.mp4) | 640×640 / 25fps / 297フレーム（11.88秒）/ H.264 ＋ AAC（音声付き） |

![InfiniteTalk の入力画像](images/021-infinitetalk-input.png)

出力から 0・100・200・296 フレーム目を抜き出したもの：

![InfiniteTalk の出力（0・100・200・296フレーム目）](images/021-infinitetalk-frames.png)

- 喋りながら顔の向きや表情が変わり、口も音声に合わせて動いている。止め絵の口だけが動く感じではない
- 背景は全フレームでほぼ動かなかった。左上 40×40 ピクセルの明るさ（Y の平均）は、全297フレームで 151.3〜153.5 の幅に収まった

**出力は `ComfyUI/output/` ではなく `ComfyUI/temp/` に出ていた。** サンプルの VHS_VideoCombine が `save_output: false`（プレビュー用の一時保存）になっているため。temp は ComfyUI を再起動すると消えるので、気づいてすぐ `images/` に退避した。本番では `save_output` を true にする。

#### 生成時間と VRAM

`ComfyUI/user/comfyui.log` から：

```text
[MultiTalk] Audio duration (279 frames) is shorter than requested (500 frames). Using 279 frames.
Sampling 279 frames in 4 windows, at 640x640 with 6 steps
Sampling audio indices 0-81:    6/6 [04:09<00:00, 41.66s/it]
Sampling audio indices 72-153:  6/6 [04:07<00:00, 41.28s/it]
Sampling audio indices 144-225: 6/6 [04:08<00:00, 41.38s/it]
Sampling audio indices 216-297: 6/6 [04:08<00:00, 41.39s/it]
[Sampling] Max allocated memory: max_memory=12.115 GB
[Sampling] Max reserved memory: max_reserved=13.281 GB
Prompt executed in 00:17:37
```

- **約11秒の動画に、全体で17分37秒かかった。** そのうちサンプリングが 81 フレームの窓 × 4 回で、1 窓あたり約4分8秒
- VRAM は最大 12.1GB（確保は 13.3GB）。16GB に収まった。ブロックスワップは 20 のまま
- 窓は 72 フレームずつずれて 9 フレーム重なる（`motion_frame: 9`）。なので新しく作られる長さは、1 窓あたり 72 フレーム＝2.88 秒
- **音声は 279 フレーム分（11.16 秒）なのに、出力は 297 フレーム（11.88 秒）だった。** 窓の数で割り切れない分は、無音で埋めて余分に生成する作り（サンプルのメモにもそう書いてある）。余分は末尾に付くので、`compose.py` が区間の長さで切り詰めれば問題ない

この速度で本番の量を見積もると（1 窓 = 2.88 秒を約4分8秒で作る、が今回の1回の実測）：

| 佐倉みどりの発話の合計 | 窓の数 | サンプリングだけの時間 |
|---|---|---|
| 1分（60秒） | 約21 | 約1.5時間 |
| 5分（300秒） | 約105 | 約7時間 |

あくまで1本から出した目安。実際は区間ごとに窓の端数が出るので、区間が細かいほど余分な生成が増える。モデルの読み込みなどの時間も別にかかる。

#### 生成の設定（出力 PNG に埋め込まれていたワークフローから）

| 項目 | 値 |
|---|---|
| 本体 / InfiniteTalk | `wan2.1-i2v-14b-480p-Q5_K_M.gguf` / `Wan2_1-InfiniteTalk_Single_Q6_K.gguf` |
| attention_mode | `sdpa` |
| LoRA | lightx2v rank64、strength 1.0 |
| 解像度 | 640×640（ImageResizeKJv2 で中央を切り抜き） |
| サンプラー | 6 steps / cfg 1.0 / shift 11.0 / `dpm++_sde` / seed 2 |
| 窓 | frame_window_size 81 / motion_frame 9 |
| 最大フレーム数 | 500（音声のほうが短いので 279 が使われた） |
| プロンプト | `a woman is singing`（サンプルのまま） |
| wav2vec2 | `DownloadAndLoadWav2VecModel`（`TencentGameMate/chinese-wav2vec2-base` を自動ダウンロード） |
| ブロックスワップ | 20 |

プロンプトはサンプルの「歌っている」のままだった。話している内容に合わせて変えたら、口の動きや表情が変わるかは試していない。

### 10. 生成サイズを下げて速くする

約11秒に17分半では、本番（佐倉みどりの発話が合計5分なら約7時間）が重い。ログを見る限り、時間のほとんどは GPU の計算そのものだった。

- 本体の重みは GPU に約3.3GB、メインメモリに約8.2GB 置かれ、毎ステップ転送されている。ただ PCIe 5.0 x8 なら 8GB でも1秒かからない。1ステップ約40秒のうちのごく一部
- 640×640・81フレームだと、モデルが一度に扱うトークン数は約3.4万（21潜在フレーム × 40 × 40）。線形層と Attention を合わせて1ステップ約 2×10¹⁵ 回の演算になる。5060 Ti の FP16 の実効性能を 50 TFLOPS 前後と置くと約40秒で、実測とほぼ合う。**実効性能の値は推定で、測っていない**

なので、生成サイズ（トークン数）を下げるのが一番効くはず、と考えた。

#### 出力のサイズは何で決まるか

**出力動画のサイズは、入力画像のサイズでは決まらない。** ワークフローの幅・高さの INTConstant（サンプルの既定は 640 / 640）で決まる。

```text
LoadImage
   ↓
ImageResizeKJv2  width / height = INTConstant、keep_proportion=crop、crop_position=center、divisible_by=16
   ↓
GetImageSizeAndCount ──→ WanVideoImageToVideoMultiTalk（出力サイズもここから受け取る）
                     └─→ WanVideoClipVisionEncode
```

- `crop` は、縦横比を保ったまま枠をすき間なく覆うまで拡大し、はみ出しを中央で切る。1回目の 832×480 は、1.33 倍の約 1109×640 にされ、左右が約176ピクセルずつ捨てられていた（元画像の中央 480×480 だけが使われた）
- 生成時間は出力の画素数で決まる。入力画像を大きくしても、遅くもきれいにもならない
- 入力画像は、出力したい縦横比で、幅・高さを16の倍数で作る

#### 3回の比較

| | 1回目 | 2回目 | 3回目 |
|---|---|---|---|
| 生成サイズ（INTConstant） | 640×640 | 640×640 | **480×480** |
| 入力画像 | 832×480（人物A） | 480×480（人物B） | 480×480（人物C） |
| 1ステップ | 約39秒 | 約39秒 | **約17秒** |
| 全体 | 17分37秒 | 18分00秒 | **8分37秒**（516.7秒） |
| VRAM 最大（確保） | 12.1GB（13.3GB） | 12.1GB（13.3GB） | **10.1GB（10.8GB）** |
| 背景の明るさの幅（隅の Y 平均、全297フレーム） | 151.3〜153.5 | 141.5〜144.1 | 148.8〜150.0 |

- **2回目は、入力画像だけ 480×480 にして、INTConstant を 640 のままにしてしまった。** 480×480 の画像が 640×640 に引き伸ばされてから生成されたので、速度は変わらなかった（ログも `at 640x640`）。生成時間を決めるのは入力ではなく INTConstant、を身をもって確かめた形
- 3回目で INTConstant も 480 にしたら、**ステップは 2.3 倍、全体は 2.1 倍速くなった。** 「トークン数が約0.56倍、Attention は2乗で効くので2倍前後」という見込みどおり
- 3回とも、音声・seed（2）・プロンプト（`a woman is singing`）・ステップ数（6）は同じ。**ただし入力画像が毎回違う。** 速度の比較は成り立つが、画質を 640 と 480 で比べたことにはならない

3回目の入力と出力：

| | ファイル |
|---|---|
| 入力画像 | [images/021-infinitetalk-480-input.png](images/021-infinitetalk-480-input.png)（`ComfyUI/input/image_70591329156168_00001_.png`、480×480） |
| 出力動画 | [images/021-infinitetalk-480-output.mp4](images/021-infinitetalk-480-output.mp4)（480×480 / 25fps / 297フレーム / 音声付き） |

![3回目の入力画像](images/021-infinitetalk-480-input.png)

出力から 0・100・200・296 フレーム目を抜き出したもの：

![3回目の出力（0・100・200・296フレーム目）](images/021-infinitetalk-480-frames.png)

- 顔立ちは最後まで入力画像に近いままに見える。2回目（640×640・上半身の構図）では後半で顔立ちが少し変わって見え、手を大きく振る動きも入ったが、3回目では姿勢も安定していた。どちらも静止画4枚を見た印象で、画像も違うので、解像度のおかげとは言えない
- 背景は青緑。クロマキーで抜くなら純色のブルーのほうがよい
- 2回目からは `save_output` を true にしたので、出力は `ComfyUI/output/` に残るようになった

#### 本番の見積もり（480×480）

3回目では、1つの窓（新しく作られるのは 2.88 秒分）が、デコード込みで約1分56秒だった。

| 佐倉みどりの発話の合計 | 窓の数 | 640×640 | 480×480 |
|---|---|---|---|
| 1分（60秒） | 約21 | 約1.5時間 | 約40分 |
| 5分（300秒） | 約105 | 約7時間 | 約3.4時間 |

これも1本から出した目安。区間ごとに窓の端数が出るので、実際はもう少し増える。

さらに速くする手として、SageAttention（今は `sdpa`）、ステップ数を 6 → 4 に減らす、が残っている。ログには torch.compile が動いた形跡もない。どれも未確認。

## 今日の学び

- 短いクリップをたくさん並べる作業は、編集ソフトを自動操作するより「全体と同じ長さの1本」にしてしまうほうが確実。編集ソフトでの作業は「0:00 に置く」だけになる
- 1つのトラックに佐倉みどりの声だけを録っておけば、発話区間は無音検出で取れる。録り方の段階で後工程が決まる
- 時刻を秒のまま区間ごとに丸めると誤差が積もる。フレーム番号に直してから引き算する
- ComfyUI で、選択式のはずの欄がテキストボックスになっていたら、まずノードが入っているかを疑う
- サンプルワークフローを読み込んだら、使われているノードの種類と入っているカスタムノードを照合すると、足りないものが一度に分かる
- ライブラリのメジャーバージョンが上がると、エラーを出さずに黙って値が `None` になることがある。`'NoneType' object is not subscriptable` は、まず呼び出し先の戻り値の仕様が変わっていないかを疑う。上流の issue を先に探すと早い
- パッチを当てたら、正解と数値で突き合わせる。今回は標準モデルの出力と差 0.0 で一致したので、安心して次に進める
- ComfyUI のプレビュー出力（`save_output: false`）は temp に出て、再起動で消える。残したい生成物はすぐ退避する
- 最初の1本で「1秒あたり何分か」を測ると、全体の計画が立つ。今回は約11秒に17分半。5分の発話なら一晩仕事になる
- 遅いときは、まず計算量で説明がつくかを見積もる。今回は「1ステップ約 2×10¹⁵ 回」で実測とほぼ合ったので、生成サイズを下げるのが効くと分かった。実際に 480×480 で2倍速くなった
- 比べるときは一度に1つだけ変える。2回目は入力画像だけ変えて生成サイズを変え忘れ、3回目は生成サイズと一緒に画像も変わったので、画質の比較ができなかった

## まだ測っていないこと

- 純色のブルーバックの画像を入れたとき、InfiniteTalk の出力でブルーがきれいに保たれるか（今回の背景は青みがかったグレー）
- プロンプトを「歌っている」から「話している」に変えたら、口の動きや表情がどう変わるか
- 640×640 と 480×480 の画質の差（同じ入力画像で比べていない）
- さらに速度を上げる手（SageAttention、ステップ数を減らす、torch.compile）がどれだけ効くか
- ブルーバックの色へのフェードが、Camtasia のキーイングでどう見えるか
- OBS で佐倉みどりの声だけを別トラックに録る方法（PipeWire の仮想シンクか、アプリ単位の音声キャプチャか）
- 実際の録音での、`segment.py` の無音の閾値（`--noise`）と隙間をまとめる秒数（`--merge-gap`）

## 次やること（一歩だけ）

純色のブルーバックで佐倉みどりの画像を1枚作り、プロンプトを「話している」に変えて、InfiniteTalk でもう1本生成する。背景のブルーが保たれるかを見る。

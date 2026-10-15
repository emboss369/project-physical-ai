# Build Log #018 — 2026-10-06

## 今日やったこと

今週はアームが手元にない。なので、実機を使わずにできることとして **SmolVLA（スモール・ブイ・エル・エー）を知る**ところから始めた。

一日の流れ：

1. SmolVLA が何なのかを、Hugging Face の公式ブログで押さえた
2. LeRobot の公式チュートリアル（SmolVLA のページ）を読み、手順を整理した
3. 手元の LeRobot 環境で SmolVLA が使えるかを確かめた
4. 論文と手元のコードで、SmolVLA の仕組みを 7 段階に分けて深掘りした

**今日の結論を一行で：実機が要るのは最後の推論だけ。手元の SO-101 のデータセットを使えば、アームがなくてもファインチューニングまでは進められる。**

---

### 1. SmolVLA とは

出典は Hugging Face の公式ブログ（2025年6月3日公開）。数値はブログに書かれたもので、自分では検証していない。

- **入力**：カメラ画像（複数可）、ロボットの現在の関節状態、言葉の指示（「レゴを箱に入れて」など）
- **出力**：この先の一連の動作（action chunk）
- **大きさ**：全体で約 4.5 億パラメータ（450M）。VLA としては小さく、ブログでは「一般向けの GPU や MacBook でも動く」としている
- **2つの部品**
  - **VLM（見て、言葉を理解する部分）**：SmolVLM2 がベース。1フレームを 64 トークンに圧縮し、VLM の途中の層で計算を打ち切って軽くしている
  - **Action Expert（動作を出す部分）**：約 1 億パラメータの Transformer。flow matching で、ノイズから正しい動作列を少しずつ組み立てる
- **事前学習データ**：LeRobot コミュニティのデータセット。ブログでは 487 個・約 1,000 万フレーム、論文では 481 個・2.29 万エピソード・1,060 万フレームと、数が少し食い違う。SO-100 / SO-101 のような安いアームのデータが中心
- **非同期推論**：動作の実行と次の推論を並行して進める。ブログでは、同期推論と比べて「タスク完了が約 30% 速く、処理量は 2 倍」
- **実機の結果（ブログの記載）**：SO-100 で成功率 78.3%。SO-101 でも ACT より良かったとのこと

### 2. 公式チュートリアルの流れ

出典：LeRobot ドキュメントの SmolVLA ページ。

1. **環境**：LeRobot を入れたあと、`pip install -e ".[smolvla]"`（手元の venv は uv で作ったので `uv pip install -e ".[smolvla]"`。節3）
2. **データ収集**：推奨は約 50 エピソード。大事なのは**バリエーション（置き場所など）ごとに十分な数を撮ること**。論文のデータは「キューブの位置 5 か所 × 各 10 エピソード」。25 エピソードでは足りず、性能が悪かったとのこと
3. **ファインチューニング**：`lerobot/smolvla_base`（事前学習済み、450M）を土台にする。20k ステップで A100 1 枚なら約 4 時間（ドキュメントの記載）

```bash
lerobot-train \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=${HF_USER}/mydataset \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=outputs/train/my_smolvla \
  --job_name=my_smolvla_training \
  --policy.device=cuda \
  --wandb.enable=true
```

4. **実機で推論**：`lerobot-rollout --policy.path=...`。#006 で ACT に使ったのと同じコマンド。`--task` には、データ収集のときと同じ指示文を渡す

### 3. 手元の環境チェック

```bash
cd ~/development/lerobot-workspace/lerobot
git log -1 --format='%h %cd'
grep -n "smolvla" pyproject.toml
ls src/lerobot/policies
~/development/lerobot-workspace/.venv/bin/python -c "import transformers"
```

- LeRobot は `6adf5151`（2026年8月13日）。`policies/smolvla` があり、`pyproject.toml` には `smolvla` の extra（`transformers`、`num2words`、`accelerate`）が定義されている
- venv には **`transformers` が入っていなかった**（`ModuleNotFoundError`）。`[smolvla]` の追加インストールが必要
- venv は uv で作ったもの（`.venv/pyvenv.cfg` に `uv = 0.12.4`）で、中に `pip` がない。なので `pip` ではなく `uv pip` を使う。`lerobot/` の中から実行しても、uv は親フォルダの `.venv` を見つける。先に `--dry-run` で、対象の環境と、`torch` が入れ替わらないことを確かめた

```bash
cd ~/development/lerobot-workspace/lerobot
uv pip install -e ".[smolvla]" --dry-run   # 確認だけ
uv pip install -e ".[smolvla]"
```

```text
Using Python 3.12.3 environment at: /home/hiro/development/lerobot-workspace/.venv
Resolved 75 packages in 7ms
Installed 14 packages in 14ms
 + accelerate==1.15.0
 + num2words==0.5.14
 + transformers==5.5.4
 （ほか、抜粋）
```

インストール後の確認：

```bash
~/development/lerobot-workspace/.venv/bin/python -c "
import torch, transformers
print(torch.__version__, torch.cuda.is_available(), transformers.__version__)
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy"
```

```text
2.11.0+cu130 True 5.5.4
```

`torch` は CUDA 版（`cu130`）のまま、GPU も見えている。SmolVLA のポリシーも import できた
- GPU は RTX 5060 Ti（16GB）

---

### 4. 仕組みを順に深掘りする

出典は論文（arXiv 2506.01844）と、手元の LeRobot（`6adf5151`）のコード（`src/lerobot/policies/smolvla/` と `policies/common/flow_matching.py`、`async_inference/configs.py`）。VLM の層数・次元は Hub の `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` の `config.json` で確認した。

```bash
cd ~/development/lerobot-workspace/lerobot/src/lerobot/policies/smolvla
sed -n 20,120p configuration_smolvla.py
grep -n "def sample_time\|x_t = \|u_t = \|mse_loss" modeling_smolvla.py
grep -n "num_vlm_layers\|expert_width_multiplier\|self_attn_every_n_layers" smolvlm_with_expert.py
curl -sL https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct/resolve/main/config.json
```

#### 4-1. 全体像：入力から動作が出るまで

```text
 カメラ画像（最大3視点） ─┐
 言葉の指示「レゴを箱へ」 ─┼─▶ [ VLM（SmolVLM2）]  ── 特徴 ──▶ [ Action Expert ] ──▶ 動作 50 ステップ分
 現在の関節状態（6軸）   ─┘    見る・読む担当                    動かす担当
                              （学習では固定）                   （ここを学習する）
                                                                    ▲
                                                               ノイズから10回かけて
                                                               動作列に仕上げる
```

| | ACT | SmolVLA |
|---|---|---|
| 言葉の指示 | なし（1つのモデルで1つのタスク） | **あり**（`--task` の文がモデルに入る） |
| 画像の見方 | ゼロから学習 | 画像と文章で**事前学習済み**の VLM を使う |
| 出発点 | ランダムな重み | コミュニティの SO-100/101 データで**事前学習済み**の `smolvla_base` |
| 一度に出す動作 | 100 ステップ（#008 の `n_action_steps=100`） | **50 ステップ**（`chunk_size=50`） |
| 動作の出し方 | 1回の推論で一気に出す | **ノイズから 10 回かけて組み立てる**（`num_steps=10`） |

#### 4-2. 画像・言葉・関節状態をトークンにする

| 入力 | 処理 | トークン数 |
|---|---|---|
| 画像（1カメラ） | 512×512 に余白付きでリサイズ（`resize_imgs_with_padding`）→ 16×16 のパッチに分ける（32×32＝1,024 個）→ pixel shuffle（`scale_factor=4`）で 4×4 のパッチを1つにまとめる | **64** |
| 言葉 | SmolVLM2 のトークナイザ。上限 `tokenizer_max_length=48` | 最大 **48** |
| 関節状態 | 32 次元に 0 埋め（`max_state_dim=32`）→ 線形層 `state_proj` で 960 次元へ | **1** |

- 並び順は「画像 → 言葉 → 状態」。これを **prefix** と呼ぶ
- #008 の2カメラ構成（wrist + front）なら、64×2 ＋ 最大48 ＋ 1 ＝ 最大 177 トークン
- 状態と動作はデータセットの平均・標準偏差で正規化（`MEAN_STD`）。画像はそのまま
- SO-101 の状態と動作は 6 次元（5 関節＋グリッパー）。残りの 26 次元は 0 埋め

#### 4-3. VLM と layer skipping

- SmolVLM2-500M の言語部分は **32 層・960 次元**（`config.json`）
- SmolVLA は **前半の 16 層だけ**を使い、残りは捨てる（`num_vlm_layers=16`、コードでは `text_model.layers[:16]`）
- 論文の理由は2つ。「下流のタスクに一番いい特徴は、最終層の特徴とは限らない」ことと、計算が半分になること
- 推論では、prefix を**観測1回につき1回だけ** VLM に通し、結果を KV キャッシュに残す（`use_cache=True`）。後の 10 回のノイズ除去では、重い VLM を回し直さない

#### 4-4. Action Expert の中身

- 層の数は VLM と同じ **16 層**（`num_expert_layers=-1`）。幅は VLM の **0.75 倍＝720 次元**（`expert_width_multiplier=0.75`）
- 入力：ノイズの入った動作列（50 ステップ × 32 次元）を `action_in_proj` で 720 次元にする → ノイズ除去の時刻 t の sin/cos 埋め込みと連結 → 小さな MLP（SiLU）に通す → **50 トークン**
- 層は2種類を交互に重ねる（`self_attn_every_n_layers=2`）
  - **偶数層（0, 2, …, 14）＝ self-attention（8 層）**：VLM のトークン列と動作トークンを1本の列としてまとめて注意をとる
  - **奇数層（1, 3, …, 15）＝ cross-attention（8 層）**：動作トークンが query になり、VLM の同じ層の K/V を見る。VLM の K/V は、Expert 専用の `k_proj` / `v_proj` で Expert の次元に写してから使う
- 誰が誰を見られるか（attention mask）
  - 画像と言葉：お互いに全部見える
  - 状態：画像と言葉を見る（画像と言葉の側からは状態は見えない）
  - 動作：prefix 全部と、**自分より前の動作だけ**（causal）
- 出力：`action_out_proj` で 32 次元に戻す。これが次の 4-5 の「速度」になる

#### 4-5. flow matching：ノイズから動作を組み立てる

学習（LeRobot の実装、`modeling_smolvla.py`）：

```text
A   = 正解の動作列（50 × 32）
ε   = ガウスノイズ（同じ形）
t   = 0〜1 の時刻。t=1 が純ノイズ、t=0 が正解
x_t = t·ε + (1 − t)·A          ← 正解とノイズを t の割合で混ぜる
u   = ε − A                    ← 「正解からノイズへ向かう方向」＝目標の速度
loss = ‖ v_θ(x_t, t, prefix) − u ‖²   ← モデルの出す速度 v を u に近づける
```

- t は Beta(1.5, 1.0) から取る（`× 0.999 + 0.001`）。密度が t に向かって増えるので、**ノイズの多い側（t が 1 に近い側）を多めに練習する**。コードのコメントでは openpi（π0）の流儀とのこと
- 論文の式は τ·A + (1−τ)·ε と、t の向きが逆の書き方になっている。中身は同じで、向きの約束が違うだけ

推論：

```text
x ← ε（純ノイズ、t=1）
10 回くりかえす：x ← x − (1/10)·v_θ(x, t, prefix)、t ← t − 1/10
t=0 の x が動作列
```

- なぜこうするのか：同じ場面でも、人のデモは毎回少しずつ違う（右から掴む回、左から掴む回）。平均を直接当てに行くと、その「間」のどっちつかずの動きになりやすい。flow matching は、ばらつきのある分布から**それらしい1本**を取り出せる。ACT は同じ問題に CVAE で対処している
- コスト：Action Expert は 10 回回るが、VLM は 1 回（4-3 の KV キャッシュ）

#### 4-6. action chunk と非同期推論

- 既定は `chunk_size=50`、`n_action_steps=50`。50 ステップを実行し切ってから次の観測を撮る（**同期**）。30Hz なら約 1.7 秒分
- 同期の弱点：推論の間、ロボットは次の動作を待つ。#008 で見た `Record loop is running slower` と同じ種類の問題
- **非同期推論**（`src/lerobot/async_inference/`）
  - GPU で推論する **PolicyServer** と、ロボットを動かす **RobotClient** に分ける
  - RobotClient は手元のキューの動作を実行し続ける。残りが閾値を下回ったら、次の観測をサーバーに送る（`chunk_size_threshold`、LeRobot の既定は 0.5）
  - 新しいチャンクと、まだ残っている古いチャンクが重なる部分は、`aggregate_fn_name` で選んだ方法で合成する
  - 論文では、関節空間でほぼ同じ観測は送らないフィルタも入れている
  - 論文の結果：1 タスクの所要時間が同期 13.75 秒 → 非同期 9.7 秒（約 30% 短縮）。一定時間内の pick-and-place が 9 回 → 19 回
- `lerobot-rollout` には `--inference.type=rtc`（Real-Time Chunking）というオプションもある。チュートリアルでは「低性能なハード向け」とだけ書かれている。中身はまだ読んでいない

#### 4-7. 事前学習データと、ファインチューニングで学習されるもの

事前学習（論文）：

- コミュニティデータセット 481 個、2.29 万エピソード、1,060 万フレーム。主に SO-100
- タスク文がばらばら・欠落していたので、**Qwen2.5-VL-3B-Instruct** に代表フレームを見せて書き直させた
- カメラ名もばらばらだったので、手作業で `OBS_IMAGE_1/2/3`（top / wrist / side）にそろえた
- 200k ステップ、バッチ 256、GPU 4 枚

ファインチューニング（LeRobot の既定）：

- **学習するのは Action Expert と、その周りの小さな層**（`state_proj`、`action_in_proj`、`action_out_proj`、時刻の MLP）。VLM と画像エンコーダは固定（`train_expert_only=True`、`freeze_vision_encoder=True`）
- 最適化は AdamW（lr 1e-4、betas (0.9, 0.95)）、warmup 1,000 ステップ、30k ステップかけて 2.5e-6 まで cosine で下げる、勾配クリップ 10

自分のデータに当てはめると：

- #008 の2カメラデータ（wrist + front）は、カメラごとに 64 トークンずつ入る
- 状態と動作は 6 次元。32 次元に 0 埋めされる
- データ収集で書いたタスク文が、そのまま言語入力になる。推論の `--task` は収集時と同じ文にする

---

### で、これは自分の SO-101 にとってどういう意味があるのか

- **ACT との違いは「言葉の指示」と「事前学習」。** ACT は1つのタスクをゼロから覚える。SmolVLA は、他の人の SO-100 / SO-101 データで基礎を学んだモデルを仕上げて使う。#006 で詰まった**位置汎化**（データを撮った位置でしか掴めない問題）を、事前学習がどこまで補えるかを ACT と比べたい
- **#006 の教訓と、公式の推奨が一致した。** 「置き場所をばらつかせて撮れ」。自分が失敗から学んだことが、公式チュートリアルでもデータ収集の要点として書かれていた
- **アームがなくても学習までは進められる。** 実機が要るのは手順 4 だけ。#005 / #008 で撮った SO-101 のデータセットは Hub にある。今週はファインチューニングまで進めておき、アームが戻ったら ACT と同じタスクで比べられる

## 今日の学び

- VLA は「見る・言葉を理解する部分（VLM）」と「動作を出す部分（Action Expert）」に分かれている
- SmolVLA は、小ささを工夫で作っている（トークン圧縮、途中の層で打ち切る、小さい Action Expert）
- データの量よりも、バリエーションごとの数が効く。25 エピソードでは足りなかった、という公式の記載は覚えておく
- 重い VLM は観測1回につき1回だけ通し、軽い Action Expert を 10 回回す。速さはこの分担から来ている
- ファインチューニングで学習するのは Action Expert まわりだけ。「どう見るか」は事前学習のまま、「どう動かすか」だけを自分のアームに合わせる

## まだ測っていないこと

- RTX 5060 Ti（16GB）で `batch_size=64` が載るか。小さい値から試す予定（推測）
- 20k ステップにかかる時間（A100 で約 4 時間という記載だけ）
- 手元の SO-101 データセットでファインチューニングした SmolVLA と、ACT の比較
- 自分のデータセットのカメラ名（wrist / front）を、`smolvla_base` の期待するカメラ名にどう対応させるか。まだ調べていない
- 非同期推論を、アームと GPU が同じ BTO PC の構成でどう動かすか（サーバーとクライアントを同じマシンで動かす形になると推測）
- `--inference.type=rtc` の中身

## 次やること（一歩だけ）

#008 のデータセットで短いステップ数の試し学習をして、VRAM と速度を測る。

## 参考

- [SmolVLA — LeRobot docs](https://huggingface.co/docs/lerobot/smolvla)
- [SmolVLA blog（Hugging Face）](https://huggingface.co/blog/smolvla)
- [SmolVLA 論文（arXiv 2506.01844）](https://huggingface.co/papers/2506.01844)

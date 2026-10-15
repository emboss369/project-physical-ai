# Build Log #019 — 2026-10-07

## 今日やったこと

#018 で SmolVLA の仕組みを調べ、`[smolvla]` を入れた。今日はその続きで、**手元の SO-101 のデータセットで SmolVLA をファインチューニングする準備**をした。アームはまだ手元にないので、学習までを進める。

一日の流れ：

1. 使うデータセットを決め、中身（カメラ名・状態の次元・タスク文）を確かめた
2. `smolvla_base` が期待するカメラ名と、自分のデータのカメラ名を対応させた（`--rename_map`）
3. 30 ステップの試し学習を、batch_size 8 / 16 / 32 / 64 で回して、VRAM と速度を測った
4. 本番の学習（batch_size=64 × 20,000 ステップ）を一晩回し、Hub に公開した

**今日の結論を一行で：RTX 5060 Ti（16GB）で、SmolVLA のファインチューニングは batch_size=64 まで載る。ただし速度（samples/s）はバッチを大きくしても変わらなかった。**

---

### 1. データセットを決める

#008 で Day2 を追加し、#009 で Day3 を追加した BTO のデータセットを使う。

- `emboss369/so101-yellow-lego-to-white-case_20260727_220921`
- いまの Hub 上の中身は Day1〜Day3 の合計で **150 エピソード／55,928 フレーム**（30fps）。#008 の時点では 100 エピソードだった
- ACT で同じデータを学習したものが `emboss369/act-yellow-lego-to-white-case-day3`（#009）。アームが戻ったら、これと比べられる

ローカルのコピー（`/mnt/data/huggingface/lerobot/emboss369/...`）は残っていなかった。なので Hub の `meta/` を直接読んで確かめた。

```bash
R=emboss369/so101-yellow-lego-to-white-case_20260727_220921
curl -sL https://huggingface.co/datasets/$R/resolve/main/meta/info.json | python3 -m json.tool
curl -sL https://huggingface.co/datasets/$R/resolve/main/meta/tasks.parquet -o tasks.parquet
```

| 項目 | 値 |
|---|---|
| `observation.state` / `action` | 6 次元（`shoulder_pan`、`shoulder_lift`、`elbow_flex`、`wrist_flex`、`wrist_roll`、`gripper`） |
| カメラ | `observation.images.wrist`、`observation.images.front`（どちらも 480×640） |
| タスク文 | `Put the yellow lego block into the white case`（1 種類だけ） |

### 2. カメラ名を合わせる（`--rename_map`）

`smolvla_base` の `config.json` を見ると、画像の入力名は `camera1` / `camera2` / `camera3` だった。

```bash
curl -sL https://huggingface.co/lerobot/smolvla_base/resolve/main/config.json | python3 -m json.tool
```

```text
observation.state            [6]
observation.images.camera1   [3, 256, 256]
observation.images.camera2   [3, 256, 256]
observation.images.camera3   [3, 256, 256]
```

自分のデータは `wrist` / `front` なので、そのままでは名前が合わない。`lerobot-train` には、データセット側の名前をポリシー側の名前に読み替える `--rename_map` がある（`src/lerobot/configs/train.py`）。

論文では、事前学習のカメラを top / wrist / side の順に `OBS_IMAGE_1/2/3` へそろえたとのこと（#018 節4-7）。そこで次のように対応させた。front を top 扱いにしたのは自分の判断で、これが最適かは分からない。

```text
observation.images.front → observation.images.camera1
observation.images.wrist → observation.images.camera2
（camera3 は無し）
```

- 足りない `camera3` は、`smolvla_base` では `empty_cameras=0` なので、ただ入力から外れる（`modeling_smolvla.py` の `prepare_images`）
- 学習後のチェックポイントの `policy_preprocessor.json` を見ると、この読み替えが `rename_observations_processor` として**保存されていた**。推論のときも、カメラ名 `wrist` / `front` のままで使える見込み（まだ実機では試していない）

### 3. 試し学習：batch_size ごとの VRAM と速度

#008 で ACT にやったのと同じ方法で測った。30 ステップだけ回し、Hub には上げない。VRAM は `nvidia-smi` を 1 秒ごとに読んで最大値を取った。

```bash
cd ~/development/lerobot-workspace/lerobot
source ../.venv/bin/activate
lerobot-train \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
  --rename_map='{"observation.images.front":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}' \
  --batch_size=8 --steps=30 --log_freq=10 \
  --output_dir=<一時フォルダ> --job_name=smolvla_test \
  --policy.device=cuda --policy.push_to_hub=false --wandb.enable=false
```

起動時のログ：

```text
Reducing the number of VLM layers to 16 ...
num_learnable_params=99880992 (100M)
num_total_params=450046176 (450M)
```

全体 4.5 億のうち、**学習するのは約 1 億**（Action Expert とその周り）。#018 節4-7 で読んだ `train_expert_only=True` のとおりだった。

| batch_size | VRAM ピーク | 1 ステップ | samples/s |
|---|---|---|---|
| 8 | 3,283 MiB | 0.179 秒 | 45 |
| 16 | 4,971 MiB | 0.360 秒 | 44 |
| 32 | 8,447 MiB | 0.725 秒 | 44 |
| 64 | 15,679 MiB | 1.509 秒 | 42 |

- **batch_size=64 も載った**。ただし 16,311 MiB 中 15,679 MiB で、余裕は 600 MiB ほど
- **samples/s は 42〜45 でほぼ一定**。バッチを倍にすると、1 ステップの時間もほぼ倍になる。#008 の ACT と同じ傾向（ACT は 44〜46 samples/s）
- ACT の batch_size=64 は OOM だった（#008）。SmolVLA は全体では ACT より大きいのに 64 が載った。学習する部分が 1 億に絞られていて、VLM の重みに勾配を持たないからだと考えている（推測）

### 4. 本番の学習時間の見積もり

samples/s がほぼ一定なので、学習時間は「何サンプル分見せるか」で決まる。

| 案 | batch × steps | 見せるサンプル数 | エポック数（55,928 フレーム） | 見積もり時間 |
|---|---|---|---|---|
| 公式チュートリアルのまま | 64 × 20,000 | 128 万 | 約 23 | 約 8.4 時間 |
| batch を半分に | 32 × 20,000 | 64 万 | 約 11 | 約 4.0 時間 |
| ACT（#009）とサンプル数をそろえる | 32 × 13,000 | 41.6 万 | 約 7.4 | 約 2.6 時間 |

見積もり時間は、表3の 1 ステップの時間 × steps。チェックポイントの保存時間は入れていない。

**公式チュートリアルのまま（64 × 20,000）で回すことにした。** VRAM の余裕が 600 MiB ほどしかないので、学習中は GPU を使う他のアプリ（llama-server、ComfyUI、佐倉みどりなど）を止めておく。学習後のモデルは、ACT と同じように Hub に公開する。

### 5. 本番の学習

Hub への push には書き込みトークンを使うので、#005 と同じく自分のターミナルで実行する。

```bash
cd ~/development/lerobot-workspace/lerobot
source ../.venv/bin/activate
mkdir -p /mnt/data/lerobot-outputs/logs
lerobot-train \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
  --rename_map='{"observation.images.front":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}' \
  --batch_size=64 \
  --steps=20000 \
  --save_freq=5000 \
  --output_dir=/mnt/data/lerobot-outputs/train/smolvla_yellow_lego \
  --job_name=smolvla_yellow_lego \
  --policy.device=cuda \
  --policy.repo_id=emboss369/smolvla-yellow-lego-to-white-case \
  --wandb.enable=false \
  2>&1 | tee /mnt/data/lerobot-outputs/logs/smolvla_yellow_lego.log
```

### 6. 本番の学習の結果

**完走して、Hub に公開できた。** 2026-10-07 22:01 に開始し、2026-10-08 06:30 に終わった。

```text
INFO 2026-10-08 06:29:59 ot_train.py:906 End of training
INFO 2026-10-08 06:30:30 in_utils.py:651 Model pushed to https://huggingface.co/emboss369/smolvla-yellow-lego-to-white-case
```

| 項目 | 実測 |
|---|---|
| 所要時間 | **8 時間 28 分**（見積もりは約 8.4 時間で、ほぼそのとおり） |
| 1 ステップ | 1.52 秒（試し学習の 1.509 秒とほぼ同じ） |
| 速度 | 42 samples/s（最初から最後まで一定） |
| VRAM（ログの `mem_gb`） | 14.40 GB で一定。OOM は起きなかった |
| データの読み込み（`data_s`） | 0.004 秒。読み込みは律速になっていない |
| 見せたサンプル数 | 128 万（約 22.9 エポック） |

loss の推移（ログの `loss`、200 ステップごとの値から抜粋）：

| step | loss | 学習率 |
|---|---|---|
| 200 | 0.447 | 1.5e-05（warmup 中） |
| 1,000 | 0.190 | 1.0e-04（最大） |
| 5,000 | 0.106 | 8.6e-05 |
| 10,000 | 0.054 | 5.2e-05 |
| 15,000 | 0.037 | 1.7e-05 |
| 20,000 | 0.035 | 2.5e-06 |

- 10,000 ステップまでは下がり続け、**15,000 ステップあたりから 0.035 前後で横ばい**になった
- 学習率のスケジュールは自動で縮められていた。`steps`（20,000）が既定の減衰期間（30,000）より短いので、warmup が 1,000 → 666、減衰が 30,000 → 20,000 になった

```text
Auto-scaling LR scheduler: num_training_steps (20000) < num_decay_steps (30000). Scaling warmup: 1000 → 666, decay: 30000 → 20000 (scale factor: 0.667)
```

- **この loss は ACT の loss とは比べられない。** ACT は L1＋KL、SmolVLA は flow matching の速度の二乗誤差（#018 節4-5）で、測っているものが違う
- 評価用のデータは分けていない（`eval_split: 0.0`）。loss は学習データに対する値なので、**実機で掴めるかどうかは、この数字からは分からない**
- データ拡張（`image_transforms`）は既定のままオフだった

公開されたリポジトリも確かめた。公開（`private: False`）で、`policy_preprocessor.json` の先頭にカメラ名の読み替え（`front → camera1`、`wrist → camera2`）が入っている。

ローカルのチェックポイントは 5,000 ステップごとに 4 つ（各 1.3GB、`/mnt/data/lerobot-outputs/train/smolvla_yellow_lego/checkpoints/`）。loss が横ばいになる前の 10,000 と、横ばい後の 20,000 を実機で比べることもできる。

## 今日の学び

- 事前学習済みのポリシーを別のカメラ名のデータで学習するときは、`--rename_map` で名前を読み替える。読み替えはチェックポイントに保存される
- SmolVLA の学習は、RTX 5060 Ti でも batch_size=64 まで載る。でも速さはバッチで変わらないので、大きいバッチにしても早く終わるわけではない
- 30 ステップの試し学習の速度から、本番の時間をほぼ正確に見積もれた（8.4 時間の見積もりに対して実測 8 時間 28 分）
- loss が下がったことと、実機で動くことは別。SmolVLA の loss は ACT の loss とも比べられない

## まだ測っていないこと

- 実機で掴めるか。loss からは分からない
- front を camera1、wrist を camera2 にした対応が良いのか。逆にした場合との比較はしていない
- 実機での推論の速さ（推論 1 回の時間、30Hz に追いつくか）。アームが戻ってから

## 次やること（一歩だけ）

アームが戻ったら、`emboss369/smolvla-yellow-lego-to-white-case` を `lerobot-rollout` で動かし、ACT（`act-yellow-lego-to-white-case-day3`）と同じ置き場所で比べる。

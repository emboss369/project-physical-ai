# Build Log #009 — 2026-08-08〜08-09

## 今日やったこと

Build Log #008 の「次やること」に挙げた2件を両方着手した日。

1. **Day3**：可動域の限界（アームを伸ばしきる遠い位置）にブロックを置いたデータを50エピソード追加収集し、再学習・実機評価した。**結果は失敗**（遠い位置を掴めず、ずれる）
2. **保留仮説「M1Macデータの質」の検証**：実機を使わないオフライン解析で、M1Mac時代に収集したデータとBTOで収集したデータを直接比較した。**「データの質が原因」仮説は棄却**され、代わりに「学習の更新回数不足」という新しい候補が浮上した

さらに、Day3失敗の原因を切り分けるため、追従誤差とデータカバレッジの定量測定を行い、**遠い位置のデータが全体の3.8%しかなかった**ことを突き止めた。

翌8/9、「学習の更新回数不足」仮説を実機で検証したが**これも棄却**。最終的に、Day3の失敗とM1Macの2ヶ月来の謎は、**「カバーしたい範囲に対してデータが疎すぎる」という同一の原因**で説明できる、という結論に至った。M1Macのレゴデータは BTO の約11倍の範囲を3倍のエピソード数でカバーしており、実効密度は約1/4だった。

さらに動画のフレームを実際に見比べたところ、M1Macデータでは**レゴだけでなく白いケースの位置も毎回変わっていた**ことが判明した。BTO側はケースを毎回同じ位置に置いている。配置の組み合わせ空間は積で効くため、広さの問題に加えて**変動の次元そのものが倍**だった。

途中、振動でサーボドライバ基板のジャンパー（`J4`）が脱落してUSBデバイスが消えるハードウェア障害が発生し、その切り分けにも時間を使った。

**今日の結論を一行で：模倣学習の成否を決めるのはエピソード数ではなく、「何を固定し、何をどれだけの密度で変動させたか」である。**

---

### 1. Day3データ収集：可動域の限界（遠い位置）を追加

Build Log #008 の Day2 と同じデータセットに `--resume=true` で追記する。今回は意図的に「アームをしっかり伸ばさないと届かない、遠い位置」にレゴブロックを置いた。

```bash
HF_USER=$(hf auth whoami --format quiet)
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --teleop.type=so101_leader \
    --teleop.port=$LEADER_ARM \
    --teleop.id=right_leader_arm \
    --dataset.repo_id=emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
    --dataset.root=/mnt/data/huggingface/lerobot/${HF_USER}/so101-yellow-lego-to-white-case_20260727_220921 \
    --dataset.num_episodes=50 \
    --dataset.single_task="Put the yellow lego block into the white case" \
    --dataset.streaming_encoding=false \
    --resume=true \
    --display_data=true
```

`--dataset.root` の明示は Build Log #008 で特定した `resume()` の制約（root省略を許さない）による。`--dataset.num_episodes=50` は「このセッションで追加する数」で、Day2 の実績どおりの挙動だった。

記録終了時のログ抜粋：

```
INFO 2026-08-08 08:03:02 ls/utils.py:143 Recording episode 148
Right arrow key pressed. Exiting loop...
INFO 2026-08-08 08:03:16 ls/utils.py:143 Reset the environment
Right arrow key pressed. Exiting loop...
Map: 100%|██████████| 405/405 [00:00<00:00, 6365.94 examples/s]
INFO 2026-08-08 08:03:24 ls/utils.py:143 Recording episode 149
Right arrow key pressed. Exiting loop...
Map: 100%|██████████| 366/366 [00:00<00:00, 6348.44 examples/s]
INFO 2026-08-08 08:03:41 ls/utils.py:143 Stop recording
INFO 2026-08-08 08:03:42 a_opencv.py:601 OpenCVCamera(0) disconnected.
INFO 2026-08-08 08:03:44 a_opencv.py:601 OpenCVCamera(2) disconnected.
INFO 2026-08-08 08:03:44 follower.py:238 right_follower_arm SOFollower disconnected.
INFO 2026-08-08 08:03:44 o_leader.py:163 right_leader_arm SOLeader disconnected.
Found 15 files to upload
  Preparing   ████████████████████  15 / 15 ✓
  Uploading   ████████████████████  13 / 13 files  230MB · 4.26MB/s ✓
  Committing  ████████████████████  15 / 15 ✓
INFO 2026-08-08 08:04:04 ls/utils.py:143 Exiting
```

50エピソードの追加記録とHubへのアップロードが完了。

---

### 2. steps数の算出

Day1（20,000steps／21,103frames ≒ 7.58エポック）、Day2（36,000steps／38,384frames ＝ 7.50エポック）と同じエポック数を維持する方針で、実測フレーム数から算出した。

```bash
python3 -c "
import json
d=json.load(open('/mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921/meta/info.json'))
f=d['total_frames']
print('total_episodes:', d['total_episodes'], 'total_frames:', f)
print('steps (7.5 epoch, bs=8):', round(f*7.5/8/1000)*1000)
print('推定所要時間:', round(f*7.5/8/5.45/60), '分 (@5.45 step/s)')
"
```

```
total_episodes: 150 total_frames: 55928
steps (7.5 epoch, bs=8): 52000
推定所要時間: 160 分 (@5.45 step/s)
```

Day3 の追加分は **50エピソード／17,544フレーム**（55,928 − 38,384）。累計 **150エピソード／55,928フレーム**。

`5.45 step/s` は Build Log #008 の実測値。batch_size=8 は #008 のスループット実測（batch_size 8〜32 で samples/s がほぼ一定＝大きいバッチにする理由がない）と、Day1・Day2 との比較可能性を保つ目的から据え置いた。

---

### 3. Day3学習の実行

```bash
lerobot-train \
  --dataset.repo_id=emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
  --policy.type=act \
  --policy.device=cuda \
  --output_dir=/mnt/data/lerobot-outputs/train/act_yellow_lego_day3 \
  --job_name=act_yellow_lego_day3 \
  --policy.repo_id=emboss369/act-yellow-lego-to-white-case-day3 \
  --batch_size=8 \
  --steps=52000 \
  --save_freq=5000 \
  --wandb.enable=false \
  2>&1 | tee /mnt/data/lerobot-outputs/logs/act_yellow_lego_day3.log
```

起動時の設定ダンプから、後の考察に効く部分を抜粋：

```
 'optimizer': {'betas': [0.9, 0.999],
               'eps': 1e-08,
               'grad_clip_norm': 10.0,
               'lr': 1e-05,
               'type': 'adamw',
               'weight_decay': 0.0001},
 'policy': {'chunk_size': 100,
            ...
            'n_action_steps': 100,
            'n_obs_steps': 1,
            'temporal_ensemble_coeff': None,
            'use_vae': True,
            'vision_backbone': 'resnet18'},
 'sample_weighting': None,
 'seed': 1000,
 'steps': 52000,
```

```
INFO 2026-08-08 08:07:16 ot_train.py:407 cfg.steps=52000 (52K)
INFO 2026-08-08 08:07:16 ot_train.py:408 dataset.num_frames=55928 (56K)
INFO 2026-08-08 08:07:16 ot_train.py:409 dataset.num_episodes=150
INFO 2026-08-08 08:07:16 ot_train.py:412 Effective batch size: 8 x 1 = 8
INFO 2026-08-08 08:07:16 ot_train.py:413 num_learnable_params=51597190 (52M)
```

序盤（loss の落ち方）：

```
step:200  smpl:2K  epch:0.03 loss:6.674 grdn:153.039 l1_loss:0.681 kld_loss:0.599
step:400  smpl:3K  epch:0.06 loss:3.009 grdn:85.991  l1_loss:0.574 kld_loss:0.244
step:1K   smpl:8K  epch:0.14 loss:2.002 grdn:66.450  l1_loss:0.424 kld_loss:0.158
step:2K   smpl:16K epch:0.29 loss:1.274 grdn:52.210  l1_loss:0.344 kld_loss:0.093
step:3K   smpl:24K epch:0.43 loss:0.821 grdn:40.596  l1_loss:0.306 kld_loss:0.052
```

終盤：

```
Training:  99%|█████████▉| 51400/52000 [2:37:42<01:50,  5.45step/s]
step:51K smpl:411K ep:1K epch:7.35 loss:0.106 grdn:8.348 lr:1.0e-05 smp/s:44 mem_gb:3.73 l1_loss:0.104 kld_loss:0.000
step:52K smpl:413K ep:1K epch:7.38 loss:0.104 grdn:8.451 lr:1.0e-05 smp/s:44 mem_gb:3.73 l1_loss:0.102 kld_loss:0.000
step:52K smpl:414K ep:1K epch:7.41 loss:0.103 grdn:8.307 lr:1.0e-05 smp/s:44 mem_gb:3.73 l1_loss:0.101 kld_loss:0.000
step:52K smpl:416K ep:1K epch:7.44 loss:0.105 grdn:8.232 lr:1.0e-05 updt_s:0.182 data_s:0.001 smp/s:44 mem_gb:3.73 l1_loss:0.102 kld_loss:0.000
INFO 2026-08-08 10:46:49 ot_train.py:655 Checkpoint policy after step 52000
Training: 100%|██████████| 52000/52000 [2:39:34<00:00,  5.43step/s]
INFO 2026-08-08 10:46:50 ot_train.py:741 End of training
INFO 2026-08-08 10:47:07 etrained.py:326 Model pushed to https://huggingface.co/emboss369/act-yellow-lego-to-white-case-day3
```

**所要時間 2時間39分34秒**（見積もり160分に対して実測159.5分。ほぼ一致）。

収束の比較：

| | loss | l1_loss | kld_loss | steps | frames |
|---|---|---|---|---|---|
| Day1 | 0.119 | 0.104 | 0.002 | 20,000 | 21,103 |
| Day2 | 0.106 | 0.101 | ≈0.000 | 36,000 | 38,384 |
| **Day3** | **0.105** | **0.102** | **0.000** | 52,000 | 55,928 |

**学習側は健全**。データ量が2.6倍になっても Day1 と同水準まで収束している。

---

### 4. Day3ポリシーの実機評価 → 失敗

```bash
lerobot-rollout \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --policy.path=emboss369/act-yellow-lego-to-white-case-day3 \
    --fps=30 \
    --task="Put the yellow lego block into the white case" \
    --display_data=true \
    --duration=0
```

アームから遠い（しっかり伸ばさないと届かない）場所にレゴブロックを置いて評価した。

**結果：掴めない。ずれてしまう。**

Day2 では「記録時と同じ位置でしか掴めない」から「左右に置いても掴める」まで進んだが、Day3 で狙った「遠い位置」は、そのためのデータを50エピソード追加したにもかかわらず掴めるようにならなかった。

この時点での見立て（後の測定で裏付けを取る）：**今回の50エピソードは一気に対象範囲を広げたため、カバーしたい空間の広さに対してデータ量が全く足りていないのではないか。**

---

### 5. 保留仮説「M1Macデータの質」の検証設計

Build Log #008 で保留にした仮説の再検討。#008 で分かっていたのは「M1Macで収集・学習したポリシーは、M1MacでもRTX 5060 Tiでもカクつく」＝**推論ハードウェア速度は主因ではない**、ここまで。「データの質が原因」はまだ消去法で残った候補にすぎず、これを詰めずに進むと思い込みを別の思い込みに置き換えるだけになる。

カクつきの原因になりうるものを、**互いに区別可能な形で**列挙した。

| | 仮説 | 残す指紋（fingerprint） |
|---|---|---|
| A1 | 収集ループが遅く、値が保持された（8Hzの指令を30fpsで記録） | action に同一値の連続（階段状）。Δaction が「ほぼ0が大半＋たまに大ジャンプ」の二峰分布 |
| A2 | 時間圧縮（実時間8Hzで進んだ動作を30fpsとして記録） | 同一値の連続は無いが、Δaction の分散が異常に大きい。エピソード長が体感より短い |
| B | ACTのチャンク継ぎ目（`n_action_steps=100`、temporal ensemble なし） | jerk のスパイクが100ステップ周期（30Hzで約3.33秒ごと）に集中 |
| C | 推論側ループが別の理由で遅い（カメラ取得・`display_data=true` のオーバーヘッド） | rollout ログのHz警告 |
| D | ポリシー自体の不確実性（単一カメラ・データ不足で行動分布が多峰） | 特定の局面でのみ振動 |
| E | フォロワー側の追従（サーボPID） | 指令は滑らかなのに実機の state だけ荒れる |

重要なのは、**A（データ）は実機を触らずにオフラインで検証できる**こと。データセットはHubに残っているので、ロボットもGPUも要らない。Day3の学習が2時間40分回っている間に実行できる。

また、Day3の設定ダンプで `'temporal_ensemble_coeff': None` を確認したことで、**B が構成上「有効な容疑者」であること**が確定した（100ステップ＝約3.33秒ごとに、前チャンク終端と新チャンク先頭が滑らかに繋がる保証がない）。

**事前に反証条件を決めておいた**（思い込みの再生産を避けるため）：

> M1Macデータの Δaction 分布・同一値連続長がBTOデータと有意に差が無ければ、「データの質」仮説は棄却する。

---

### 6. 解析スクリプトの作成とBTOベースラインの取得

`tools/action_forensics.py` を作成（このリポジトリに追加）。LeRobotDataset の parquet から action 系列だけを読み、以下を計算する。

| 指標 | 定義 | 何が分かるか |
|---|---|---|
| timestamp乖離 | `max abs(timestamp - frame_index/fps)` | timestamp が実測値か合成値か |
| 直前と完全一致した比率 | 全次元が直前フレームと厳密一致したフレームの割合 | A1（値の保持） |
| 連長3以上の割合 | 同一値が3フレーム以上続いた連の割合 | A1（8Hz→30fpsなら連長3〜4が支配的になるはず） |
| \|Δaction\| 平均/中央値/99%点 | 隣接フレーム間のL2距離 | A2（時間圧縮なら約3.75倍になるはず） |
| jerk RMS | 2階差分のL2ノルムのRMS | 動作の滑らかさ |
| 4Hz以上のパワー比 | 各関節のパワースペクトルのうち4Hz以上が占める割合 | 高周波振動の有無 |

差分はすべてエピソード境界で切っている（エピボーダーで巨大な偽の跳躍が出るのを防ぐため）。

まず手元のBTOデータ（Day1〜Day3、良品の対照群）で基準値を取った。

```bash
cd /home/hiro/development/lerobot-workspace && source .venv/bin/activate
python3 tools/action_forensics.py \
  /mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921
```

```
指標                                      so101-yellow-lego-to-white-case_20260727_220921
---------------------------------------------------------------------------------------
エピソード数                                                                              150
総フレーム数                                                                            55928
公称fps                                                                                30
timestamp と frame/fps の最大乖離[s]                                                 0.000001
エピソード長 平均[frames]                                                                 372.9
エピソード長 平均[s] (公称fps換算)                                                            12.43
★直前と完全一致したフレーム比率                                                                 0.1283
★連長3以上の割合                                                                        0.0159
最大連長                                                                                129
|Δaction| 平均                                                                     2.0396
|Δaction| 中央値                                                                    1.4971
|Δaction| 99%点                                                                   8.2214
★|Δaction| 変動係数 (std/mean)                                                        0.997
jerk RMS (2階差分)                                                                  0.7699
★jerk / |Δaction|平均                                                               0.377
4Hz以上のパワー比                                                                       0.0002
```

---

### 7. 発見：`timestamp` は合成値だった

```
timestamp と frame/fps の最大乖離[s]   0.000001
```

`timestamp` は `frame_index / fps` そのもの（乖離が浮動小数の誤差レベル）。つまり **LeRobotDataset の timestamp からは実時刻の情報が一切取れない**。

これは仮説検証の方法論に直接効く。「収集ループが何Hzで回っていたか」をタイムスタンプから判定することは**原理的に不可能**で、値のパターン（同一値の連・Δの分布）に頼るしかない。もし気づかずに timestamp を根拠に「30Hzで記録されている」と結論していたら、完全に誤った検証をしていた。

---

### 8. M1Mac側データセットの特定と、学習設定の発掘

比較対象のデータセット名は、ポリシー側の学習設定（`train_config.json`）から引ける。

```bash
for p in emboss369/act_so101_lego_2cam_v1_150 emboss369/act_so101_lego_2cam_v1_100 \
         emboss369/so101_lego_2cam_narrow_v1_49 emboss369/act_policy_20260606; do
  echo "=== $p ==="
  python3 -c "
import json
from huggingface_hub import hf_hub_download
d = json.load(open(hf_hub_download('$p', 'train_config.json')))
print(' dataset.repo_id :', d.get('dataset',{}).get('repo_id'))
print(' steps/batch     :', d.get('steps'), '/', d.get('batch_size'))
pol = d.get('policy',{})
print(' n_action_steps  :', pol.get('n_action_steps'), ' temporal_ensemble_coeff:', pol.get('temporal_ensemble_coeff'))
"
done
```

```
=== emboss369/act_so101_lego_2cam_v1_150 ===
 dataset.repo_id : emboss369/so101_lego_2cam_v1_20260617_192936
 steps/batch     : 12000 / 32
 n_action_steps  : 100  temporal_ensemble_coeff: None
=== emboss369/act_so101_lego_2cam_v1_100 ===
 dataset.repo_id : emboss369/so101_lego_2cam_v1_20260617_192936
 steps/batch     : 8000 / 32
 n_action_steps  : 100  temporal_ensemble_coeff: None
=== emboss369/so101_lego_2cam_narrow_v1_49 ===
 dataset.repo_id : emboss369/so101_lego_2cam_v1_20260617_192936
 steps/batch     : 5000 / 32
 n_action_steps  : 100  temporal_ensemble_coeff: None
=== emboss369/act_policy_20260606 ===
 dataset.repo_id : emboss369/record-test_20260606_114847
 steps/batch     : 20000 / 8
 n_action_steps  : 100  temporal_ensemble_coeff: None
```

M1Mac時代の2カメラ系ポリシー3本は、すべて同一データセット `emboss369/so101_lego_2cam_v1_20260617_192936` から学習されていた。そして**batch_size が 32、steps が 12,000／8,000／5,000** だったことが判明。これが後述の新候補につながる。

---

### 9. Hugging Face Xet CDN の500エラーとフォールバック

Hubからデータセットを取得しようとしたところ、Xet経由のダウンロードが失敗した。

```
RuntimeError: Task error: File reconstruction error: CAS Client Error: Request error:
HTTP status server error (500 Internal Server Error),
domain: https://us.aws.cdn.hf.co/xorbs/default/58ecba3deb832b21664dcdff8f7f55154805d7c821ae68368b0b341df3465983
```

`HF_HUB_DISABLE_XET=1` で通常のHTTP経路にフォールバックしたところ成功した。Hub側の一時障害と判断（再現性は未確認）。

```bash
HF_HUB_DISABLE_XET=1 python3 tools/action_forensics.py ...
```

---

### 10. BTO vs M1Mac のデータ比較 → 「データの質」仮説の棄却

parquet（action系列）だけを取得し、動画はダウンロードしない設定で3つのデータセットを比較した。

```bash
cd /home/hiro/development/lerobot-workspace && source .venv/bin/activate
HF_HUB_DISABLE_XET=1 python3 tools/action_forensics.py \
  /mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
  --repo-id emboss369/so101_lego_2cam_v1_20260617_192936 \
  --repo-id emboss369/record-test_20260606_114847
```

| 指標 | BTO（Day1-3, 良品） | **M1Mac 2cam v1** | M1Mac 単一カメラ（初期版） |
|---|---|---|---|
| エピソード数 | 150 | 150 | 5 |
| 総フレーム数 | 55,928 | 60,936 | 4,034 |
| timestamp乖離[s] | 0.000001 | 0.000001 | 0.000001 |
| エピソード長 平均[frames] | 372.9 | 406.2 | 806.8 |
| ★連長3以上の割合 | 1.59% | **2.13%** | 2.93% |
| ★直前と完全一致した比率 | 12.83% | **17.05%** | 18.07% |
| 最大連長 | 129 | 93 | 66 |
| \|Δaction\| 平均 | 2.0396 | **1.8064** | 1.3147 |
| \|Δaction\| 中央値 | 1.4971 | 1.1019 | 0.7764 |
| \|Δaction\| 99%点 | 8.2214 | 8.5789 | 5.8053 |
| jerk RMS | 0.7699 | 0.7077 | 1.1641 |
| ★jerk / \|Δaction\|平均 | 0.377 | **0.392** | 0.885 |
| 4Hz以上のパワー比 | 0.0002 | **0.0002** | 0.0003 |

事前に決めた反証条件にそのまま該当した。

- **A1（8Hz保持の階段）は棄却**。8Hzで記録されていれば連長3〜4が支配的になり割合が数十%に跳ね上がるはずだが、実測は **2.13%**。BTOの1.59%と実質同水準
- **A2（時間圧縮）も棄却**。実時間が遅いのに30fpsで刻んでいたなら1フレームあたりの移動量はBTOの約3.75倍になるはずだが、実測は **1.81 < 2.04 でむしろ小さい**。エピソード長も406フレーム（公称13.5秒）で、8Hz実効なら実時間50秒/エピソードという非現実的な値になる
- 高周波成分（0.0002）もjerk比（0.392）もBTOとほぼ同一

**M1Macで収集した教示データは、BTOで収集したものと同じくらい滑らかだった。** 収集は問題なく、推論ハードウェアも主因ではない。原因は別のところにある。

なお、この結果により「M1Macポリシーを低fps（8〜15Hz）で走らせて本来の速度に戻るか見る」という予定していた安価な実験は**前提を失ったので中止**した。時間圧縮が無いなら、fpsを下げても意味がない。

---

### 11. 新候補の浮上：学習の更新回数不足

Section 8 で発掘した学習設定を並べ直すと、M1Mac時代とBTO時代で**勾配更新回数が3〜4倍違う**ことが分かる。

| | データ | batch | steps | **勾配更新回数** | サンプル数 | エポック |
|---|---|---|---|---|---|---|
| M1Mac `_150` | 60,936f | **32** | 12,000 | **12,000** | 384,000 | 6.30 |
| M1Mac `_100` | 60,936f | 32 | 8,000 | 8,000 | 256,000 | 4.20 |
| BTO Day1 | 21,103f | 8 | 20,000 | 20,000 | 160,000 | 7.58 |
| BTO Day2 | 38,384f | 8 | 36,000 | **36,000** | 288,000 | 7.50 |
| BTO Day3 | 55,928f | 8 | 52,000 | **52,000** | 416,000 | 7.44 |

**エポック数（見たサンプル数）は同水準なのに、勾配更新回数だけが 1/3〜1/4。** 学習率はどちらも `1e-5` 固定。AdamW で lr を据え置いたままバッチだけ4倍にすると、実効的な学習の進み方は更新回数に強く支配されるため、M1Mac時代のポリシーは**単純に学習が足りていなかった**可能性がある（仮説であり、まだ検証中）。ACTが収束不足だと行動分布がぼやけ、時刻ごとに違うモードを出して振動する、というのはカクつきの説明として筋が通る。

皮肉なことに、**Build Log #008 で実測した「batch_sizeを上げても samples/s は変わらない」がここに効く。** 当時 batch_size=32 を選んだことに速度上のメリットは無く、同じ実時間で更新回数だけを1/4に減らしていたことになる。#008 で自分が書いた教訓「学習率を固定したまま batch_size だけ変えると比較できない」の実例が、過去の自分の設定に埋まっていた。

さらに、**Day2ポリシー（BTO収集・BTO学習）の動きが滑らかだった**という事実が容疑者を絞る。Day1〜Day3 も M1Mac時代と同じ `temporal_ensemble_coeff: None` / `n_action_steps: 100` で学習されているのに滑らかなので、**B（チャンク継ぎ目）は単独では原因になりえない**。

| 仮説 | 状態 |
|---|---|
| 推論HW速度 | 棄却（Build Log #008） |
| A1/A2 データの質 | **棄却**（Section 10） |
| D データ不足・単一カメラ由来の多峰性 | **後退**。M1の150ep/60,936f は Day2 の 100ep/38,384f より多い |
| B チャンク継ぎ目 | **後退**。Day1-3 も同条件で滑らか |
| **F 更新回数不足（bs=32 / 12,000 steps）** | **最有力**。M1側だけに存在する差 |

---

### 12. Day3失敗の原因調査①：物理的到達限界の検証 → 棄却

Day3 に戻る。学習は健全に収束している（loss 0.105）のに遠い位置を掴めない。ここで見落としやすい対抗仮説がある。

> **遠い位置は、そもそもフォロワーアームが物理的に届いていないのではないか。**

アームを伸ばしきる姿勢は重力モーメントが最大になる姿勢でもある。テレオペ収集中にリーダーの指令（`action`）にフォロワー（`observation.state`）が追従できていなかったなら、データ自体が「指令はしたが到達していない」記録になっていて、ポリシーがどれだけ正確に再現しても物理的に届かない。この場合、**Day4でデータを増やしても改善しない**。

`tools/tracking_error.py` を作成し、Day1／Day2／Day3 のエピソード区間で追従誤差 `|action - state|` を比較した。

```bash
python3 tools/tracking_error.py \
  /mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921
```

```
==============================================================================
追従誤差 |action - state|  （単位: 正規化前の関節値）
==============================================================================
関節                      Day1 (ep 0-49)     Day2 (ep 50-99)   Day3 (ep 100-149)
------------------------------------------------------------------------------
shoulder_pan.pos       1.248     5.407     1.518     5.846     1.525     6.022
shoulder_lift.pos      2.800    10.681     3.432    14.813     4.002    16.132
elbow_flex.pos         3.136     9.758     3.724    13.275     4.016    14.945
wrist_flex.pos         1.403     6.154     1.990     8.879     2.214     8.879
wrist_roll.pos         1.970    10.549     2.328    11.077     2.390    10.989
gripper.pos            2.401     8.515     3.095    12.775     2.671     8.975
（左=平均 / 右=95%点）

==============================================================================
各関節の指令レンジ（Day3 が本当に新しい領域を含むかの確認）
==============================================================================
関節                      Day1 (ep 0-49)     Day2 (ep 50-99)   Day3 (ep 100-149)
------------------------------------------------------------------------------
shoulder_pan.pos       -56.3      13.8     -56.7      28.1     -56.1      23.1
shoulder_lift.pos     -106.9      33.8    -107.1      41.7    -107.2      64.0
elbow_flex.pos         -34.8      98.2     -34.5      98.3     -58.0      98.2
wrist_flex.pos          -0.2     103.6     -35.7      98.6     -30.5     102.4
wrist_roll.pos         -21.0     127.4     -21.9     121.5     -19.6     118.3
gripper.pos              0.0      64.6       0.0      88.9       0.0      59.7
（左=min / 右=max）
```

読み取れたこと：

- 追従誤差は Day3 がやや大きい（shoulder_lift 4.00 vs Day1 2.80）が、**同じオーダー**。3〜5倍に跳ねるような破綻はしていない
- **Day3 は確かに新しい関節領域を含んでいる**：`shoulder_lift` の最大が **64.0**（Day2 は 41.7）、`elbow_flex` の最小が **-58.0**（Day2 は -34.5）。前方リーチ方向に明確に拡張されている
- 一方 `shoulder_pan` のレンジはほぼ変わらない（-56〜23）。今回広げたのは**左右ではなく前方向**だった

さらに、「新領域だけを取り出したときの追従誤差」を測った（次節のスクリプトで同時に算出）。

```
新領域 vs 既知領域での追従誤差（Day3のみ）
関節                        既知領域         新領域       比
shoulder_pan.pos         1.629       0.782    0.48x
shoulder_lift.pos        4.252       2.208    0.52x
elbow_flex.pos           4.192       2.751    0.66x
wrist_flex.pos           2.301       1.587    0.69x
wrist_roll.pos           2.557       1.191    0.47x
gripper.pos              2.611       3.098    1.19x
```

**新領域のほうが追従誤差は小さい**（0.48〜0.69倍）。伸ばしきった姿勢でもフォロワーは指令どおり到達している（伸ばす局面はゆっくり動かすので、むしろ追従が良い）。

**物理的到達限界の仮説は棄却。** Day4でデータを足す方針は正しい、と裏付けが取れた。

---

### 13. Day3失敗の原因調査②：新領域のカバレッジ測定

Day1+Day2 の到達範囲（`shoulder_lift ≤ 41.7`、`elbow_flex ≥ -34.8`）を「既知領域」、それを超える部分を「新領域＝遠い位置」と定義して、フレーム数を数えた。

```bash
python3 -c "
import json, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path('/mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921')
info=json.loads((ROOT/'meta'/'info.json').read_text()); J=info['features']['action']['names']
df=pd.concat([pd.read_parquet(f) for f in sorted((ROOT/'data').rglob('*.parquet'))]).sort_values(['episode_index','frame_index'])
act=np.stack(df['action'].to_numpy()).astype(float); sta=np.stack(df['observation.state'].to_numpy()).astype(float)
ep=df['episode_index'].to_numpy(); err=np.abs(act-sta)
li,ei=J.index('shoulder_lift.pos'),J.index('elbow_flex.pos')
d3=ep>=100
lift_hi=act[~d3,li].max(); elb_lo=act[~d3,ei].min()
print(f'既知領域の境界: shoulder_lift <= {lift_hi:.1f},  elbow_flex >= {elb_lo:.1f}')
new=(act[:,li]>lift_hi)|(act[:,ei]<elb_lo)
for lab,m in (('Day1+2',~d3),('Day3',d3)):
    print(lab, m.sum(), (m&new).sum(), f'{(m&new).sum()/m.sum()*100:.1f}%')
eps_with_new=sorted(set(ep[new&d3]))
cnt=[(new&(ep==e)).sum() for e in eps_with_new]
print('新領域を含むDay3エピソード数:', len(eps_with_new), '/ 50')
print('平均', np.mean(cnt), '中央値', np.median(cnt))
"
```

```
既知領域の境界: shoulder_lift <= 41.7,  elbow_flex >= -34.8

区間             総frames     新領域frames       割合
Day1+2           38384             0     0.0%
Day3             17544          2146    12.2%

新領域を含むDay3エピソード数: 25 / 50
そのエピソード内の新領域frames: 平均 86 / 中央値 69 (1エピソード平均351frames中)
```

**これが Day3 が失敗した理由の定量的な答え。**

1. **データセット全体 55,928フレームのうち、遠い位置は 2,146フレーム＝3.8% しかない。** 7.44エポックの一様サンプリングで、416,000サンプルのうち新領域は約16,000。残り96%に埋もれている。掴めないのではなく、**そこを学ぶ機会がほとんど与えられていなかった**
2. **「遠くに置いた」つもりの50エピソードのうち、実際に既知領域を超えたのは25エピソード＝半分だけ。** 残り半分は Day2 までの範囲内で完結していた。体感で「遠くに置いた」と思っていた位置の半分は、実は既知の範囲だった
3. 新領域を含むエピソードでも、その中で新領域にいるのは平均86フレーム（1エピソード平均351フレーム中）。エピソードの大半はホームポジションからの往復に費やされる

「一気に範囲を広げたぶん、カバーしたい空間に対して50エピソードでは全く足りなかった」という直感が、**3.8% / 25-of-50 という数字で裏付けられた**形になる。

---

### 14. M1Macデータの再学習

Section 11 の仮説F（更新回数不足）を検証する。**データもハードウェアも固定し、学習レシピだけを差し替える** — Build Log #008 の対照実験の正統な続き。

```bash
# M1Macデータを、Day1-3と同じレシピ（bs=8, 7.5エポック）で学習し直す
# 60,936 frames × 7.5 / 8 ≈ 57,000 steps
lerobot-train \
  --dataset.repo_id=emboss369/so101_lego_2cam_v1_20260617_192936 \
  --policy.type=act \
  --policy.device=cuda \
  --output_dir=/mnt/data/lerobot-outputs/train/act_m1data_retrain_bs8 \
  --job_name=act_m1data_retrain_bs8 \
  --policy.repo_id=emboss369/act-m1data-retrain-bs8 \
  --batch_size=8 \
  --steps=57000 \
  --save_freq=5000 \
  --wandb.enable=false \
  2>&1 | tee /mnt/data/lerobot-outputs/logs/act_m1data_retrain_bs8.log
```

```
INFO 2026-08-08 11:11:51 ot_train.py:261 Creating dataset
Fetching 6 files: 100%|██████████| 6/6 [00:01<00:00,  3.21it/s]
Fetching 17 files: 100%|██████████| 17/17 [00:24<00:00,  1.43s/it]
INFO 2026-08-08 11:12:19 ot_train.py:295 Creating policy
INFO 2026-08-08 11:12:19 ot_train.py:407 cfg.steps=57000 (57K)
INFO 2026-08-08 11:12:19 ot_train.py:408 dataset.num_frames=60936 (61K)
INFO 2026-08-08 11:12:19 ot_train.py:409 dataset.num_episodes=150
INFO 2026-08-08 11:12:19 ot_train.py:412 Effective batch size: 8 x 1 = 8
Training:   0%|          | 133/57000 [00:29<2:53:48,  5.45step/s]
```

終盤：

```
Training:  99%|█████████▉| 56400/57000 [2:52:56<01:50,  5.45step/s]
step:56K smpl:451K ep:1K epch:7.40 loss:0.137 grdn:9.290 lr:1.0e-05 smp/s:44 mem_gb:3.73 l1_loss:0.135 kld_loss:0.000
step:57K smpl:453K ep:1K epch:7.43 loss:0.139 grdn:9.400 lr:1.0e-05 smp/s:44 mem_gb:3.73 l1_loss:0.137 kld_loss:0.000
step:57K smpl:454K ep:1K epch:7.46 loss:0.140 grdn:9.545 lr:1.0e-05 smp/s:44 mem_gb:3.73 l1_loss:0.138 kld_loss:0.000
step:57K smpl:456K ep:1K epch:7.48 loss:0.136 grdn:9.017 lr:1.0e-05 updt_s:0.182 data_s:0.001 smp/s:44 mem_gb:3.73 l1_loss:0.134 kld_loss:0.000
INFO 2026-08-08 14:07:06 ot_train.py:655 Checkpoint policy after step 57000
Training: 100%|██████████| 57000/57000 [2:54:47<00:00,  5.43step/s]
INFO 2026-08-08 14:07:07 ot_train.py:741 End of training
INFO 2026-08-08 14:07:25 etrained.py:326 Model pushed to https://huggingface.co/emboss369/act-m1data-retrain-bs8
```

**11:12:19開始 → 14:07:07完了、所要時間 2時間54分47秒**（見積もり2時間55分に対してほぼ一致）。最終 **loss 0.136 / l1 0.134 / kld 0.000**。

| | データ | steps | 勾配更新回数 | 最終 loss | l1 |
|---|---|---|---|---|---|
| BTO Day3 | 55,928f（レゴ→ケース） | 52,000 | 52,000 | 0.105 | 0.102 |
| **M1再学習** | 60,936f（レゴ掴み） | 57,000 | **57,000** | **0.136** | 0.134 |
| M1 元 `_150` | 60,936f（同上） | 12,000 | **12,000** | 記録なし | 記録なし |

M1データのほうが loss がやや高い（0.136 vs 0.105）が、**タスクもデータも別物なのでこの差だけでは何も結論づけられない**。比較すべきは「同じデータを bs=32／12,000steps で学習した元のポリシー」との実機挙動。元のポリシーの最終lossは記録が残っておらず不明（→ 学習ログを残す運用の必要性）。

#### 実機評価の手順（次に実行）

体感の記憶に頼ると「前はもっとカクカクだった気がする」というバイアスが入るため、**新旧を連続で、同じ位置・同じ照明で交互に**回す。

新（再学習・bs=8 / 57,000steps）：

```bash
lerobot-rollout \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --policy.path=emboss369/act-m1data-retrain-bs8 \
    --fps=30 \
    --task="Grab the yellow lego block" \
    --display_data=true \
    --duration=0
```

旧（M1Mac時代・bs=32 / 12,000steps）— 直後に同じ配置で：

```bash
lerobot-rollout \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --policy.path=emboss369/act_so101_lego_2cam_v1_150 \
    --fps=30 \
    --task="Grab the yellow lego block" \
    --display_data=true \
    --duration=0
```

見るポイント：

1. **カクつきの有無**（本命。仮説Fの判定）
2. **カクつきが周期的か**（約3.3秒＝100ステップごとに引っかかるなら、残っているのは仮説B＝チャンク継ぎ目）
3. 掴めるかどうか（今回の主眼ではないが、更新回数の増加で精度も変わる可能性がある）

判定基準（事前に決めておく）：

- **カクつきが消えたら F 確定** — 原因はM1MacでもGPUでもなく、自分の学習設定（batch_size=32／12,000steps）だった
- **消えなければ B が残る** — チャンク継ぎ目。`temporal_ensemble_coeff` を有効にして再評価する

どちらに転んでも候補を1つ潰せる。

なお、`--policy.path` を付けて `lerobot-record` を回せばポリシーの実行結果をデータセットとして残せるはずで、それを `tools/action_forensics.py` にかければ教示データの基準値（jerk比 0.377〜0.392、4Hz以上パワー比 0.0002）と直接比較できる客観値が得られる。「カクカクして見えた」を数値で言えるようになるので、記事化するなら有用。ただし `--policy.path` 併用時のフラグ構成はこの環境で未検証。

---

### 15. M1再学習ポリシーの実機評価 → 仮説F も棄却

翌8/9夜、再学習した `emboss369/act-m1data-retrain-bs8` を実機で評価した。

```bash
lerobot-rollout \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --policy.path=emboss369/act-m1data-retrain-bs8 \
    --fps=30 \
    --task="Grab the yellow lego block" \
    --display_data=true \
    --duration=0
```

```
INFO 2026-08-09 20:35:16 /context.py:209 Policy loaded: type=act, device=cuda
INFO 2026-08-09 20:35:24 ence/sync.py:76 SyncInferenceEngine initialized (device=cuda, action_keys=6)
INFO 2026-08-09 20:35:24 _rollout.py:223 Robot: so100_follower | FPS: 30 | Duration: infinite
INFO 2026-08-09 20:35:24 gies/base.py:53 Base strategy control loop started
WARNING 2026-08-09 20:35:24 gies/base.py:75 Record loop is running slower (2.9 Hz) than the target FPS (30.0 Hz). Dataset frames might be dropped and robot control might be unstable. Common causes are: 1) Camera FPS not keeping up 2) Policy inference taking too long 3) CPU starvation
2026-08-09T11:35:52.912433Z  INFO re_grpc_server: Exceeded gRPC proxy server memory limit (1.0 GiB). Dropping the oldest log messages.
^CINFO 2026-08-09 20:36:36 s/process.py:61  Shutdown signal 2 received. Cleaning up…
INFO 2026-08-09 20:36:41 _rollout.py:241 Rollout finished
```

**結果：動きはあまり変わらず、ブロックも掴めなかった。** 勾配更新回数を12,000→57,000（4.75倍）にしても、カクつきは解消しなかった。

**→ 仮説F（更新回数不足）も棄却。**

#### 2.9 Hz 警告の検証（＝#008の結論が崩れていないかの確認）

ログに `Record loop is running slower (2.9 Hz)` が出ており、これが持続的なら「BTO側は30Hz出ている」という Build Log #008 の前提が崩れる。ソースを確認した。

```bash
find . -name 'base.py' -path '*strateg*'
# -> ./src/lerobot/rollout/strategies/base.py
```

```python
# src/lerobot/rollout/strategies/base.py:55-77
while not ctx.runtime.shutdown_event.is_set():
    loop_start = time.perf_counter()
    ...
    dt = time.perf_counter() - loop_start
    if (sleep_t := control_interval - dt) > 0:
        precise_sleep(sleep_t)
    else:
        logger.warning(
            f"Record loop is running slower ({1 / dt:.1f} Hz) than the target FPS ({cfg.fps} Hz). ..."
        )
```

警告は**ループ内で毎周期チェックされる**実装（`else` 節なので、遅延した周期ごとに出力される）。ところが実際のログでは **20:35:24 に1回だけ**で、ループは 20:36:36 まで72秒間（約2,000周期）走っている。

**したがって 2.9 Hz は初回イテレーションのウォームアップコスト**（初回CUDA推論・cuDNNのオートチューニング・カメラ初フレーム取得）であり、以降は30Hzに乗っていたと判断できる。

独立した傍証もある。同じログで rerun が **28秒で 1 GiB** を溜めている（20:35:24 開始 → 20:35:52 に `Exceeded gRPC proxy server memory limit`）。640×480×3バイト × 2カメラ ≒ 1.8 MB/フレームなので、この流量は約30fps相当。2.9 Hz なら 1 GiB 到達に3分以上かかるはずで、映像は30fpsで流れていたことになる。

#### 検証：rerun を切って警告回数を数える

推測で終わらせず、`--display_data=false` で回して警告の回数を直接数えた。

```bash
lerobot-rollout \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --policy.path=emboss369/act-m1data-retrain-bs8 \
    --fps=30 \
    --task="Grab the yellow lego block" \
    --display_data=false \
    --duration=0 \
    2>&1 | tee /mnt/data/lerobot-outputs/logs/rollout_m1retrain_nodisplay.log
```

```bash
LOG=/mnt/data/lerobot-outputs/logs/rollout_m1retrain_nodisplay.log
echo "遅延警告の回数: $(grep -c 'running slower' $LOG)"
grep 'running slower' $LOG | head -5
```

```
遅延警告の回数: 1
WARNING 2026-08-09 20:47:57 gies/base.py:75 Record loop is running slower (5.2 Hz) than the target FPS (30.0 Hz). ...
```

**警告はループ開始と同じ秒に1回だけ**（今回は 5.2 Hz。ウォームアップの実測値は実行ごとに 2.9〜5.2 Hz とばらつく）。**制御ループは30Hzで回っていることが確定した。**

- **仮説C（推論ループの遅延）は棄却で確定**
- Build Log #008 の「推論ハードウェア速度は主因ではない」という結論は**維持**
- rerun（`--display_data=true`）の負荷も、動作への影響という意味では容疑から外れた

（危うくこの1行を根拠に前提を取り違えるところだった。警告の実装がワンショットか毎周期かを確認せずに解釈しないこと。そして「出ていない側の情報」＝72秒間で1回しか出ていないこと、が決め手になった）

#### 別の問題の発見：USBカメラの脱落

上記の検証中、Day1ポリシーで回した1本目が途中でクラッシュした。

```
WARNING 2026-08-09 20:45:30 a_opencv.py:467 Error reading frame in background thread for OpenCVCamera(0): OpenCVCamera(0) read failed (status=False).
（同警告が11回連続）
RuntimeError: OpenCVCamera(0) exceeded maximum consecutive read failures.
WARNING 2026-08-09 20:45:30 ies/core.py:157 Could not return to initial position: OpenCVCamera(0) read thread is not running.
[ WARN:0@36.108] global cap_v4l.cpp:804 requestBuffers VIDEOIO(V4L2:/dev/video0): failed VIDIOC_REQBUFS: errno=19 (No such device)
```

`errno=19 (No such device)` は、**実行中に `/dev/video0`（wrist カメラ）がUSBから消えた**ことを意味する。ソフトのバグではなく、USB側の問題（給電不足・帯域・接触）の可能性が高い。次の実行（20:47:57）では正常に接続できているため、間欠的な事象。

これが重要なのは、**今回はクラッシュしたから気づけたが、軽度なら気づかないまま進む**こと。`read_latest()` は背景スレッドが持つ最新フレームを返す実装なので、スレッドが一時的に詰まれば**ポリシーは古い画像を見たまま動き続ける**。これは「カクつき」や「掴み損ね」として現れうる。

密度仮説を否定するものではないが、**観測系の安定性という別軸の変数**として記録しておく。今後ロールアウトのたびに確認する：

```bash
grep -c 'read failed' <ログ>
```

---

### 16. 密度仮説：Day3 の失敗と M1Mac の謎は同じ原因だった

仮説F が棄却され、残った説明はデータ側に戻る。ただし Section 10 で棄却した「データの質（滑らかさ）」ではなく、**データの密度**である。

M1Mac 時代のレゴ掴みは、**最初から約20cm四方の範囲にランダムにブロックを置いていた**。対して今回のBTO Day1 は約2cm四方のほぼ同じ位置に置いていた。範囲に対してサンプル数が全く足りていなかったのではないか——これは **Day3 の失敗とまったく同じ構造**である。

| | 配置範囲 | エピソード数 | 結果 |
|---|---|---|---|
| BTO Day1 | 約2cm四方 | 50 | 掴める（同じ位置のみ） |
| BTO Day2 | ＋左右に拡張 | +50 | 掴める（拡張範囲内で汎化） |
| BTO Day3 | ＋前方に大きく拡張 | +50（実際に新領域に入ったのは25） | **掴めない** |
| M1Mac レゴ | **約20cm四方にランダム** | 150 | **掴めない・カクつく** |

Section 11 で仮説D（データ不足由来の多峰性）を「M1の150ep/60,936f は Day2 の100ep/38,384f より多いから」という理由で後退させたが、**これは指標の取り方が誤っていた**。効くのはフレーム総数ではなく「カバーする範囲あたりの密度」である。

さらにこの仮説は**カクつきの説明にもなる**。学習データが疎な位置ではACTの行動分布が多峰になり、時刻ごとに違うモードを出力して振動しうる。「掴めない」と「カクつく」が同じ原因から出ることになる。

#### 密度の測定

`tools/grasp_spread.py` を作成。把持の瞬間（`gripper.pos` が最も急に閉じたフレーム）の関節姿勢 `(shoulder_pan, shoulder_lift, elbow_flex)` を対象物の配置位置の代理指標とし、そのばらつきから「配置範囲」と「密度」を推定する。

```bash
BTO=/mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921
M1=$(ls -d /mnt/data/huggingface/hub/datasets--emboss369--so101_lego_2cam_v1_20260617_192936/snapshots/*)
python3 tools/grasp_spread.py \
  "$BTO:0-49:BTO Day1 (2cm四方・50ep)" \
  "$BTO:50-99:BTO Day2 (＋左右・50ep)" \
  "$BTO:100-149:BTO Day3 (＋前方・50ep)" \
  "$M1::M1Mac レゴ (20cm四方ランダム・150ep)"
```

```
[BTO Day1 (2cm四方・50ep)]  エピソード数 = 50
  関節                          平均      標準偏差       5%点      95%点    幅(90%)
  shoulder_pan.pos         -46.8      4.80     -51.5     -36.6      14.9
  shoulder_lift.pos          9.3     11.14      -5.6      27.7      33.3
  elbow_flex.pos            -2.4     14.21     -29.3      16.8      46.1
  配置範囲の代理面積 (pan幅 × lift幅) =      495.4
  ★密度 = エピソード数 / 面積        =     0.1009 ep/unit²

[BTO Day2 (＋左右・50ep)]  エピソード数 = 50
  shoulder_pan.pos         -45.8      5.09     -50.7     -36.8      13.9
  shoulder_lift.pos         15.6      9.78      -2.3      30.0      32.3
  elbow_flex.pos           -12.6     12.23     -30.9       6.7      37.6
  配置範囲の代理面積 (pan幅 × lift幅) =      447.3
  ★密度 = エピソード数 / 面積        =     0.1118 ep/unit²

[BTO Day3 (＋前方・50ep)]  エピソード数 = 50
  shoulder_pan.pos         -45.9      8.92     -52.0     -33.3      18.7
  shoulder_lift.pos         11.4      8.92      -4.7      24.1      28.7
  elbow_flex.pos            -5.8     13.59     -25.0      17.8      42.8
  配置範囲の代理面積 (pan幅 × lift幅) =      536.4
  ★密度 = エピソード数 / 面積        =     0.0932 ep/unit²

[M1Mac レゴ (20cm四方ランダム・150ep)]  エピソード数 = 150
  shoulder_pan.pos         -26.5     18.29     -55.7       1.7      57.4
  shoulder_lift.pos          6.6     30.39     -50.6      45.0      95.6
  elbow_flex.pos            -2.7     35.26     -51.1      58.0     109.1
  配置範囲の代理面積 (pan幅 × lift幅) =     5485.6
  ★密度 = エピソード数 / 面積        =     0.0273 ep/unit²
```

**M1Mac のデータは BTO の約11倍の範囲を、3倍のエピソード数でカバーしていた。実効密度は約1/4。** 各関節のばらつきも桁が違う（`shoulder_lift` の標準偏差 30.39 vs 9〜11、`elbow_flex` 35.26 vs 12〜14）。

言い換えると、**M1Mac時代の20cm四方をDay1と同じ密度で埋めるには、150ではなく約550エピソード必要**だった計算になる（150 × 0.1009 / 0.0273 ≒ 554）。

測定の限界も記録しておく：BTO Day1 は「約2cm四方」のはずなのに代理面積 495 が出ている。これは把持姿勢そのもののばらつき（同じ位置でもアームの通り方が毎回違う）が乗った**ノイズフロア**であり、BTO 3群がいずれも 447〜536 に固まっていることがその証拠。M1Mac の 5,486 はそのフロアの10倍以上なので、差は実在すると判断できる。この指標は絶対値ではなく**群間比較にのみ**使える。

また Day3 の代理面積が 536 と Day1（495）とほぼ変わらないのは、5〜95%点で刈っているため「遠い位置」が裾に落ちているためで、**新領域に入ったのが25/50だった**という Section 13 の測定と整合する。

---

### 17. ハードウェアトラブル：USB切断の原因はジャンパーの脱落だった

Section 15 の評価の直後から、ロールアウトが連続してクラッシュするようになった。今度はサーボ側である。

```
WARNING 2026-08-09 21:00:27 ies/core.py:157 Could not return to initial position:
    Failed to sync read 'Present_Position' on ids=[1, 2, 3, 4, 5, 6] after 1 tries. [TxRxResult] Port is in use!
...
  File ".../serial/serialposix.py", line 673, in flush
    termios.tcdrain(self.fd)
termios.error: (5, 'Input/output error')
FATAL: exception not rethrown
中止 (コアダンプ)
```

#### 調査：カーネルログ

```bash
journalctl -k --since "20:45" --no-pager | grep -iE 'usb|xhci|cdc_acm|uvcvideo|disconnect|reset'
```

```
20:56:49  usb 3-2: USB disconnect, device number 3      ← Innomaker（wrist）
20:56:53  usb 3-2: USB disconnect, device number 4
20:57:49  usb 3-2: USB disconnect, device number 5
20:57:46  usb 5-1: USB disconnect, device number 2      ← C920（front）
20:58:08  usb 5-1: reset high-speed USB device number 4
21:00:05  usb 5-2: USB disconnect, device number 3      ← アームのシリアル（1a86:55d3）
21:00:06  cdc_acm 5-2:1.0: ttyACM2: USB ACM device
21:00:27  usb 5-2: USB disconnect, device number 5      ← ★クラッシュの瞬間
21:00:27  cdc_acm 5-2:1.0: ttyACM1: USB ACM device
```

**実行中にデバイスがUSBから消えて再列挙されていた。** `$FOLLOWER_ARM` が指していたノードが無効になり、開いていたファイルディスクリプタが死んで `Input/output error` になっていた。

udev は正しく設定されていた（シリアル番号でマッチしているのでノード名が変わってもリンクは追従する）ため、命名の問題ではない。

```
/etc/udev/rules.d/99-so101.rules:
  SUBSYSTEM=="tty", ATTRS{serial}=="5A7A018619", SYMLINK+="so101_follower"
  SUBSYSTEM=="tty", ATTRS{serial}=="5A4B047951", SYMLINK+="so101_leader"
```

#### 誤った仮説：USB帯域の競合

`lsusb -t` でトポロジを確認したところ、次の構成だった。

```
Bus 005 (USB2.0 / 2ポート, pci 0e:00.4)
  ├─ Port 1: C920 PRO HD Webcam   ← front カメラ
  └─ Port 2: USB Single Serial    ← フォロワーアーム  ★切断したのはこれ
Bus 001 (USB2.0 / 12ポート, pci 0b:00.0)
  └─ Port 2: USB Single Serial    ← リーダーアーム（切断ゼロ）
```

「同じ2ポートのコントローラをカメラとサーボバスが共有していて、カメラが帯域を確保したときにシリアルが巻き添えになっている」と推論し、ポートの差し替えを提案した。

**これは誤りだった。** 「リーダーはBus 1で無事、フォロワーはBus 5で落ちる」という相関を読み過ぎた。実際の差はバスではなかった。

#### 真の原因：ジャンパーキャップの脱落

差し替え後もクラッシュが再現し、そこでユーザーが物理的な原因を発見した。**アームの振動で、サーボドライバ基板のジャンパーキャップが抜け落ちていた。**

基板は **Seeed Studio Bus Servo Driver Board for XIAO V1.0**。抜けたのは回路図上の `J4`（シルク "Jumper Cap"）。

公式回路図で機能を確定した：

```
Type-C 5V ──► U3 (TPS7A0533, 3.3V/200mA LDO) ──► LDO_3V3
                                                    │
                                            J4 ◄────┘  ← このジャンパー
                                             │
                                          +3V3 ──┬─► U7 CH343P の VIO / V3
                                                 ├─► U4 SN74LVC1G126（バッファ）
                                                 ├─► U5 SN74LVC1G125（バッファ）
                                                 └─► TXEN 回路（Q1 MMBT3906）のプルアップ
```

**`J4` は「USB側の3.3V LDO出力」を「基板のメイン `+3V3` レール」に繋ぐスイッチ。** `+3V3` は **USB-シリアル変換IC（CH343P）の I/O 電源**と、**サーボの `Data` 線を駆動する半二重の方向制御ロジック（U4/U5）** を動かしている。つまり PC とサーボの間の通信経路そのものの電源。

この基板は電源供給元が2通りある：

| 使い方 | `+3V3` の供給元 | J4 |
|---|---|---|
| XIAO を挿して UART で駆動 | XIAO の 3V3 ピン | 不要（デフォルト非短絡） |
| **USB-C で PC から駆動** | **基板上の LDO** | **必須** |

本プロジェクトは後者（XIAOソケットは空、`lsusb` に出るのは `1a86:55d3` ＝ CH343P）。**`+3V3` に LDO 以外の供給元がないため、J4 は必須の結線**だった。抜けた瞬間に CH343P が落ちてUSBデバイスが消え、同時にサーボ通信路も断たれる——観測された症状と完全に一致する。

なお、サーボ本体の電源は `J1`（DC 5-12V）から3Aで直接供給されており **J4 とは無関係**。「サーボには電気が来ているのに通信だけ死ぬ」状態になる。

（基板右上の `JP1`/`JP2` は別物。CH343P の TXD/RXD を XIAO の D6/D7 に繋ぐハンダジャンパで、回路図の改訂履歴 "Use JP1 and JP2 instead of R12 and R18" がこれにあたる）

出典：
- [Bus Servo Driver Board | Seeed Studio Wiki](https://wiki.seeedstudio.com/bus_servo_driver_board/)
- [Servo Driver Board for Seeed Studio XIAO v1.0 回路図PDF](https://files.seeedstudio.com/wiki/bus_servo_driver_board/202004237_Servo_Driver_Board_for_Seeed_Studio_XIAO_SCH_PDF_250225.pdf)

#### 対処

この用途では J4 は常時ONで固定してよい（XIAO の UART 駆動に切り替えない限り外す理由がない）。振動で再発するため、ジャンパーキャップ＋テープ、またはハンダブリッジで固定する。

#### 副産物：警告の感度が分かった

トラブル中のログに、判断に効く情報があった。

```
21:07:49  Record loop is running slower (5.1 Hz)   ← ウォームアップ
21:07:51  Record loop is running slower (28.8 Hz)  ← 30Hzに対して28.8Hz
```

**28.8 Hz でも警告が出る。** この警告は「1周期でも1/30秒を超えたら出る」感度で、実質ノイズに近い。逆に言えば、数千周期あるロールアウトで警告が1〜2回しか出ないのは「完全に健全」ということ。Section 15 の仮説C棄却が、想定より強く裏付けられた。

---

### 18. クリーンな条件での再評価と、動画から判明した決定的な差

ジャンパーを直したうえで、M1再学習ポリシーを再評価した。

```
INFO 2026-08-09 21:56:31 gies/base.py:53 Base strategy control loop started
WARNING 2026-08-09 21:56:31 gies/base.py:75 Record loop is running slower (5.1 Hz) ...  ← ウォームアップのみ
INFO 2026-08-09 21:57:41 s/process.py:61  Shutdown signal 2 received. Cleaning up…
INFO 2026-08-09 21:57:46 _rollout.py:241 Rollout finished
```

70秒間の実行で、カメラエラーなし・シリアル切断なし・遅延警告はウォームアップの1回のみ・正常終了。**ハードウェア障害を排除した有効な評価。**

**結果：レゴを掴めない。白いケースの方を持ち上げてしまうなど挙動が不安定。動きも滑らかでない。**

**→ 仮説F（更新回数不足）の棄却が、正当な条件下で確定した。**

#### 動画による検証：変動していた物体は2つだった

「白いケースを持ち上げる」という挙動から、「M1Mac収集時のシーンに白いケースは無く、分布外の物体だったのではないか」という疑いを持ったが、これは**外れ**だった。データセットの動画から実際にフレームを抜いて確認した。

```bash
# M1Macデータ（Hubから front カメラの動画を1本取得してフレーム抽出）
python3 -c "
from huggingface_hub import hf_hub_download
print(hf_hub_download('emboss369/so101_lego_2cam_v1_20260617_192936',
      'videos/observation.images.front/chunk-000/file-000.mp4', repo_type='dataset'))
"
ffmpeg -i <上記パス> -vf "select='eq(n\,30)+eq(n\,900)+eq(n\,2400)',scale=480:-1,tile=3x1" -frames:v 1 m1_front.png

# BTOデータ（ローカル）
B=/mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921/videos/observation.images.front/chunk-000
ffmpeg -i $B/file-000.mp4 -vf "select='eq(n\,30)+eq(n\,1500)',scale=480:-1,tile=2x1" -frames:v 1 bto_early.png
ffmpeg -i $B/file-002.mp4 -vf "select='eq(n\,30)+eq(n\,1500)',scale=480:-1,tile=2x1" -frames:v 1 bto_late.png
```

**M1Macデータのシーン**（[images/009-m1-scene-front.png](images/009-m1-scene-front.png)）:

| フレーム | 白いケースの位置 | レゴの位置 |
|---|---|---|
| 1枚目 | 左寄り | 右上 |
| 2枚目 | 中央 | 右上（やや下） |
| 3枚目 | 左上 | ケース内 |

白いケースは最初から存在しており、分布外ではなかった（タスク文字列は `Grab the yellow lego block` だが、実際に収集されていた動作は Day1-3 と同じ「レゴをケースに入れる」だった）。

**しかし、白いケースの位置が毎回変わっている。**

**BTOデータのシーン**（[images/009-bto-scene-day1.png](images/009-bto-scene-day1.png) / [images/009-bto-scene-day3.png](images/009-bto-scene-day3.png)）：Day1 も Day3 も、**白いケースは毎回まったく同じ位置**（フレーム左中央）。動くのはレゴブロックだけ。

| | 変動する物体 | 配置空間 |
|---|---|---|
| **M1Mac レゴ** | **レゴ ＋ 白いケース（2つとも動く）** | 2物体 × 2次元 |
| **BTO Day1-3** | レゴのみ（ケースは固定） | 1物体 × 2次元 |

**M1Macのデータは、変動する物体が2つあった。** 配置の組み合わせ空間は積で効くので、「20cm四方」という広さの問題に加えて、**そもそも変動の次元が倍**だった。150エピソードでは、同じ「レゴとケースの位置関係」がほぼ二度と再現しない。

さらに、今日観察された「**白いケースの方を持ち上げてしまう**」という挙動もこれで説明がつく。学習データの中でケースは「毎回違う場所にある、アームが向かっていく白い物体」だったため、ポリシーにとって掴む対象とケースの区別が曖昧になっている可能性が高い。

Section 16 の密度測定（把持姿勢のばらつき＝約11倍の範囲、密度1/4）は**レゴの位置だけを見た値**であり、ケースの変動を含めれば実効的な疎さはさらに大きい。**密度仮説は、当初の見立てよりも強く支持された。**

---

## 結果（成功／失敗／保留）

- **失敗：Day3（遠い位置）。** 50エピソード追加・52,000ステップで再学習し loss 0.105 まで収束したが、遠い位置のブロックは掴めず、ずれた。原因は測定済み（下記）
- **成功：Day3 失敗の原因を定量化。** 遠い位置のデータは全体の **3.8%（2,146 / 55,928 frames）** しかなく、さらに「遠くに置いた」つもりの50エピソードのうち実際に新領域に入っていたのは **25エピソードだけ**だった
- **成功：「M1Macデータの質」仮説を棄却。** M1Mac収集データはBTO収集データと同等に滑らか（連長3以上 2.13% vs 1.59%、jerk比 0.392 vs 0.377、4Hz以上パワー比 いずれも0.0002）。事前に決めた反証条件どおりに棄却した
- **成功：「物理的到達限界」仮説を棄却。** 新領域での追従誤差はむしろ既知領域より小さい（0.48〜0.69倍）。アームは指令どおり届いている
- **成功：新候補Fの発掘。** M1Mac時代のポリシーは batch_size=32／12,000steps で、BTO時代（bs=8／36,000〜52,000steps）に対し**勾配更新回数が1/3〜1/4**だった
- **成功：`timestamp` が合成値（`frame_index/fps`）であることを確認。** 収集ループの実速度はタイムスタンプからは原理的に判定できない
- **成功：仮説F（更新回数不足）を棄却。** M1Macデータを Day1-3 と同じレシピ（bs=8／57,000steps、勾配更新回数4.75倍）で学習し直したが、実機での動きはほとんど変わらず、ブロックも掴めなかった。ジャンパー修理後のクリーンな条件で再評価しても同じ結果（掴めない／白いケースを持ち上げる／滑らかでない）
- **成功（今日最大の発見）：M1Macデータでは変動する物体が2つ（レゴ＋白いケース）だった。** 動画のフレームを実際に確認したところ、BTO Day1-3 は白いケースが毎回同じ位置なのに対し、M1Macデータはケースの位置も毎回変わっていた。配置の組み合わせ空間が積で効くため、「20cm四方」に加えて**変動の次元そのものが倍**だった。「白いケースを持ち上げる」という今日の挙動もこれで説明がつく
- **成功：USBデバイス切断の原因を特定。** 振動でサーボドライバ基板（Seeed Bus Servo Driver Board for XIAO V1.0）の `J4` ジャンパーキャップが脱落していた。回路図で確認したところ、J4 は USB側 LDO の 3.3V を `+3V3` レール（CH343P の I/O 電源＋サーボData線の駆動ロジック）に繋ぐ**必須の結線**で、抜けると USB デバイスごと消える
- **訂正：USB帯域の競合（C920 とサーボバスが同一コントローラ）という仮説は誤りだった。** 「リーダーはBus 1で無事、フォロワーはBus 5で落ちる」という相関を読み過ぎた。実際の差はバスではなく、基板上のジャンパーの緩みだった
- **成功：`2.9 Hz` 警告がウォームアップ由来であることを確定。** ソースを読み（毎周期チェックされる実装）、さらに `--display_data=false` で回して警告回数を実測（**1回のみ**）。制御ループは30Hzで回っており、**仮説C（推論ループの遅延）は棄却で確定**。#008 の結論（推論HW速度は主因でない）は維持。rerun の負荷も容疑から外れた
- **発見（未解決）：USBカメラの間欠的な脱落。** ロールアウト中に `/dev/video0`（wrist）が `errno=19 (No such device)` で消え、クラッシュした。軽度なら気づかないまま「古い画像で動き続ける」ため、カクつき・掴み損ねの隠れた要因になりうる。今後ロールアウトのたびに `grep -c 'read failed'` で確認する
- **成功（今日の本丸）：密度仮説の定量化。** M1Macのレゴデータは BTO の**約11倍の範囲**を**3倍のエピソード数**でカバーしており、実効密度は **約1/4**（0.0273 vs 0.1009 ep/unit²）。Day3 の失敗（新領域が全体の3.8%）と M1Mac の失敗は、**「範囲に対してデータが疎すぎる」という同一の原因**で説明できる
- **保留：仮説B（チャンク継ぎ目）。** Day1-3 が同条件で滑らかなため単独原因ではないが、完全には消えていない
- **訂正：Section 11 で仮説D（データ不足由来の多峰性）を「M1のほうがフレーム数が多いから」という理由で後退させたのは誤り。** 効くのはフレーム総数ではなく範囲あたりの密度だった

---

## 失敗の原因・学んだこと

- **「範囲の広さ」だけでなく「変動する物体の数」で必要データ量が決まる。** 物体を1つ増やすと配置の組み合わせ空間は掛け算で増える。M1Macのデータは、レゴ20cm四方に加えてケースも動かしていたので、150エピソードでは同じ状況がほぼ二度と現れない。**汎化させたくないものは固定する**——これは制約ではなく、限られたデータを効かせるための設計判断である
- **数値解析だけでは足りず、生の動画を見て初めて分かることがあった。** 関節値の統計（Section 16）では「レゴの配置範囲が11倍」までしか見えなかった。実際にフレームを抜いて並べたら、ケースまで動いていたことが一目で分かった。**データの中身は、統計を取る前に一度目で見るべきだった**
- **今日の一番の学び：模倣学習の成否を決めるのは「エピソード数」ではなく「カバーしたい範囲あたりの密度」だった。** 同じ150エピソードでも、2cm四方に置けば足り、20cm四方にばらまけば全く足りない。「データを増やす」という言い方自体が曖昧で、「どの範囲を、どの密度で埋めるか」に言い換える必要がある
- **「掴めない」と「カクつく」は、同じ原因（データが疎）から出ている可能性が高い。** 別々の問題として2ヶ月追いかけていたが、疎な領域でACTの行動分布が多峰になれば、精度の低下と動作の振動が同時に起きる。症状を切り分けようとするあまり、原因が1つである可能性を長く見落としていた
- **自分の仮説の後退のさせ方を間違えた。** Section 11 で仮説D を「M1のほうがフレーム数が多いから」と後退させたが、比較すべきは総量ではなく密度だった。**正しい指標を選ばないと、正しい手順で間違った結論に着地する**
- **警告メッセージは、実装がワンショットか毎周期かを確認してから解釈する。** `2.9 Hz` の1行だけを見て「BTOも遅かった」と結論していたら、#008 の結論を誤って覆すところだった。72秒間で1回しか出ていないという「**出ていない側の情報**」が決め手になり、最後は `grep -c` で回数を数えて確定させた。ログは「何が出ているか」だけでなく「何回出ているか」で読む
- **相関から因果を読み過ぎた（2回目）。** 「リーダーはBus 1で無事、フォロワーはBus 5で落ちる」から帯域競合を疑ってポート差し替えを提案したが、実際は基板のジャンパーが振動で抜けていただけだった。Section 11 で仮説Dをフレーム数で後退させたのと同じ失敗パターン——**目についた差異が原因だと思い込む**。差異が2つ以上あるときは、どれが効いているか確かめてから動くべきだった
- **ソフトを3階層掘っても、原因がハードにあることがある。** 推論速度 → データの質 → 学習の更新回数、と掘り進めた同じ日に、緩んだジャンパー1個でシステム全体が落ちていた。スタックトレースは Python の奥深くを指していたが、原因は基板の上にあった
- **ハードウェア障害が混ざった状態で実験結果を解釈してはいけない。** 一度目の評価はUSB切断が起きうる状態で行っていた。結論自体は再評価でも変わらなかったが、変わっていたら誤った結論を採用していた。**評価の前に、ログにエラーが出ていないことを確認する**のを手順に入れる
- **クラッシュしてくれた不具合は運がいい。** USBカメラの脱落は今回たまたま完全に落ちたので気づけたが、間欠的に数フレーム詰まるだけなら気づかず、「なぜかカクつく」の原因不明リストに積まれていた。静かに劣化する不具合のほうが怖い
- **「範囲を広げる」は、広げた範囲に見合うデータ量とセットでないと意味がない。** Day2 の左右方向は既存の範囲に近かったので50エピソードで足りたが、Day3 で前方向に一気に広げたぶん、同じ50エピソードでは密度が全く足りなかった。データ量は「エピソード数」ではなく「カバーしたい空間に対する密度」で考える必要がある
- **「遠くに置いたつもり」の半分は、実は既知の範囲だった。** 体感と実測がずれる。収集の狙いが達成できているかは、収集後に必ずデータ側で検算すべきだった（今回は失敗してから測った）
- **学習の loss は、実機で使えるかどうかを何も保証しない。** Day3 は Day1・Day2 と同水準（0.105）まで綺麗に収束していたのに、狙った動作はできなかった。訓練データにフィットすることと、狙った汎化が得られることは別問題
- **`timestamp` が合成値だと知らずに検証していたら、完全に誤った結論を出していた。** 「30fpsと記録されている＝30Hzで収集された」は成り立たない。データの由来を確かめる前に、その数値が何を意味するのかを確かめる必要がある
- **Build Log #008 で自分が書いた教訓が、過去の自分の設定に埋まっていた。** 「学習率を固定したまま batch_size だけ変えると比較できない」——まさにそれを M1Mac 時代にやっていた。しかも #008 の実測により、その batch_size=32 には速度上のメリットが無かったことも分かっている
- **オフライン解析は安い。** 今回の3つの棄却（データの質・物理限界、および仮説Bの後退）はすべて、ロボットに触らず、GPUも使わず、学習を回している裏で完了した。実機実験の前に、手持ちのデータで答えが出せるものは出しておくほうが速い
- **反証条件を先に書いておくと判断がぶれない。** 「Δaction分布に有意差がなければ棄却する」と決めてから測ったので、結果を見てから解釈を後付けせずに済んだ
- **過去の学習の最終lossを記録していなかったため、今回の再学習（0.136）と直接比較できなかった。** 設定（`train_config.json`）はHubに残るが、結果（loss推移）は残らない。`--wandb.enable=false` で回すなら、せめて `tee` したログを捨てずに残しておくべきだった。今後は学習ログを `/mnt/data/lerobot-outputs/logs/` に必ず残す
- Hugging Face Hub の Xet CDN が 500 を返すことがある。`HF_HUB_DISABLE_XET=1` で通常のHTTP経路にフォールバックできる

---

## 次やること（一歩だけ）

- **Day4：範囲を広げるのをやめ、密度で殴る。** 今日の結論を踏まえると、選択肢は2つしかない。**(a) 対象範囲を狭く保ったまま密度を上げる**か、**(b) 広い範囲を狙うなら、それに見合う数百エピソードを覚悟する**か。Day4 は (a) を採る
  - 遠い位置の**狙う範囲そのものを絞る**（前回のように「遠く」と漠然と広げず、特定の狭い領域に固定する）
  - **50エピソード全部をその領域に入れる**（前回は25/50しか入っていなかった）。置く前に「これは `shoulder_lift > 42` に入るか」を意識する
  - 収集後、学習に入る前に `tools/tracking_error.py` と `tools/grasp_spread.py` で検算し、**「新領域を含むエピソード数 50/50」「密度が Day1 相当（約0.10 ep/unit²）に届いているか」**を確認してから学習に入る
  - 達成できれば新領域は 2,146 → 約9,600フレーム、全体の約13%（現状の3.4倍）になる見込み
  - 学習は 73,000frames × 7.5 / 8 ≈ 68,000 steps（約3時間30分）の見込み
- **`sample_weighting` の調査。** 学習設定に存在するフィールド（現在 `None`）。新領域のフレームを重点サンプリングできれば、収集を増やさずに信号比を上げられる可能性がある。APIの実態は未確認
- **収集前に「密度目標」を決める運用にする。** これまでは「50エピソード録る」と数だけ決めていた。今後は `tools/grasp_spread.py` で目標範囲の代理面積を見積もり、Day1相当の密度（約0.10 ep/unit²）を満たすエピソード数を先に算出してから収集に入る
- **`J4` ジャンパーの固定。** ジャンパーキャップ＋テープ、またはハンダブリッジ。この用途では常時ONで固定してよい（XIAO の UART 駆動に切り替えない限り外す理由がない）。振動で再発するため、挿し直しただけでは不十分
- **ロールアウト前後のヘルスチェックを手順化する。** `grep -c 'read failed'`（カメラ脱落）と `grep -c 'running slower'`（ループ遅延。1〜2回なら正常）を毎回確認してから結果を解釈する。ハードウェア障害が混ざった状態の評価は無効
- **収集前に「何を固定し、何を変動させるか」を明示的に決める。** Day4 では白いケースは固定を維持する（BTOはこれまで固定できていた）。変動させる物体を増やすときは、組み合わせ空間が積で増えることを前提にエピソード数を見積もる
- **仮説B（チャンク継ぎ目）の検証は保留のまま。** 密度が原因なら、密度を上げたDay4でカクつきも軽減するはず。**もしDay4で掴めるようになってもカクつきが残るなら、そのとき初めて `temporal_ensemble_coeff` を試す**（原因が2つある証拠になる）

---

## メモ（動画ネタ・気づき）

- **「M1Macのせいだと思っていた失敗の原因は、ハードでも学習設定でもなく、最初にレゴを20cm四方にばらまいたことだった」** — 犯人を4回間違えた話（推論速度 → データの滑らかさ → 学習の更新回数 → 実は配置範囲）。1本の動画として構成が完成している。#008 の「速いGPUでも直らなかった」から続く、思い込みが順に剥がれていくシリーズになる
- **「同じ150エピソードでも、2cm四方なら足りて20cm四方なら足りない」** — 密度 0.1009 vs 0.0273 ep/unit²、必要エピソード数の試算550。模倣学習を始める人が最初に踏む地雷そのもので、実測値付きで語れるのは強い。Qiita記事の単独テーマになりうる
- **「掴めない」と「カクつく」を別問題として2ヶ月追いかけていたが、同じ原因だったかもしれない** — 症状ベースで切り分けようとすると、原因が1つである可能性を見落とす。デバッグの方法論の話として汎用性がある
- **「統計を3時間とっても分からなかったことが、動画を1枚並べたら一目で分かった」** — M1Macデータとの比較画像（ケースが動いている／固定されている）はそのまま画で見せられる。**動画向きの素材としては今日で一番強い**。「データセットは、統計を取る前にまず目で見ろ」という教訓に着地する
- **「ソフトを3階層掘った日に、原因は緩んだジャンパー1個だった」** — 推論速度→データの質→学習の更新回数と掘り進めた同じ日に、基板のジャンパー脱落でシステムが落ちた。Python の深いスタックトレースと、手のひらの上の2ピンの対比。Failure Log の題材として完成度が高い
- **「ジャンパー1個の意味を、回路図まで降りて確定させた」** — 型番不明 → 公式Wiki → 回路図PDF → `J4` は USB側LDOの3.3Vを CH343P と駆動ロジックに繋ぐ必須結線、と特定した過程。「分からないものを推測で済ませない」実例として使える
- **「遠くに置いたつもりが、半分は届く範囲だった」** — 体感と実測のズレ。Failure Log の題材として素直に強い。「失敗を分析したら、失敗の実行自体が半分しかできていなかった」という二重構造がある
- **「loss は綺麗に下がったのに、実機では掴めない」** — 機械学習の入口でよく誤解されるポイントを、自分の実測（loss 0.105、Day1と同水準）で語れる
- **「timestampは実時刻じゃない」** — LeRobot を使う人向けの実用的な技術ネタ。Qiita記事の単独テーマになりうる
- **「ロボットに触らずに仮説を3つ潰した日」** — 実機を持たない人にも刺さる切り口。オフライン解析の費用対効果という話にできる
- Day3 は結果だけ見れば失敗だが、原因が数字で出ているので `Road to Folding a T-shirt` の進捗回としても成立しそう。`Failure Log` を使うかどうかは、この後のDay4の結果を見てから判断する（CONVENTIONS の「常用しない」に従う）

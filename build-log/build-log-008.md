# Build Log #008 — 2026-08-05〜08-06

## 今日やったこと

AWS試験勉強で少し間が空いたのち再開。前半はM1Mac時代の失敗記録を参照した対照実験、後半はDay2（配置バリエーションを加えたデータ追加収集・再学習）を行った。

### 1. M1Mac失敗記録の確認

過去に個人ブログに記録した記事を参照：https://smartphone-zine.com/so-arm101-m1-mac-lerobot-install/

記事の要点：
- 単一カメラ構成では250エピソード学習しても成功率が頭打ち（奥行き・接触の瞬間が見えない）。最終的に2カメラ構成（InnoMaker 1080P＝wrist、Logitech C920n＝front）に変更
- 2カメラ構成での自律動作テスト時、`Record loop is running slower (8.1 Hz) than the target FPS (30.0 Hz)`という警告が発生。ACTは`n_action_steps=100`のチャンク予測を行うため、推論が30Hzに追いつかないとチャンク途中でバッファが切れ、動作の連続性が失われるという問題があった
- 記事はここから「M1 MacのMPSでのACT推論は実時間性が困難」と結論し、学習・推論をAWS EC2スポットインスタンスに移行する方針に転換していた

### 2. 対照実験の設計：M1Mac学習済みポリシーをRTX 5060 Tiで実行する

Build Log #006では「BTOで収集・BTOで学習」という別実験だったため、ポリシーとハードウェアの両方が変数になっており、動きが滑らかになった原因（GPU速度かACTアーキテクチャか）が未確定のままだった。

今回は**M1Macで収集・学習済みのポリシー（重みは固定）を、実行環境だけRTX 5060 Tiに差し替える**ことで、推論ハードウェアという変数だけを動かす対照実験とした。これにより「M1Macでの失敗が推論速度不足だったのか、それとも単一カメラ構成などポリシー・データ自体の限界だったのか」を切り分けられる、という仮説。

### 3. 対象ポリシーの選定

Hugging Face Hub上のM1Mac学習済みポリシー候補を`config.json`で確認：

- `emboss369/act_policy_20260606`：単一カメラ、初期版
- `emboss369/act_so101_lego_2cam_v1_100`：2カメラ、100エピソード
- `emboss369/so101_lego_2cam_narrow_v1_49`：2カメラ、可動範囲を絞ったnarrow variant、49エピソード
- `emboss369/act_so101_lego_2cam_v1_150`：2カメラ、150エピソード（ユーザー指定、今回の本命）

いずれも`observation.images.wrist` / `observation.images.front`のキー名、`chunk_size=100`で共通しており、BTOの既存カメラ配線（build-log-006と同じ）とそのまま互換であることを確認した。

### 4. カメラ配線の確認

```bash
v4l2-ctl --list-devices
```
```
Innomaker-U20CAM-1080p-S1: Inno (usb-0000:0e:00.3-2):
	/dev/video0
	/dev/video1
	/dev/media0

HD Pro Webcam C920 (usb-0000:0e:00.4-1):
	/dev/video2
	/dev/video3
	/dev/media1
```

`/dev/video0`＝Innomaker（wrist）、`/dev/video2`＝C920（front）で、build-log-006時点の配線・indexと一致。さらに、この2台はM1Mac記事の機材（InnoMaker 1080P・Logitech C920n）と**同一機種**であり、カメラ機材まで揃った厳密な対照実験になった。

### 5. RTX 5060 Tiでの推論実行

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

（`so101_lego_2cam_narrow_v1_49`も同様のコマンドで用意）

**結果**：動きはM1Mac時とほぼ同じカクつき（カクカク感）だった。RTX 5060 Tiは推論速度に余裕があるはずのハードウェアであるため、この結果は「M1Macでの失敗＝推論速度不足」という仮説にとって否定的な材料になった。むしろ、**M1Mac収集時点のデータ自体（収集時の動作が既に低速・不連続だった可能性）がポリシーの挙動に反映されている**、という仮説の方が有力になった。この点は結論を出し切れておらず、今後の検証課題として残る。

### 6. Day2データ収集：置き場所バリエーションの追加

Build Log #006の「次やること」（配置位置に意図的なバリエーションを持たせて位置汎化を検証する）を実施。対象は`emboss369/so101-yellow-lego-to-white-case_20260727_220921`（Day1、50エピソード）の続き。

### 7. `--dataset.root`必須エラーの発生と原因調査

初回実行時、以下のエラーで停止：

```
Traceback (most recent call last):
  File "/home/hiro/development/lerobot-workspace/.venv/bin/lerobot-record", line 10, in <module>
    sys.exit(main())
  File "/home/hiro/development/lerobot-workspace/lerobot/src/lerobot/scripts/lerobot_record.py", line 546, in main
    record()
  File "/home/hiro/development/lerobot-workspace/lerobot/src/lerobot/configs/parser.py", line 320, in wrapper_inner
    response = fn(cfg, *args, **kwargs)
  File "/home/hiro/development/lerobot-workspace/lerobot/src/lerobot/scripts/lerobot_record.py", line 415, in record
    dataset = LeRobotDataset.resume(
  File "/home/hiro/development/lerobot-workspace/lerobot/src/lerobot/datasets/lerobot_dataset.py", line 855, in resume
    raise ValueError(
ValueError: resume() requires an explicit 'root' directory because it creates a DatasetWriter. Writing into the revision-safe Hub snapshot cache (used when root=None) would corrupt the shared cache. Please provide a local directory path.
```

`lerobot_dataset.py`のソースを確認し、原因を特定：
- 新規記録（`create()`）はroot省略時、`$HF_LEROBOT_HOME/{repo_id}`（＝`$HF_HOME/lerobot/{repo_id}`）に自動解決される
- しかし`resume()`はroot省略を明示的に禁止しており（Hubのスナップショットキャッシュを汚染しないための安全装置）、必ず`--dataset.root`を渡す必要がある

Day1のローカルデータが実際に残っていることを確認：

```bash
ls -la /mnt/data/huggingface/lerobot/emboss369/
```
```
so101-yellow-lego-to-white-case_20260727_220921
```

このパスを`--dataset.root`に明示指定して再実行。

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

### 8. Day2記録結果

50エピソード追加記録に成功、Hugging Face Hubへのアップロードも完了。

```
INFO 2026-08-05 22:21:18 ls/utils.py:143 Stop recording
INFO 2026-08-05 22:21:19 a_opencv.py:601 OpenCVCamera(0) disconnected.
INFO 2026-08-05 22:21:21 a_opencv.py:601 OpenCVCamera(2) disconnected.
INFO 2026-08-05 22:21:21 follower.py:238 right_follower_arm SOFollower disconnected.
INFO 2026-08-05 22:21:21 o_leader.py:163 right_leader_arm SOLeader disconnected.
Found 11 files to upload
  Preparing   ████████████████████  11 / 11 ✓
  Uploading   ████████████████████  9 / 9 files  216MB · 1.63MB/s ✓
  Committing  ████████████████████  11 / 11 ✓
INFO 2026-08-05 22:21:40 ls/utils.py:143 Exiting
```

`meta/info.json`で確認：

```bash
cat /mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220921/meta/info.json | python3 -m json.tool | grep -E "total_episodes|total_frames|fps"
```
```
"fps": 30,
"total_episodes": 100,
"total_frames": 38384,
```

Day1（50エピソード／21,103フレーム）と合わせて**合計100エピソード／38,384フレーム**。

### 9. batch_size・stepsの最適化：実測によるスループット検証

再学習の前に、RTX 5060 Tiに最適なbatch_sizeを検討するため、実際に短時間の学習を回してVRAM・スループットを実測した。

GPUアイドル状態を確認：

```bash
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```
```
memory.used [MiB], memory.total [MiB], utilization.gpu [%]
15 MiB, 16311 MiB, 0 %
```

`--steps=30`のショートラン（`--policy.push_to_hub=false`、`--wandb.enable=false`）をbatch_size 8/16/32/64で実行し、`nvidia-smi`のVRAMポーリングと`lerobot-train`のログ出力（`smp/s`＝実効スループット）を突き合わせた。

batch_size=8の結果：
```
Training: 100%|██████████| 30/30 [00:10<00:00,  5.45step/s]INFO 2026-08-05 22:23:45 ot_train.py:609 step:30 smpl:240 ep:1 epch:0.01 loss:7.434 grdn:179.331 lr:1.0e-05 updt_s:0.182 data_s:0.001 smp/s:44 mem_gb:3.73 l1_loss:0.773 kld_loss:0.666
peak_mem_MiB: 4717
```

batch_size=16／32の結果：
```
=== batch_size=16 ===
step:30 smpl:480 ep:1 epch:0.01 loss:6.708 ... smp/s:45 mem_gb:6.85
peak_mem_MiB: 8199

=== batch_size=32 ===
step:30 smpl:960 ep:3 epch:0.03 loss:6.216 ... smp/s:46 mem_gb:13.10
peak_mem_MiB: 14855
```

batch_size=64はOOM：
```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 708.00 MiB. GPU 0 has a total capacity of 15.48 GiB of which 261.25 MiB is free. Including non-PyTorch memory, this process has 15.20 GiB memory in use.
peak_mem_MiB: 15589
```

| batch_size | step/s | samples/s | VRAM(peak) |
|---|---|---|---|
| 8 | 5.45 | 44 | 4.7GB / 16.3GB |
| 16 | 2.78 | 45 | 8.2GB / 16.3GB |
| 32 | 1.42 | 46 | 14.9GB / 16.3GB |
| 64 | — | — | OOM |

**結論**：samples/s（実効スループット）はbatch_size 8〜32でほぼ一定（44〜46）。このGPU・このモデル規模では計算がボトルネックで、バッチサイズを上げても学習は速くならず、VRAM消費が増えるだけだった。「大きいバッチ＝速い」という前提は今回は成立しなかった。

学習率（1e-5固定）を調整していないこと、Day1（batch_size=8）との比較可能性を保ちたいことから、**batch_size=8を維持**する判断とした。steps数はデータ量の増加比に合わせて算出：Day1は20,000ステップ（160,000サンプル／21,103フレーム≒7.58エポック）で収束していたため、同じエポック数を目安に

```
steps ≈ 36,000（36,000×8=288,000サンプル ÷ 38,384フレーム ≒ 7.5エポック）
```

とした。

### 10. Day2学習の実行

```bash
lerobot-train \
  --dataset.repo_id=emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
  --policy.type=act \
  --policy.device=cuda \
  --output_dir=/mnt/data/lerobot-outputs/train/act_yellow_lego_day2 \
  --job_name=act_yellow_lego_day2 \
  --policy.repo_id=emboss369/act-yellow-lego-to-white-case-day2 \
  --batch_size=8 \
  --steps=36000 \
  --save_freq=5000 \
  --wandb.enable=false \
  2>&1 | tee /mnt/data/lerobot-outputs/logs/act_yellow_lego_day2.log
```

**結果**：総ステップ数36,000、所要時間**1時間50分25秒**（約5.45 step/s、見積もり通り）。

```
INFO 2026-08-06 00:17:50 ot_train.py:655 Checkpoint policy after step 35000
step:35K smpl:282K ep:734 epch:7.34 loss:0.108 grdn:9.572 lr:1.0e-05 ... l1_loss:0.103 kld_loss:0.001
step:36K smpl:288K ep:750 epch:7.50 loss:0.106 grdn:9.546 lr:1.0e-05 updt_s:0.182 data_s:0.001 smp/s:44 mem_gb:3.73 l1_loss:0.101 kld_loss:0.000
INFO 2026-08-06 00:20:55 ot_train.py:655 Checkpoint policy after step 36000
INFO 2026-08-06 00:20:56 ot_train.py:741 End of training
INFO 2026-08-06 00:21:22 etrained.py:326 Model pushed to https://huggingface.co/emboss369/act-yellow-lego-to-white-case-day2
```

Day1（loss 0.119／l1 0.104／kld 0.002）とDay2（loss 0.106／l1 0.101／kld ≈0.000）で近い水準まで収束しており、置き場所バリエーションを増やしたことによる収束の悪化は見られなかった。

### 11. Day2ポリシーの実機評価

```bash
lerobot-rollout \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --robot.cameras='{
        wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30},
        front: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}
    }' \
    --policy.path=emboss369/act-yellow-lego-to-white-case-day2 \
    --fps=30 \
    --task="Put the yellow lego block into the white case" \
    --display_data=true \
    --duration=0
```

**結果**：Day1は記録時と同じ位置に置かないと掴めなかったが、Day2ではブロックをアームの右や左に置いても掴めるようになった。一方、アームを目一杯伸ばさないと届かないような遠い位置は、学習データに含めていなかったためか掴むことができなかった。**位置汎化は「置いた範囲内」でのみ成立し、学習データの外（可動域の限界付近）へは汎化しなかった**。

## 結果（成功／失敗／保留）

- 保留：「M1Macの失敗＝推論速度不足」仮説は、同一ポリシー・同一カメラをRTX 5060 Tiで動かしても同様のカクつきが出たことで否定的な材料が出た。原因はデータ収集時の質（M1Mac収集時点で既に低速だった可能性）の方が有力だが、未確定
- 成功（条件付き）：Day2（配置バリエーション追加・batch_size=8/steps=36,000で再学習）により、左右の位置汎化を獲得。ただし可動域の限界（アームを伸ばしきる遠い位置）へは汎化しなかった
- 成功：`--dataset.root`必須というresume()特有の制約を特定し、Day2データ収集を完了
- 成功：batch_sizeとVRAM・スループットの関係を実測し、「大きいバッチ＝速い」が今回のGPU・モデル規模では成立しないことを確認

## 失敗の原因・学んだこと

- `LeRobotDataset.resume()`はroot省略を許さない仕様（新規作成の`create()`とは非対称）。Hubのスナップショットキャッシュを汚染しないための安全装置だが、エラーメッセージを読むまで気づきにくかった
- batch_sizeを上げてもこのGPU・このワークロードではスループット（samples/s）はほぼ変わらない。計算がボトルネックであり、VRAMに余裕があるからといって大きいバッチにする理由にはならない
- 学習率を固定したままbatch_sizeだけ変えると、同じステップ数でも「見たサンプル数」が変わってしまい、収束速度の単純比較はできない。比較実験ではbatch_sizeも学習率も揃えるか、意図的に変えるなら理由を明確にする必要がある
- ポリシーの位置汎化は「学習データに含めた範囲」でしか成立しない。今回は左右方向は汎化したが、可動域の限界（遠い位置）は未学習のため汎化しなかった。汎化させたい範囲は明示的にデータ収集でカバーする必要がある、という当たり前だが重要な教訓
- M1Mac時代の「推論速度不足」という自分の仮説を、同一ポリシー・同一カメラでの対照実験によって再検証できた。当初の思い込みを鵜呑みにせず、変数を1つに絞った実験で確かめる価値を再確認した

## 次やること（一歩だけ）

- Day3：可動域の限界（アームを伸ばしきる遠い位置）にもブロックを置いたデータを追加収集し、汎化範囲がさらに広がるか検証する
- 保留中の「M1Macデータの質」仮説（収集時点で低速だったのではないか）を検証する方法を検討する

## メモ（動画ネタ・気づき）

- 「同じポリシーを速いGPUで動かしても、カクつきは直らなかった」というM1Mac対照実験の結果は、直感に反する良いネタになりそう。「推論速度が悪いんだろう」という思い込みが外れた回として、研究ノート向きかもしれない
- 「大きいバッチ＝速い」という直感が、実測では成立しなかった（samples/sが一定）というのも技術ネタとして使えそう
- Day2の「左右は掴めるようになったが、目一杯伸ばす位置はまだ掴めない」は、Road to Folding a T-shirtの正統な進捗回として使える。「一歩進んだ」を体現している

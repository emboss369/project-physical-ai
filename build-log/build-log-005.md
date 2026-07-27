# Build Log #005 — 2026-07-27

## 今日やったこと

### 1. テレオペレーション（カメラなし）の動作確認

前回（Build Log #004）の「次やること」だった、リーダーアームの動きにフォロワーアームが追従するかの確認。

```bash
cd ~/development/lerobot-workspace/lerobot
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_ARM \
    --robot.id=right_follower_arm \
    --teleop.type=so101_leader \
    --teleop.port=$LEADER_ARM \
    --teleop.id=right_leader_arm
```

結果：エラーなく接続完了、`Teleop loop time: 16.72ms (60 Hz)`を維持したまま安定動作。激しく操作しても追従が途切れず、Ctrl+Cで正常終了。

### 2. カメラの認識・識別

データ収集に向けて、机に接続済みの2台のUSBカメラを認識・区別した。

```bash
lsusb | grep -i -E "camera|video|webcam"
ls /dev/video*
```

結果：
```
Bus 003 Device 002: ID 0c45:6366 Microdia Webcam Vitade AF
Bus 005 Device 002: ID 046d:08e5 Logitech, Inc. C920 PRO HD Webcam
/dev/video0 /dev/video1 /dev/video2 /dev/video3
```

`lerobot-find-cameras`で実際に使えるストリームのindexを特定：

```bash
lerobot-find-cameras opencv
```

`/dev/video0`と`/dev/video2`が有効なストリーム（`/dev/video1`・`3`は同一カメラのメタデータノードと推測）。それぞれのキャプチャ画像（`outputs/captured_images/`に保存）を確認したところ、`video0`は完全な黒画像（レンズキャップが付いたままのwristカメラ）、`video2`は机を俯瞰するLogitech C920（frontカメラ）と判明。

### 3. カメラ付きテレオペレーション

```bash
lerobot-teleoperate \
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
    --display_data=true
```

1回目実行時、2台のカメラ接続・テレオペ自体は60Hzを維持したまま正常動作。ただし終了時に以下のエラーが出た：

```
ERROR re_grpc_client::write: Write messages call failed: transport error
ERROR re_grpc_client::write: gRPC connection severed: Failed to send messages: Unknown error
```

途中経過にも`Exceeded gRPC proxy server memory limit (1.0 GiB)`という警告が出ていた。

**原因の切り分け**：640×480の映像を2台×30fpsで送り続けると、rerun（可視化ツール）が保持する再生用の履歴データが約20秒で1GiBに達し、rerunが古い履歴を自動的に間引く仕様だった。これはライブ映像（今画面に映っている最新フレーム）やロボット制御ループ、記録データ（`lerobot-record`はディスクに直接保存するため無関係）には影響しない、rerun内部の表示バッファ管理の話。実際、映像の遅延は体感できなかったとのこと。

2回目実行時は「ターミナルをCtrl+Cで先に終了 → その後rerunビューアウィンドウを閉じる」の順にしたところ、シャットダウン時のエラー（`transport error`・`gRPC connection severed`）が出なくなった。シャットダウンの順序が影響することを確認。

### 4. 音声通知（TTS）の言語・エンジン修正

`lerobot-record`実行中の音声案内（"Recording episode one"等）が「R・E・C・O・R・D・I・N・G」とアルファベットを1文字ずつ読み上げてしまう不具合に気づいた。

**原因調査**：

```bash
which espeak espeak-ng festival spd-say
dpkg -l | grep -i -E "speech-dispatcher|espeak|festival"
spd-say -O                    # → espeak-ng, openjtalk
echo $LANG                    # → ja_JP.UTF-8
```

LeRobot側（`src/lerobot/utils/utils.py`の`say()`関数）はLinuxで単に`spd-say text`を呼ぶだけで言語指定をしていない。システムロケールが`ja_JP.UTF-8`のため、speech-dispatcherのデフォルト言語が日本語になり、espeak-ngが英単語を認識できず、Latin文字を1文字ずつ読み上げる挙動になっていたと判明。

**対処1（言語をユーザー単位で上書き）**：

```bash
mkdir -p ~/.config/speech-dispatcher
printf 'DefaultLanguage "en-US"\n' >> ~/.config/speech-dispatcher/speechd.conf
systemctl --user restart speech-dispatcher.service
spd-say --wait "Recording episode one"   # 確認OK
```

システム全体（`/etc`側）ではなくユーザー単位（`~/.config`側）の上書きに留めた。

**TTSエンジンの比較検討**：現状のespeak-ng（軽量・機械的）、flite（CMU製、apt一発で導入可、聞き取りやすい）、Piper（ニューラルTTS、高品質だが要モデルダウンロード・追加設定）を比較し、費用対効果でfliteを試すことにした。

**対処2（flite導入）**：

```bash
sudo apt install -y speech-dispatcher-flite   # sudo権限が必要なためユーザーのターミナルで実行
```

インストール直後は`spd-say -O`にfliteが出現せず、`pkill speech-dispatcher`だけでは反映されなかった（systemdが古い状態のままデーモンを再起動していたため）。`systemctl --user restart speech-dispatcher.service`で明示的に再起動したところ、`sd_flite`プロセスが立ち上がり認識された。

```bash
spd-say -o flite -L                              # → kal16 (en) のみ
spd-say -o flite --wait "Recording episode one"  # 確認OK
```

最終的にユーザー設定ファイルは以下の内容に：

```
# ~/.config/speech-dispatcher/speechd.conf
DefaultLanguage "en-US"
DefaultModule "flite"
```

```bash
systemctl --user restart speech-dispatcher.service
spd-say --wait "Recording episode one"   # モジュール指定なしでもfliteの声で発話することを確認
```

### 5. データ収集（`lerobot-record`）

タスクを決定：「黄色いレゴブロックを、白いケースに入れる」。LeRobotの既存データセット・学習事例は英語表記が主流のため、`--dataset.single_task`は英語 `"Put the yellow lego block into the white case"` を採用。計画は**1日50エピソード×4日間**、データが増えるにつれて精度がどう変化するかを見る。

Hugging Face Hubへのログイン（トークンは非共有情報のためユーザー自身のターミナルで実行）：

```bash
export HF_WRITE_TOKEN=<Write権限トークン>
hf auth login --token $HF_WRITE_TOKEN --add-to-git-credential
hf auth whoami   # → emboss369
```

Day1の記録コマンド：

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
    --dataset.repo_id=${HF_USER}/so101-yellow-lego-to-white-case \
    --dataset.num_episodes=50 \
    --dataset.single_task="Put the yellow lego block into the white case" \
    --dataset.streaming_encoding=false \
    --display_data=true
```

3回試行し、1・2回目は開始直後に中断（`meta/info.json`の`total_episodes: 0`のローカル空フォルダのみ残存）、3回目が完走。`lerobot-record`はrepo_idに実行時タイムスタンプを自動付与する仕様のため、実際のHub上のrepo名は`emboss369/so101-yellow-lego-to-white-case_20260727_220921`になった。

**結果**：**50エピソード、合計21,103フレーム**を記録（`meta/info.json`で確認）。録画中はエラーゼロ、映像エンコード（SVT-AV1、front/wrist各カメラ）・データセット化も全エピソードで正常完了。

Hugging Face Hubへのアップロードも`HfApi().dataset_info()`で確認：

```
data/chunk-000/file-000.parquet
meta/episodes/chunk-000/file-000.parquet
meta/info.json
meta/stats.json
meta/tasks.parquet
videos/observation.images.front/chunk-000/file-000.mp4  (165.9MB)
videos/observation.images.wrist/chunk-000/file-000.mp4  (111.2MB)
```

全ファイル揃っており、アップロード完全成功を確認。

中断した2つの空フォルダ（ローカルのみ、Hub側には存在しない）は削除：

```bash
rm -rf /mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_215238
rm -rf /mnt/data/huggingface/lerobot/emboss369/so101-yellow-lego-to-white-case_20260727_220827
```

なお、確認の過程でHugging Faceアカウントに6月収集の同系統（レゴ掴み）データセットが複数残っていることが判明した（`so101_lego_20260613`、`so101_lego_2cam_v1_20260617`、`so101_lego_2cam_narrow_v1_20260627`など）。今回のシリーズとは名前が異なるため学習時に混ざる心配はないが、存在は認識しておく。

### 6. 学習曲線の確認方法の検討

学習前に、学習曲線（loss推移）の見方を検討。選択肢は3つ：①wandb.ai（クラウド、`uv pip install wandb`＋ログインのみで開始可）②`wandb server`（ローカルDocker、完全オフラインだがDocker未導入で要事前セットアップ）③ターミナル出力のみ。今回はDocker未導入かつ導入コストを避けたく、③を選択。

`lerobot-train`のログ出力形式（`src/lerobot/utils/logging_utils.py`の`MetricsTracker.__str__`、`log_freq`デフォルト200ステップ毎に出力）を事前に確認：

```
step:200 smpl:1.6K ep:8 epch:0.08 loss:2.341 grdn:3.120 lr:1.0e-04 updt_s:0.150 data_s:0.020 smp/s:53 mem_gb:4.20
```

- `loss`：直近200ステップ分の平均。印字するたびにリセットされる（累積平均ではない）ので、前の行と比較して下がっているかで判断する
- `grdn`（gradient norm）：学習の安定性の指標
- `lr`：現在の学習率
- `--dataset.eval_split`を指定しない場合、`eval_loss`の行は出ない（今回は未指定）

### 7. 初回学習（Day1、ACTポリシー）

学習を開始したところ、依存関係エラーが発生：

```
ImportError: 'accelerate' is required but not installed. Install it with: pip install 'lerobot[training]' (or uv pip install 'lerobot[training]')
```

対処：

```bash
cd ~/development/lerobot-workspace/lerobot
uv pip install -e ".[training]"
```

`accelerate`・`wandb`含む13パッケージが追加インストールされた（`training` extraは`pyproject.toml`上で`wandb`も含む定義だが、今回は`--wandb.enable=false`で使わない）。

学習コマンド：

```bash
lerobot-train \
  --dataset.repo_id=emboss369/so101-yellow-lego-to-white-case_20260727_220921 \
  --policy.type=act \
  --policy.device=cuda \
  --output_dir=/mnt/data/lerobot-outputs/train/act_yellow_lego_day1 \
  --job_name=act_yellow_lego_day1 \
  --policy.repo_id=emboss369/act-yellow-lego-to-white-case \
  --batch_size=8 \
  --steps=20000 \
  --save_freq=5000 \
  --wandb.enable=false \
  2>&1 | tee /mnt/data/lerobot-outputs/logs/act_yellow_lego_day1.log
```

実行前にスリープ設定を確認（長時間の学習中にPCがサスペンドしないか）：

```bash
gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout   # → 0
```

AC電源接続時は自動サスペンドしない設定に既になっていたため、変更不要と判断。

**結果**：

- 総ステップ数20,000、所要時間**1時間1分28秒**（約5.44 step/s、RTX 5060 Ti使用）
- loss推移：6.506（step 200）→ **0.119**（step 20000）
- 内訳：`l1_loss` 0.616→0.104、`kld_loss` 0.589→0.002（ほぼ収束）
- `grdn`（勾配ノルム）：152.4→12〜13前後まで低下し安定、不安定な暴れなし
- チェックポイントを5000／10000／15000／20000ステップで保存（`/mnt/data/lerobot-outputs/train/act_yellow_lego_day1/checkpoints/`）
- 学習後、ポリシーをHugging Face Hubへ自動push：`https://huggingface.co/emboss369/act-yellow-lego-to-white-case`（`push_to_hub`のデフォルトが`true`のため追加操作不要だった）

ログ解析時の気づき：`tee`で保存したログファイルは、tqdmの進捗バーが改行（`\n`）ではなく復帰（`\r`）で更新されるため、`grep`や`tail`だけでは意図した行をうまく抽出できなかった（`\r`区切りの内容が全て1つの巨大な"行"として連結されてしまう）。`tr '\r' '\n'`で変換してから`grep`することで、実際のログ行（`step:`表示や`Checkpoint policy after step`など）を正しく抽出できた。

## 結果（成功／失敗／保留）

- 成功

## 失敗の原因・学んだこと

- rerunの`Exceeded gRPC proxy server memory limit (1.0 GiB)`警告は、2カメラ×30fpsの映像を送り続けると履歴バッファが約20秒で上限に達するために起きる、rerun内部の表示履歴管理の仕様。ライブ映像・ロボット制御・記録データには影響しない
- rerunのシャットダウン時エラー（`transport error`・`gRPC connection severed`）は、ターミナル（Ctrl+C）→ビューアウィンドウの順で閉じることで回避できた。逆順だと発生しやすい
- LeRobotの音声通知（`spd-say`呼び出し）は言語指定をしておらず、システムロケール（`ja_JP.UTF-8`）に引きずられてespeak-ngが英語をアルファベット読みしてしまっていた。`~/.config/speech-dispatcher/speechd.conf`に`DefaultLanguage "en-US"`を設定することでユーザー単位で解決
- speech-dispatcherの出力モジュール変更は`pkill speech-dispatcher`だけでは反映されないことがある。`systemctl --user restart speech-dispatcher.service`で明示的に再起動する必要があった
- `lerobot-record`は`--dataset.repo_id`にタイムスタンプを自動付与する。固定名で毎回同じrepoに記録したい場合は`--resume=true`が必要になる（Day2以降で使う予定）
- 記録を開始してもすぐに中断すると、ローカルに`total_episodes: 0`の空フォルダが残る。Hub側にはアップロードされないため、ローカルのみ手動で削除すれば良い
- `lerobot-train`実行には`lerobot[training]`extra（`accelerate`含む）が別途必要で、通常の`uv pip install -e .`だけでは入らない
- `tee`で保存したトレーニングログはtqdmの`\r`更新のせいで`grep`/`tail`が効きづらい。`tr '\r' '\n'`を挟むと解決する

## 次やること（一歩だけ）

- 学習済みポリシー（`emboss369/act-yellow-lego-to-white-case`）をフォロワーアームに実際に推論させ、黄色いレゴブロックを白いケースに入れられるか評価する
- Day2のデータ収集（`--resume=true`で追加50エピソード）

## メモ（動画ネタ・気づき）

- テレオペ成功→カメラ設定→TTSの謎の挙動修正→データ収集→初回学習、と1日で一気通貫に進んだ回。「Road to Folding a T-shirt」の1本にまとめるにはネタが多すぎるくらいで、TTSの原因調査だけでも独立した「研究ノート」的なミニコンテンツになりそう
- 「R・E・C・O・R・D・I・N・G」と読み上げる不具合の原因が、システムロケールの副作用だったという展開は、地味だが「なぜ？」が明確で検証型コンテンツに向いている
- 4日間のデータ蓄積で精度がどう変わるかを定点観測する企画は、Day1だけでなく通しで見せると面白い構成になりそう

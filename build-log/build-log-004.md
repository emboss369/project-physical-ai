# Build Log #004 — 2026-07-26

## 今日やったこと

### 1. Mozc（日本語入力）の初期モードをひらがなに固定

デフォルトではIBus+Mozcは「Direct（半角英数）」モードで起動する仕様（IBus 1.5.0以降の既知の仕様）。これを起動時から「ひらがな」に固定した。

```bash
vim ~/.config/mozc/ibus_config.textproto
```

ファイル内の`active_on_launch: False`を`active_on_launch: True`に書き換えて保存。

```bash
ibus write-cache
ibus restart
```

反映のため上記2コマンドを実行後、再起動して確認。

**設定ファイルの構造**：`~/.config/mozc/ibus_config.textproto`はMozc公式（google/mozc）が定義するIBus固有設定ファイル。バージョン2.26.4220以降で編集可能になった。`active_on_launch`はIBus起動時にMozcエンジン自体を有効化するかどうかのフラグで、`engines`ブロックとは独立した設定項目。

### 2. GRUBブートメニューでの矢印キー二重入力の解決

**症状**：GRUBメニュー（Ubuntu起動／メモリチェック／Windows起動の選択画面）で、上下キーを1回押すとメニューが2つ分移動する。

**切り分け手順**：
- OS内（Ubuntu起動後）のキー入力：正常（現象なし）→ キーボード本体の物理故障を除外
- USB2.0ポート／USB3.0ポート：どちらでも現象再現 → ポートの個体差を除外
- ワイヤレスキーボードではない（有線） → 無線レシーバーの混信も除外
- ASRock B650M Pro X3D WiFiのBIOSに「Legacy USB Support」の項目が存在しない → CSM無効化済み（UEFI専用構成）のため正常な状態と判断

**原因の推定**：GRUBのグラフィカル描画（gfxterm）とファームウェアのUSB HIDポーリングタイミングの競合。GRUBはOSのようなキーリピート制御・デバウンス処理を持たず、ファームウェアから受け取るキー入力を単純にポーリングするため、描画負荷でタイミングがズレると1回の押下が2回分として記録されることがある。

**対処**：

```bash
sudo nano /etc/default/grub
```

`GRUB_TERMINAL=console`を追加（グラフィカル描画からテキストコンソール描画に切り替え）。

```bash
sudo update-grub
sudo reboot
```

**結果**：解消。原因はレンダリング負荷だったと確認。

### 3. LeRobot開発環境構築（Ubuntu 24.04.4 LTS、uv使用）

以前のM1 Mac環境ではconda（miniforge3）を使用していたが、今回はuvに移行。

**uvとは**：Rust製の高速なPythonパッケージ・プロジェクト管理ツール（Astral社製）。`pip install`・`venv`・Pythonバージョン管理を単一ツールに統合しており、依存解決がRust実装により従来のpip/condaより大幅に高速。ただしcondaと異なり非Pythonのシステムライブラリ（ffmpeg等）は管理対象外で、OS側（apt）で別途用意する必要がある。

**uvのインストール**：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

**作業フォルダ準備**：

```bash
mkdir -p ~/development/lerobot-workspace
cd ~/development/lerobot-workspace
```

**Python 3.12環境の作成**：

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
python --version
```

condaの`conda create -n lerobot python=3.12`＋`conda activate lerobot`に相当。uvの仮想環境はパス（`.venv`）で管理するため、作業のたびに`cd`＋`source .venv/bin/activate`が必要。

**ffmpegの導入（システム側）**：

```bash
sudo apt update
sudo apt install -y ffmpeg
ffmpeg -version
ffmpeg -encoders | grep libsvtav1
```

condaでは`conda install ffmpeg=7.1.1 -c conda-forge`で環境内に閉じ込めていたが、uvはPythonパッケージ管理専用のためffmpegはaptで導入。LeRobotの動画コーデック（AV1）に必要な`libsvtav1`エンコーダの有無を確認。PyTorch 2.10以上であればシステムffmpegでも動作要件を満たす設計のため、この後導入するPyTorch 2.11.0であれば問題にならない。

**PyTorchのバージョン選定調査**：

RTX 5060 Tiは Blackwell世代（アーキテクチャコード：sm_120）。PyTorch 2.7.0以降の安定版でCUDA 12.8ビルド（cu128）としてネイティブサポートされる。それ以前のバージョンではsm_120向けカーネルが存在せず、`nvidia-smi`は正常でも学習実行時に`CUDA error: no kernel image is available for execution on the device`で失敗する既知の問題がある。現在の最新安定版は2.11.0（2026年3月リリース）。

**依存解決の事前確認（dry-run）**：

```bash
uv pip install --dry-run -e .
```

LeRobotの`pyproject.toml`側でtorchのバージョン制約がすでに新しく（cu128自動選択される水準に）更新されていることを確認。結果、`torch==2.11.0+cu128`が自動的に選択されることが判明したため、PyTorchを個別に前もって固定するステップは不要と判断（当初「依存解決で古いバージョンが選ばれるリスク」を懸念していたが、dry-run確認により杞憂と判明）。

**LeRobot本体のインストール**：

```bash
cd ~/development/lerobot-workspace
git clone https://github.com/huggingface/lerobot.git
cd lerobot
uv pip install -e .
uv pip install -e ".[feetech]"
```

**疎通確認**：

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

結果：
```
2.11.0+cu128 True NVIDIA GeForce RTX 5060 Ti
```

**追加extrasのインストール**：

```bash
uv pip install -e ".[viz]"       # rerun-sdk、テレオペ時のGUI可視化
uv pip install -e ".[dataset]"   # datasetsライブラリ、データセット記録・アップロード
uv pip install pynput            # キーボード操作（記録の開始/終了合図）
```

`viz`・`dataset`は問題なく完了したが、`pynput`のみビルドエラーで失敗：

```
× Failed to build `evdev==1.9.3`
fatal error: Python.h: そのようなファイルやディレクトリはありません
```

**原因**：LinuxでのPynputはキーボード監視バックエンドとして`evdev`パッケージに依存する。`evdev`はC拡張モジュールを含み、インストール時にその場でコンパイルが必要。コンパイルには`Python.h`ヘッダファイルが要るが、Ubuntuの通常の`python3`パッケージには含まれておらず、開発用ヘッダパッケージ（`python3-dev`）が別途必要だった。LeRobot固有の問題ではなく、Cコードを含むPythonパッケージをビルドする際に一般的に起きるパターン。

**対処**：

```bash
sudo apt update
sudo apt install -y python3-dev
uv pip install pynput
```

`python3-dev`インストール後、`/usr/include/python3.12/Python.h`が配置されてビルドが通り、成功。

### 4. データ保存先の設定（4TB HDD活用）

**HDDのフォーマット**：Windows側「ディスクの管理」でGPT初期化、NTFSでフォーマット（ラベル：DATA）。

**Ubuntu側の認識確認**：

```bash
lsblk
```

デフォルトではGNOMEのudisks/GVFSにより`/media/hiro/DATA`へ自動マウントされていることを確認。ただしデスクトップセッション依存の自動マウントのため、将来的なCLI/systemd経由の自動化作業を見据え、`/etc/fstab`による固定マウントに切り替えた。

```bash
sudo blkid | grep sda2
```

UUID（`C6403380403375F1`）を取得。

```bash
sudo mkdir -p /mnt/data
sudo umount /media/hiro/DATA
echo 'UUID=C6403380403375F1  /mnt/data  ntfs-3g  defaults,uid=1000,gid=1000,windows_names  0  0' | sudo tee -a /etc/fstab
sudo mount -a
df -h /mnt/data
```

初回`umount`は「対象は使用中」（Nautilus等がハンドルを掴んでいた）で失敗したため再起動で解決。fstabへの追記自体は成功しており、再起動後に`/dev/sda2` 3.7TBが`/mnt/data`へ正しくマウントされたことを確認。

**HuggingFaceキャッシュ先をHDDに変更**：

```bash
mkdir -p /mnt/data/huggingface /mnt/data/modelscope
echo 'export HF_HOME=/mnt/data/huggingface' >> ~/.bashrc
echo 'export MODELSCOPE_CACHE=/mnt/data/modelscope' >> ~/.bashrc
source ~/.bashrc
```

`HF_HOME`はLeRobotのデータセットキャッシュ・キャリブレーションファイルの保存先ベースディレクトリとして使われる（デフォルトは`~/.cache/huggingface`＝SSD側）。これを変更することで、データセット・キャリブレーションデータが自動的にHDD側に保存されるようにした。

### 5. SO-101アームのUSB接続・ポート固定

**ポートの特定**：

```bash
lerobot-find-port
```

USBケーブルの抜き差し検出方式で、フォロワーアーム／リーダーアームそれぞれのポートを特定。

```
フォロワーアーム: /dev/ttyACM1
リーダーアーム:   /dev/ttyACM0
```

Linuxの`/dev/ttyACM*`は認識順で番号が振られるため、抜き差しや再起動のたびに番号が入れ替わる可能性がある（M1 Macの`/dev/tty.usbmodemXXXXX`はシリアル番号ベースで固定だったのと対照的）。この対策として、udevルールでシリアル番号ベースの固定シンボリックリンクを作成した。

**シリアル番号の確認**：

```bash
udevadm info -a -n /dev/ttyACM1 | grep -m1 serial
udevadm info -a -n /dev/ttyACM0 | grep -m1 serial
```

結果：
```
フォロワー: 5A7A018619
リーダー:   5A4B047951
```

**udevルールファイルの作成**：

```bash
sudo nano /etc/udev/rules.d/99-so101.rules
```

内容：
```
SUBSYSTEM=="tty", ATTRS{serial}=="5A7A018619", SYMLINK+="so101_follower"
SUBSYSTEM=="tty", ATTRS{serial}=="5A4B047951", SYMLINK+="so101_leader"
```

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
ls -l /dev/so101_follower /dev/so101_leader
```

`/dev/so101_follower` → `ttyACM1`、`/dev/so101_leader` → `ttyACM0`のシンボリックリンクが生成されたことを確認。

**環境変数の設定**：

```bash
echo "export FOLLOWER_ARM='/dev/so101_follower'" >> ~/.bashrc
echo "export LEADER_ARM='/dev/so101_leader'" >> ~/.bashrc
source ~/.bashrc
```

参考にした過去記事では`READER_ARM`という変数名だったが、これは誤字（leader/readerの混同）と判断し、`LEADER_ARM`に修正した。

### 6. モーターセットアップの要否確認

`lerobot-setup-motors`はモーター本体のEEPROM（内部フラッシュメモリ）にサーボIDを書き込む処理であり、PCのOS・ディストリとは独立してハードウェア側に保持される。以前M1 Mac環境で同一の物理アームに対して実行済みのため、今回は再実行不要と判断し省略した。手順は以下の元記事を参照。

参照：https://smartphone-zine.com/so-arm101-m1-mac-lerobot-install/（「モーターのセットアップ」節）

### 7. キャリブレーション

一方、キャリブレーションデータ（各関節の可動域min/max値）はPC側のファイルシステムに保存される情報のため、M1 Mac環境で取得したデータはこのUbuntu環境には引き継がれておらず、初回実行が必要だった。

```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=$FOLLOWER_ARM --robot.id=right_follower_arm
```

初回実行時、以下のエラーで失敗：

```
ConnectionError: Failed to write 'Torque_Enable' on id_=2 with '0' after 1 tries. [TxRxResult] There is no status packet!
```

原因はUSBケーブルの挿し方が甘かったこと（電源アダプタ側の接触不良）。抜き差しで復活し、再実行で成功。

```
NAME            |    MIN |    POS |    MAX
shoulder_pan    |    819 |   2131 |   3533
shoulder_lift   |    804 |    813 |   3192
elbow_flex      |    890 |   3108 |   3122
wrist_flex      |    843 |   2856 |   3175
gripper         |   1820 |   1839 |   3308
Calibration saved to /mnt/data/huggingface/lerobot/calibration/robots/so_follower/right_follower_arm.json
```

続いてリーダーアームも実行：

```bash
lerobot-calibrate --teleop.type=so101_leader --teleop.port=$LEADER_ARM --teleop.id=right_leader_arm
```

```
NAME            |    MIN |    POS |    MAX
shoulder_pan    |    741 |   2067 |   3260
shoulder_lift   |    772 |    782 |   3181
elbow_flex      |    975 |   3176 |   3189
wrist_flex      |    790 |   2584 |   3134
gripper         |   2032 |   2046 |   3353
Calibration saved to /mnt/data/huggingface/lerobot/calibration/teleoperators/so_leader/right_leader_arm.json
```

いずれも保存先は`/mnt/data/huggingface/lerobot/calibration/`（HDD側）で、事前のHF_HOME設定通りに機能した。

## 結果（成功／失敗／保留）

- 成功

## 失敗の原因・学んだこと

- GRUBの矢印キー二重入力は、GRUBのグラフィカル描画（gfxterm）とファームウェアのUSB HIDポーリングの競合が原因。`GRUB_TERMINAL=console`でテキストモードに切り替えることで解消した。フォーラム検索でもズバリ一致する報告は見つからず、原因を自力で切り分けて解決する必要があった
- conda環境からuv環境への移行で、ffmpeg・PyTorchのバージョン管理の考え方が根本的に異なる点を再確認した。condaは非Pythonのシステムライブラリまで環境内に閉じ込められるが、uvはPythonパッケージ管理に特化しており、ffmpegのようなシステムバイナリは別途OS側で用意する必要がある
- 「依存解決で古いPyTorchが選ばれるリスク」を懸念してPyTorchを個別に先行固定しようとしたが、`--dry-run`で確認した結果、LeRobot側の依存指定がすでに新しいバージョン要求に更新されておりcu128が自動選択されることが判明。取り越し苦労だったが、思い込みで進めず実際に検証したことで無駄な作業を避けられた
- HDDの自動マウント（GNOME/udisks経由）とfstabによる固定マウントは別物。デスクトップ環境依存の自動マウントは、将来のCLI/systemd経由の自動化作業では機能しない可能性があるため、早い段階でfstab化しておく判断は正しかった
- 一度「前回設定した」と思い込んで確認を省略しかけたが、実際には未実行の手順（HDDマウント・HF_HOME・LeRobot本番インストール）が複数残っていた。「説明した」ことと「実行された」ことを混同しないよう、都度完了確認を取ることの重要性を再認識した
- Linuxの`/dev/ttyACM*`はUSBの認識順で番号が振られ、抜き差しのたびに入れ替わる可能性がある（M1 Macのシリアル番号ベースの命名とは異なる）。udevルールでシリアル番号ベースの固定シンボリックリンクを作ることで、番号の入れ替わりに影響されない運用にした
- SO-101のキャリブレーションエラー（`There is no status packet!`）は、参考記事でも報告されていた症状名と一致していたが、原因は記事のUSBハブのチップ品質問題ではなく、今回は単純なアーム電源アダプタの接触不良だった。同じエラーメッセージでも原因は複数あり得るため、都度切り分けが必要
- モーターセットアップ（EEPROM書き込み）とキャリブレーション（PC側ファイル保存）は保存先が異なるレイヤーの情報であり、前者はハードウェア引き継ぎ可能、後者はマシンごとに再実行が必要という区別を明確にした
- `pynput`のインストールで`Python.h`が見つからずビルド失敗。原因はUbuntuの標準`python3`パッケージに開発用ヘッダが含まれておらず、`python3-dev`が別途必要だったこと。C拡張を含むPythonパッケージのビルドエラーでは、まずこれを疑うとよいという一般的な教訓が得られた

## 次やること（一歩だけ）

- テレオペレーション（`lerobot-teleoperate`）でフォロワーアームがリーダーアームに追従するか確認する

## メモ（動画ネタ・気づき）

- 「conda脳をuvに矯正する」プロセスは、同じ移行を検討している人向けのコンテンツとして需要がありそう。特にffmpegの扱いの違いは見落としやすい
- GRUBの二重入力問題は、症状の再現性と切り分け手順がきれいに揃っているので「検証型」動画に向いている
- 「前回設定したと思い込んでいたが実際は未実行だった」という一幕は、AIとの共同作業における確認漏れのリアルな例として、Claude Codeとの対話パートを見せる回に使えそう

# Build Log #003 — 2026-07-25

## 今日やったこと

BTO PC（Ryzen 7 9800X3D / RTX 5060 Ti 16GB）を受け取り、Windows環境を温存しつつUbuntu 24.04 LTSとのデュアルブート環境を構築した。

### 1. Windows側の事前準備

**高速スタートアップの無効化**：

```
コントロールパネル → 電源オプション → 「電源ボタンの動作を選択する」
→ 「現在利用可能ではない設定を変更します」
→ 「高速スタートアップを有効にする」のチェックを外す
```

高速スタートアップが有効だとNTFSが休止状態のまま扱われ、この後のパーティションリサイズが失敗・破損する可能性があるため、事前に無効化した。

**BitLockerの確認**：

```powershell
manage-bde -status
```

未設定であることを確認。設定されていた場合はリサイズ前に無効化・一時停止が必要だったが、今回は不要だった。

**Windowsのブートモード確認**：

```
Win + R → msinfo32 → Enter
```

「システム情報」の「BIOSモード」が`UEFI`であることを確認（この後のUSBインストーラーのパーティション方式・ブートモードをこれに合わせる必要があるため）。

### 2. データ用4TB HDDのNTFSフォーマット（Windows側）

```
Win + X → 「ディスクの管理」
→ 未割り当てのHDDを右クリック → 「新しいシンプルボリューム」
→ GPT初期化
→ ファイルシステム：NTFS
→ クイックフォーマットにチェック
→ ボリュームラベル：DATA
```

WindowsとUbuntu両方から読み書きする用途のため、ext4ではなくNTFSを選択（ext4はWindows側で追加ドライバなしでは読めない）。Ubuntu標準のntfs-3gは十分枯れており、大きめファイルの読み書きでも速度上問題にならない。

### 3. SSD（1TB）のパーティション縮小

```
Win + X → 「ディスクの管理」→ Cドライブ右クリック → 「ボリュームの縮小」
```

縮小サイズはMB単位指定のため、500GB確保する場合：

```
500 GB × 1024 = 512000 MB
```

縮小後は「未割り当て」領域として残し、フォーマットやドライブ文字割当は行わない（Ubuntuインストーラー側でパーティションを作成するため）。

### 4. Ubuntu 24.04 LTSインストールUSBの作成（Rufus）

```
Rufus（Windows上）で8GB以上のUSBに書き込み
- パーティション方式：GPT
- ターゲットシステム：UEFI（非CSM）
```

**なぜGPT/UEFIか**：USBのパーティション方式は、USBメモリ自体の起動可能形式を指すものであり、容量とは無関係。既存WindowsがGPT/UEFIで構成されている場合、インストーラーもGPT/UEFIで起動しないと、GRUB（Ubuntu側ブートローダー）とWindowsのUEFIブートエントリが異なる仕組みで共存することになり、デュアルブートが破綻するリスクがある。GPTディスクはLegacy BIOS（CSM）から正常にブートできないため、両者を揃える必要がある。

### 5. BIOS設定変更（ASRock B650M Pro X3D WiFi）

```
- Secure Boot：無効化
- Boot Mode：UEFIであることを確認
- USB起動を優先に設定
```

Secure Boot無効化は、事前に把握していたRTX 5060 Ti固有の既知のドライバ不具合パターン（後述）への予防的対処として実施。

### 6. Ubuntu 24.04インストール本番

```
USBから起動 → Try or Install Ubuntu
→ 言語・キーボード設定
→ 「サードパーティ製ソフトウェアをインストールする」にチェック
→ インストールの種類：「それ以外」（手動パーティション設定）
```

パーティション構成：

| マウントポイント | サイズ | ファイルシステム |
|---|---|---|
| `/boot/efi` | 既存のWindows EFIパーティションを流用（新規作成しない） | - |
| `/` | 約450GB | ext4 |
| swap | 16〜32GB | swap area |

ブートローダーのインストール先も既存のEFIパーティションを指定。タイムゾーン・ユーザー設定後、インストール実行。再起動後、GRUBメニューでUbuntu/Windows両方が選択可能であることを確認。

### 7. NVIDIAドライバのインストール

事前調査で、RTX 5060 Ti（Blackwell世代）はUbuntu 24.04でドライバ560/575/580系列すべてが`nvidia-smi: No devices were found`や`Failed to allocate NvkmsKapiDevice`エラーで失敗する報告が複数（NVIDIA公式フォーラム等）確認できていたため、警戒しながら作業した。

```bash
sudo apt update && sudo apt upgrade -y
ubuntu-drivers devices
sudo apt install -y nvidia-driver-580
sudo reboot
```

疎通確認：

```bash
nvidia-smi
```

結果：

```
NVIDIA-SMI 595.84   Driver Version: 595.84   CUDA Version: 13.2
GPU: NVIDIA GeForce RTX 5060 Ti / 16311MiB
```

事前に警戒していた既知の不具合パターンには該当せず、一発で疎通した。`CUDA Version: 13.2`の表示は、ドライバが対応可能なCUDAの上限バージョンを示すものであり、CUDA Toolkit（`nvcc`）自体はまだインストールされていない点に注意（ドライバとToolkitは別パッケージ）。

### 8. CUDA Toolkitのインストール

**まず標準リポジトリ版を dry-run で検証**：

```bash
sudo apt install --dry-run nvidia-cuda-toolkit
```

結果、`nvidia-cuda-toolkit (12.0.140~12.0.1-4build4)`と、CUDA 12.0の古いバージョンであることが判明。RTX 5060 Ti（Blackwell、sm_120）はCUDA 12.8以降でないとネイティブサポートされないため、これは不適切と判断。加えて`openjdk-8-jre`や`nsight-compute`等、開発に不要なパッケージが108個中に多数含まれており、ディスクを無駄に消費する構成だった。Ubuntu標準リポジトリ（noble）は長期サポート版のパッケージであり、新しいGPU世代に追いついていないことを確認した一幕。

**NVIDIA公式リポジトリ経由でCUDA 12.8を導入**：

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get install -y cuda-toolkit-12-8

echo 'export PATH=/usr/local/cuda-12.8/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

疎通確認：

```bash
nvcc --version
```

結果：

```
Cuda compilation tools, release 12.8, V12.8.93
Build cuda_12.8.r12.8/compiler.35583870_0
```

CUDA 12.8を選んだ理由は、後続でインストールするPyTorch 2.11.0のcu128ホイールとバージョンを揃えるため（ドライバは13.2まで対応可能なため上位互換の心配はない）。

## 結果（成功／失敗／保留）

- 成功

## 失敗の原因・学んだこと

- USBインストーラーのパーティション方式（GPT/UEFI）は、既存Windowsのブート方式と揃える必要がある。ここがズレるとデュアルブート自体が破綻するリスクがあるため、事前に`msinfo32`でWindows側のBIOSモードを確認してから作業する判断は有効だった
- 高速スタートアップを無効化せずにパーティションリサイズを行うと、NTFSが休止状態のまま扱われて失敗・破損するリスクがある。作業前のひと手間が事故防止になった
- RTX 5060 Ti（Blackwell世代）はUbuntu 24.04でドライバ認識不良の既知の不具合報告が複数あり警戒していたが、今回は`nvidia-driver-580`系列で一発で疎通した。事前の懸念が杞憂に終わるケースもあると分かった一方、警戒して備えておいたこと自体は無駄ではなかった（Secure Boot無効化などの予防策を先に打てていたため）
- Ubuntu標準リポジトリの`nvidia-cuda-toolkit`はCUDA 12.0と古く、Blackwell（sm_120）に非対応。新しいGPU世代を使う場合はディストロ標準リポジトリではなくNVIDIA公式リポジトリを使うべきと確認した。`--dry-run`で中身を事前確認してから本番実行する習慣が、今回のような回り道の回避に直結した
- ドライバのインストールとCUDA Toolkitのインストールは別物であり、`nvidia-smi`が通っても`nvcc`は別途入れる必要がある、という基本の切り分けを再確認した

## 次やること（一歩だけ）

- データ用HDDのUbuntu側マウント設定、LeRobotのuv環境構築

## メモ（動画ネタ・気づき）

- 「新品Blackwell GPUはUbuntuでどこまで素直に動くか」は同じ構成で悩む人向けに需要がありそう。デュアルブート分割〜CUDA疎通までの一連の流れをRoad to Folding a T-shirtの1本として編集する価値あり
- 「apt標準リポジトリに釣られかけたが公式リポジトリに切り替えた」の一幕は、dry-runで中身を確認する習慣の効能を示す教育的なくだりとして使える

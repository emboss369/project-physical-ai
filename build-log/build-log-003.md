# Build Log #003 — 2026-07-25

## 今日やったこと
- BTO PC（Ryzen 7 9800X3D / RTX 5060 Ti 16GB）受け取り、初期セットアップ
- Windows既存環境を温存しつつUbuntu 24.04 LTSをデュアルブートで導入（SSD 1TBを500GB/500GBに分割）
- データ用4TB HDDをNTFSでフォーマットし、データセット・モデルキャッシュ置き場として追加
- NVIDIAドライバ（580系列）インストール、`nvidia-smi`で疎通確認
- CUDA Toolkit 12.8をNVIDIA公式リポジトリ経由で導入、`nvcc`で疎通確認

## 結果（成功／失敗／保留）
- 成功

## 失敗の原因・学んだこと
- RTX 5060 Ti（Blackwell世代）はUbuntu 24.04でドライバが認識しない既知の不具合報告が複数あったため警戒していたが、今回は`nvidia-driver-580`系列で一発で疎通した。事前の懸念が杞憂に終わるケースもあると分かった。
- Ubuntu標準リポジトリの`nvidia-cuda-toolkit`はCUDA 12.0と古く、Blackwell（sm_120）非対応。新しいGPU世代を使う場合はディストロ標準リポジトリではなくNVIDIA公式リポジトリを使うべきと再確認した。
- ドライバのインストールとCUDA Toolkitのインストールは別物であり、`nvidia-smi`が通っても`nvcc`は別途入れる必要がある、という基本の切り分けを再確認した。

## 次やること（一歩だけ）
- LeRobotのuv環境構築（Python 3.12、PyTorch 2.11.0 cu128）

## メモ（動画ネタ・気づき）
- 「新品Blackwell GPUはUbuntuでどこまで素直に動くか」は同じ構成で悩む人向けに需要がありそう。デュアルブート分割〜CUDA疎通までの一連の流れをRoad to Folding a T-shirtの1本として編集する価値あり。
- 「apt標準リポジトリに釣られかけたが公式リポジトリに切り替えた」の失敗一歩手前エピソードは、Claude Codeとの対話ログ（dry-run確認のくだり）ごと見せると教育的。

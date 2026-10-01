# Build Log #016 — 2026-09-22

## 今日やったこと

#015 の環境整備の続きで、**画像生成AIをローカルで動かした。** ComfyUI を入れ、OpenPose の ControlNet まで通して、実際に画像が出るところまで。

目的は **VTuber 画像の生成。** ツールとしては動作確認まででいったん区切る。

**今日の結論を一行で：ローカルの RTX 5060 Ti 16GB で SD1.5 + LoRA + ControlNet(OpenPose) の画像生成が回った。ただし ControlNet は SDXL 用ではなく SD1.5 用を入れたので、SDXL と組み合わせるならもう一段必要。**

---

### 1. なぜ ComfyUI か

候補にした理由は「VRAM 効率が良く、ノードベースで角度違いの一貫生成（IPAdapter / ControlNet）がやりやすい。16GB なら SDXL + ControlNet 程度は快適」**とのこと**。調べた範囲の評判であって、自分で他ツールと比較したわけではない。「快適」の実測もまだ（節8）。

### 2. 本体のインストール

置き場所は `~/development/ComfyUI`（このリポジトリの `~/Develop/` とは別ディレクトリ）。

```bash
cd ~/development/
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI
python3 -m venv venv
source venv/bin/activate
```

PyTorch は **CUDA 12.8 の wheel を明示指定**する。RTX 5060 Ti（Blackwell）は cu128 以降のビルドでないと動かない。

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

ComfyUI 本体の依存関係：

```bash
pip install -r requirements.txt
```

入ったもの：

| 項目 | バージョン |
|---|---|
| ComfyUI | v0.37.0（commit `b0f4b7b2`、2026-09-20） |
| Python（venv） | 3.12.3 |
| torch / torchvision / torchaudio | 2.11.0+cu128 / 0.26.0+cu128 / 2.11.0+cu128 |
| CUDA（torch 側） | 12.8 |
| NVIDIA ドライバ | 595.84 |
| GPU | RTX 5060 Ti 16GB（`torch.cuda.is_available()` → `True`） |

確認コマンド：

```bash
~/development/ComfyUI/venv/bin/python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

```text
2.11.0+cu128 12.8 True NVIDIA GeForce RTX 5060 Ti
```

### 3. 起動

```bash
cd ~/development/ComfyUI
source venv/bin/activate
python main.py
```

ブラウザで `http://127.0.0.1:8188` を開く（既定ポート）。

### 4. ControlNet（OpenPose）を入れる

ポーズや骨格を指定して生成するため。

```bash
mkdir -p ~/development/ComfyUI/models/controlnet
cd ~/development/ComfyUI/models/controlnet
wget https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_openpose.pth
```

1.4GB。ファイル名の `sd15` のとおり **SD1.5 用**。SDXL のチェックポイントとは組み合わせられない（節7）。

前処理ノード（画像から骨格を抽出する側）は `comfyui_controlnet_aux`：

```bash
cd ~/development/ComfyUI/custom_nodes/
git clone https://github.com/Fannovel16/comfyui_controlnet_aux
cd comfyui_controlnet_aux
source ../../venv/bin/activate
pip install -r requirements.txt
```

入ったのは commit `59b1fc4`（2026-08-28）。ComfyUI を再起動するとノードが増える。

### 5. モデル

チェックポイントと LoRA は https://civitai.com/models/ と Hugging Face から、動作確認のために手近なものを置いた。**入手 URL とダウンロード手順は記録していない**（どのモデルを常用するかは今後検討。決めたときに残す）。今 `models/` にあるもの：

| ファイル | サイズ | 種類 |
|---|---|---|
| `checkpoints/sd_xl_base_1.0.safetensors` | 6.5GB | SDXL |
| `checkpoints/sd_xl_refiner_1.0.safetensors` | 5.7GB | SDXL refiner |
| `checkpoints/Deliberate_v2.safetensors` | 2.0GB | SD1.5 |
| `loras/Bjd_Dolls_v1.safetensors` | 9.2MB | LoRA（SD1.5） |
| `controlnet/control_v11p_sd15_openpose.pth` | 1.4GB | ControlNet（SD1.5、節4） |

### 6. 実際に生成した

`output/` に 88枚。最初の1枚が 9/21 17:40（`ComfyUI_00001_.png`）、最後が 9/22 05:18（`doll__00087_.png`）。

最後の1枚に埋め込まれていたワークフローのパラメータ（ComfyUI は PNG の `prompt` チャンクにノード構成を保存するので、後から読める）：

```bash
cd ~/development/ComfyUI/output
python3 -c "
import json; from PIL import Image
im = Image.open('doll__00087_.png')
for v in json.loads(im.info['prompt']).values():
    print(v['class_type'], {k: x for k, x in v['inputs'].items() if not isinstance(x, list)})
"
```

| ノード | 設定 |
|---|---|
| CheckpointLoaderSimple | `Deliberate_v2.safetensors` |
| LoraLoader | `Bjd_Dolls_v1.safetensors`、strength 0.45 / 0.45 |
| ControlNetLoader | `control_v11p_sd15_openpose.pth` |
| ControlNetApplyAdvanced | strength 0.7、0.0〜1.0 |
| KSampler | steps 40、cfg 9.5、euler / normal、denoise 0.77 |
| 出力 | 768×768 |

画像とプロンプトはこのログには載せない。生成できた、という事実だけ残す。

保存したワークフロー：`~/development/ComfyUI/user/default/workflows/Workflow SD1.5.json`、`sdxl_simple_example.json`。

### 7. SD1.5 と SDXL が混ざっている

節1の「SDXL + ControlNet が快適」を見て SDXL の base / refiner を落としたが、節4で入れた ControlNet は SD1.5 用。**ControlNet はベースモデルの系統（SD1.5 / SDXL）と揃っていないと使えない。** 結果として、ControlNet を通した生成は SD1.5 の `Deliberate_v2` で回した。SDXL の方は `sdxl_simple_example.json` を動かしただけ。

SDXL で OpenPose を使うなら、SDXL 用の ControlNet（例：`thibaud/controlnet-openpose-sdxl-1.0` など）を別途入れる必要がある。今日はやっていない。

### 8. ここで区切る

ツールとしての導入はここまで。モデルは civitai で探せば足りる。「これから活躍してくれるかもしれない」が、使い道が決まるまで深追いしない。

---

## 今日の学び

- **ControlNet は「モデルの系統」に紐づく。** ファイル名の `sd15` を見落として SDXL を先に落とした。チェックポイントと ControlNet はセットで選ぶ
- **RTX 50 系は PyTorch の wheel を cu128 で指定する。** Blackwell（sm_120）は CUDA 12.8 以降でないとネイティブ対応しない（#003 節で確認済み）。#003 で CUDA Toolkit を 12.8 に揃えた判断が、今日 `--index-url .../cu128` の一行で済んだ理由
- **ComfyUI は PNG にワークフローを埋め込む。** 「あのとき何の設定で出したか」は画像ファイルから復元できる。Build Log に書き忘れても後から取り出せる
- **「快適」の根拠は自分の数字で持つ。** 節1の評判は評判のまま。1枚あたりの生成時間と VRAM 使用量を測っていない（下記）

## まだ測っていないこと

1. **生成時間と VRAM。** SD1.5 768×768 40 steps の1枚あたりの秒数、`nvidia-smi` のピーク VRAM。SDXL 1024×1024 でも同様に。「16GB で快適」を自分の数字にする
2. **SDXL 用 ControlNet。** 節7。SDXL でポーズ指定したくなったら
3. **相棒AI（#013）や llama-server（#014）との VRAM の取り合い。** どれも 16GB を前提に組んでいるので、同時には動かない。起動スクリプト側で見張る仕組み（#014 節7）を ComfyUI にも適用するかは、使い道が決まってから
4. **常用するモデルの選定と入手手順の記録。** 節5。VTuber 画像向けにどのチェックポイント・LoRA を使うか決めたら、URL と落とし方を残す

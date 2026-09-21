# Build Log #015 — 2026-09-21

## 今日やったこと

Ubuntu 24.04 の作業環境の穴を2つ埋めた。SO-101 も LLM も触っていない、純粋な環境整備の日。

1. **前半（節1〜9）：画面キャプチャ → OCR → クリップボード。** Windows の「テキスト抽出ツール」、Mac の「ライブテキスト」に相当するものを NormCap で作った。日本語だと文字間に余計なスペースが入る問題に当たり、原因を NormCap のソースまで追って、クリップボード後処理で潰した
2. **後半（節10〜16）：Magic Trackpad 2 のジェスチャー。** libinput-gestures + xdotool で、3本指・4本指スワイプとピンチを GNOME の操作に割り当てた

**今日の結論を一行で：「公式手順どおり」は自分の環境（X11 / Ubuntu 24.04 / 日本語）では3か所ずれていた。ずれの理由を1つずつ確かめてから直すと、後で壊れたときに戻れる。**

---

### 0. 前提となる環境

#003 で組んだ BTO PC（Ryzen 7 9800X3D / RTX 5060 Ti 16GB）の Ubuntu 側。判断の分かれ目になるので先に確認した。

```bash
lsb_release -d
echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE  DESKTOP=$XDG_CURRENT_DESKTOP"
python3 --version
which pip pip3 pipx
```

```text
Description:    Ubuntu 24.04.4 LTS
XDG_SESSION_TYPE=x11  DESKTOP=ubuntu:GNOME
Python 3.12.3
（pip / pip3 / pipx はいずれも未インストール）
```

**セッションは Wayland ではなく X11**（#010 の Desktop Pet Mode のときと同じ）。今日やる2つはどちらもこれに依存する。

---

## 前半：画面キャプチャ → OCR（NormCap）

### 1. 欲しいもの

Windows の「テキスト抽出ツール」や Mac の「ライブテキスト」のように、**画面の一部を囲むとテキストになってクリップボードに入る**機能。Ubuntu に標準では無い。エラーメッセージや設定画面の文言をチャットに貼りたい場面が毎日あり、手打ちで写すのをやめたかった。

候補は [NormCap](https://github.com/dynobo/normcap)（dynobo さん、GPL-3.0）。範囲選択 → OCR → クリップボード、という流れがそのまま欲しいものだった。

### 2. 最初に見た手順と、そのままでは通らない3点

README の「Python package」の手順に日本語を足した、次の案から始めた。

```bash
# ── 最初の案（このままでは通らない）──
sudo apt install build-essential tesseract-ocr tesseract-ocr-jpn libtesseract-dev libleptonica-dev wl-clipboard
pip install normcap
```

実行する前に環境と NormCap のソースを確認したところ、3点ずれていた。

| ずれ | 理由 | 直し |
|---|---|---|
| `pip install normcap` が通らない | ① `pip` 自体が未インストール ② 仮に入れても Ubuntu 24.04 の Python は PEP 668 の externally-managed 扱いで `error: externally-managed-environment` になる | `pipx` を使う |
| `wl-clipboard` が効かない | セッションが X11。NormCap 0.6.0 のクリップボード実装は `wlclipboard` / `xclip` / `xsel` / `qtclipboard` から使えるものを選ぶ作り | `xclip` を入れる |
| `build-essential` `libtesseract-dev` `libleptonica-dev` が不要 | NormCap 0.6.0 の依存は `jeepney` `pyside6-essentials` `zxing-cpp` の3つだけ。tesseract は C API ではなく `subprocess` で `tesseract` コマンドを叩いている（`normcap/detection/ocr/tesseract.py`）。README のこの記述は `tesserocr` を使っていた時代の名残 | 入れない |

PyPI のメタデータで依存を確認したコマンド：

```bash
curl -s https://pypi.org/pypi/normcap/json | python3 -c "
import json,sys
d=json.load(sys.stdin); i=d['info']
print(i['version'], i['requires_python'])
print(i['requires_dist'])
"
```

```text
0.6.0 >=3.9
['jeepney==0.9.0', 'pyside6-essentials==6.9.2', 'shiboken6==6.9.2', 'zxing-cpp==2.3.0', ...]
```

なお上流の推奨は Flatpak（`flatpak install flathub com.github.dynobo.normcap`）。ただし Flatpak 版は tessdata を sandbox 内（`~/.var/app/com.github.dynobo.normcap/config/normcap/tessdata`）に固定し、アプリ内の言語マネージャーから別途ダウンロードする方式（`normcap/gui/system_info.py` の `get_tessdata_path()`）。apt で入れた日本語データをそのまま使いたかったので、今回は pipx 版にした。

### 3. インストール

```bash
sudo apt install tesseract-ocr tesseract-ocr-jpn tesseract-ocr-jpn-vert xclip pipx
pipx install normcap
pipx ensurepath   # ~/.local/bin が PATH に無ければ追加。今回は既に入っていた
```

入ったもの：

| パッケージ | バージョン | 役割 |
|---|---|---|
| `tesseract-ocr` | 5.3.4-1build5 | OCR エンジン本体 |
| `tesseract-ocr-jpn` | 1:4.1.0-2 | 日本語（横書き）の学習データ |
| `tesseract-ocr-jpn-vert` | 1:4.1.0-2 | 日本語（縦書き） |
| `xclip` | 0.13-3 | X11 クリップボード |
| `pipx` | 1.4.3-1 | 隔離環境で Python アプリを入れる |
| `normcap`（pipx） | 0.6.0 | 本体 |

学習データは 4.1.0 で本体は 5.3.4 だが、v5 は v4 の traineddata をそのまま読める。

### 4. 起動と言語の確認

```bash
tesseract --list-langs
echo "${TESSDATA_PREFIX:-(unset)}"
normcap
```

```text
List of available languages in "/usr/share/tesseract-ocr/5/tessdata/" (4):
eng
jpn
jpn_vert
osd
(unset)
```

`TESSDATA_PREFIX` は未設定だが、pipx 版の NormCap はその場合 tessdata パスを渡さず tesseract の既定に任せるので、4言語ともメニューに出る。

初回起動で "Introduction to NormCap" が出る。「Show on startup」を外して Ok。画面がピンク枠になったら右上の歯車 → Languages で **`jpn` だけにチェック**（`eng` は外す）。

- 複数言語をチェックすると `-l jpn+eng` で走り、遅くなるうえ精度が落ちることがある。`jpn` の学習データは英数字もそこそこ拾う
- `jpn_vert` は縦書きを読むときだけ切り替える
- `osd` は文字の向き検出用で、言語として選ぶものではない

### 5. 日本語OCRで文字間にスペースが入る

GNOME の設定画面を囲んでみた結果がこれ。

```text
Compose キ ー(C) レイ アウ ト の デフ ォ ル ト )
```

正解は `Compose キー(Cレイアウトのデフォルト)`。文字がほぼ全部読めているのに、文節ごとに半角スペースが挟まる。別のキャプチャでも `"2.0 TB ボリ ュー ム " に アク セス で きま せ` と同じ症状。

### 6. 原因の切り分け（NormCap のソースを読む）

NormCap は tesseract を `-c tessedit_create_tsv=1` 付きで呼び、**TSV（word 単位の出力）**を読んでいる。それを `normcap/detection/ocr/models.py` の `add_linebreaks()` で連結する。

```python
def add_linebreaks(
    self,
    block_sep: str = os.linesep * 2,
    par_sep: str = os.linesep,
    line_sep: str = os.linesep,
    word_sep: str = " ",        # ← 言語に関係なく半角スペース固定
) -> str:
```

tesseract の日本語モデルは1行を「文節らしき塊」ごとの word box で返す。それを言語を見ずに `" "` で繋ぐので、`レイ` `アウ` `ト` `の` → `レイ アウ ト の` になる。capture mode（parse / raw）はどちらもこの連結を通るので、設定では変わらない。

もう一つ分かったこと。NormCap は `jpn` など空白で区切らない言語だけを選んだとき、**すでに自動で `-c preserve_interword_spaces=1` を付けている**（`TessArgs.is_language_without_spaces()`）。それでこの結果なので、このオプションは効いていない。

### 7. 検証：再現と、対策候補の潰し込み

同じ文言の画像を作って手元の tesseract で再現し、思いつく対策を全部試した。

```bash
# 検証用画像を作る（Noto Sans CJK JP 28px、白背景）
FONT=$(fc-match -f '%{file}' "Noto Sans CJK JP")
python3 - "$FONT" <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFont
font = ImageFont.truetype(sys.argv[1], 28)
img = Image.new("RGB", (640, 70), "white")
ImageDraw.Draw(img).text((10, 18), "Compose キー(Cレイアウトのデフォルト)", font=font, fill="black")
img.save("ja.png")
PY

# NormCap の前処理相当（2倍拡大＋80px 余白）
python3 - <<'PY'
from PIL import Image
im = Image.open("ja.png")
im2 = im.resize((im.width*2, im.height*2), Image.LANCZOS)
big = Image.new("RGB", (im2.width+160, im2.height+160), "white")
big.paste(im2, (80, 80)); big.save("ja_x2.png")
PY

# tessdata_best の jpn（14MB）を比較用に取得
mkdir -p best/tessdata
curl -sL -o best/tessdata/jpn.traineddata \
  https://github.com/tesseract-ocr/tessdata_best/raw/main/jpn.traineddata

# NormCap と同じ呼び方で TSV を作り、word を半角スペースで連結して表示
run() {
  d="$1"; img="$2"; shift 2
  tesseract "$img" out -l jpn --oem 1 --psm 6 \
    -c tessedit_create_tsv=1 -c preserve_interword_spaces=1 "$@" 2>/dev/null
  python3 -c "
import csv
rows=list(csv.reader(open('out.tsv'),delimiter='\t',quotechar=None))
h=rows.pop(0); ti=h.index('text')
print('$d'.ljust(28), '|', ' '.join(r[ti] for r in rows if len(r)>ti and r[ti].strip()))
"
}
run "apt jpn 4.1.0 / 等倍"      ja.png
run "apt jpn 4.1.0 / 2倍+余白"  ja_x2.png
run "tessdata_best / 等倍"      ja.png    --tessdata-dir best/tessdata
run "tessdata_best / 2倍+余白"  ja_x2.png --tessdata-dir best/tessdata
```

```text
正解                         | Compose キー(Cレイアウトのデフォルト)
apt jpn 4.1.0 / 等倍         | Compose キー(C と レイ アウ ト の デフ ォ ル ト )
apt jpn 4.1.0 / 2倍+余白     | Compose キー(C と レイ アウ ト の デフ ォ ル ト )
tessdata_best / 等倍         | Compose キー(C レ イア ウト の デフ ォ ル ト )
tessdata_best / 2倍+余白     | Compose キー(C レ イア ウト の デフ ォ ル ト )
```

| 試したこと | 結果 |
|---|---|
| `preserve_interword_spaces=1` の有無 | TSV の word 分割は変わらない（NormCap は既に付けている） |
| 2倍拡大＋余白 | 変わらない |
| tessdata_best の `jpn` | 誤認識（余計な `と`）は直った。**スペースは残る**。1サンプルでの結果 |
| capture mode の parse / raw | 同じ連結処理を通るので変わらない |

**結論：NormCap と tesseract の設定では消えない。クリップボードの後処理で消す。**

### 8. 対策：クリップボード後処理のラッパー

2ファイルを `~/.local/bin` に置いた。

`~/.local/bin/normcap-ja-clean.py` — 整形本体。ルールは「**日本語↔日本語、日本語↔ASCII記号の間の空白だけ削る**」。英数字との間は残す。

```python
import re, sys

CJK = r"　-〿぀-ゟ゠-ヿ㐀-䶿一-鿿＀-￯"
PUNCT = r"!-/:-@\[-`{-~"          # ASCII 記号（英数字は含めない）
J = f"[{CJK}]"
JP = f"[{CJK}{PUNCT}]"

def clean(text: str) -> str:
    # 日本語↔日本語、日本語↔ASCII記号 の間の空白のみ削る（英数字との間は残す）
    text = re.sub(rf"({J})[ \t]+(?={JP})", r"\1", text)
    text = re.sub(rf"({JP})[ \t]+(?={J})", r"\1", text)
    return text

if __name__ == "__main__":
    sys.stdout.write(clean(sys.stdin.read()))
```

`~/.local/bin/normcap-ja` — normcap を起動し、終了後にクリップボードを整形して書き戻す。

```bash
#!/usr/bin/env bash
# NormCap を起動し、終了後にクリップボード内の日本語間スペースを除去する。
# tesseract の日本語モデルは文節ごとに word box を返し、NormCap がそれを
# 半角スペースで連結するため、そのままでは「レイ アウ ト」になる。
set -euo pipefail

normcap "$@"

current=$(xclip -o -selection clipboard 2>/dev/null || true)
[ -n "$current" ] || exit 0
printf '%s' "$current" | python3 "$HOME/.local/bin/normcap-ja-clean.py" \
  | xclip -i -selection clipboard
```

```bash
chmod +x ~/.local/bin/normcap-ja
```

整形の確認：

```text
in : Compose キ ー(C) レイ アウ ト の デフ ォ ル ト )
out: Compose キー(C)レイアウトのデフォルト)

in : GitHub で Build Log #014 を 公開 する
out: GitHub で Build Log #014 を公開する      ← 英数字との間は残る
```

クリップボード経由の往復（`xclip -i` → `xclip -o` → 整形 → `xclip -i`）も通した。

### 9. 運用上の注意

- **NormCap の「Keep in system tray」は必ずオフ。** 常駐モードだと `normcap` プロセスが終わらず、ラッパーの後処理が走らない
- GNOME のショートカット登録：設定 → キーボード → キーボードショートカット → カスタムショートカット
  - 名前: `NormCap`
  - コマンド: `/home/hiro/.local/bin/normcap-ja`（**フルパス**。GNOME からの起動はログインシェルを通らないことがあり、`~/.local/bin` が PATH に無い前提で書く）
  - キー: `Ctrl+Super+S`（登録済み）
- 整形ルールの割り切り：`キー(C とレイアウト` のように **英数字と日本語の間のスペースは消せない**（`Compose キー` のような正しいスペースまで消えるため）。ここは手で直す

---

## 後半：Magic Trackpad 2 のジェスチャー（libinput-gestures）

### 10. 状況

Magic Trackpad 2 は Bluetooth で繋いだ時点でカーソル移動と2本指スクロールは動く（libinput が `Apple Inc. Magic Trackpad` として認識）。**動かないのは3本指以上のスワイプとピンチ。** X11 の GNOME はマルチタッチジェスチャーを自分では扱わないので、[libinput-gestures](https://github.com/bulletmark/libinput-gestures)（bulletmark さん）でジェスチャーを拾い、`xdotool` でキー入力に変換する。

```bash
libinput list-devices | grep -A14 "Apple Inc. Magic Trackpad" | grep -E "Device|Capabilities|Tap|Scroll"
bluetoothctl devices Connected
```

```text
Device:           Apple Inc. Magic Trackpad
Capabilities:     pointer gesture
Tap-to-click:     disabled
Tap-and-drag:     enabled
Scroll methods:   *two-finger edge
Device 18:7E:B9:68:10:83 AkiAppleTrackbad2
```

`Capabilities` に `gesture` があるので、libinput はジェスチャーイベントを出せる。

### 11. 必要パッケージ

```bash
sudo apt update
sudo apt install libinput-tools wmctrl xdotool git
```

| パッケージ | バージョン | 役割 |
|---|---|---|
| `libinput-tools` | 1.25.0-1ubuntu3.7 | `libinput debug-events` など。libinput-gestures がこれ経由でイベントを読む |
| `wmctrl` | 1.07-7ubuntu3 | ウィンドウ操作。libinput-gestures の内部でフォーカス判定に使う |
| `xdotool` | 1:3.20160805.1-5build1 | X11 にキー入力を送る。**Wayland では動かない** |

#010 のときは `xdotool` が無くて `ctypes` で `libX11` を直接叩いた。今日から入っている。

### 12. libinput-gestures の取得とインストール

Ubuntu の apt には無いので GitHub から。

```bash
cd ~
git clone https://github.com/bulletmark/libinput-gestures.git
cd libinput-gestures
sudo make install
```

入ったのは version 2.80（commit `87e81bb`、2026-08-17）。`/usr/bin/libinput-gestures` と `/usr/bin/libinput-gestures-setup` が置かれる。

### 13. `input` グループへの追加

libinput-gestures は `/dev/input/event*` を読むため、ユーザーが `input` グループに入っている必要がある。

```bash
sudo gpasswd -a $USER input
```

**この後、一度ログアウトして入り直す**（グループの変更はログインセッションに乗らない）。

```bash
id -nG
```

```text
hiro adm dialout cdrom sudo dip plugdev users lpadmin ollama input
```

### 14. 動作確認（設定前）

まずフォアグラウンドでデバッグ出力を見ながら動かし、3本指スワイプが拾えていることを確認する。

```bash
libinput-gestures -d
```

この状態でトラックパッドを3本指でスワイプすると、`swipe up 3` などのイベントが流れる。Ctrl+C で止める。

現在の状態だけ見るなら：

```bash
libinput-gestures-setup status
```

### 15. ユーザー設定ファイル

システム全体の `/etc/libinput-gestures.conf` は触らず、`~/.config/libinput-gestures.conf` を作る。こちらがあれば優先される。

```bash
mkdir -p ~/.config
nano ~/.config/libinput-gestures.conf
```

内容（そのまま貼る）：

```text
# ===== 3本指スワイプ =====
# 上下でワークスペース切替(GNOME標準のCtrl+Alt+↑/↓相当)
gesture swipe up    3    xdotool key super+Page_Up
gesture swipe down  3    xdotool key super+Page_Down

# 左右でアプリ(ウィンドウ)切替
gesture swipe left  3    xdotool key alt+Tab
gesture swipe right 3    xdotool key alt+shift+Tab

# ===== 4本指スワイプ =====
# 上でアクティビティ画面(概要表示)を開く/閉じる
gesture swipe up    4    xdotool key super
# 下でデスクトップを表示(全ウィンドウ最小化)
gesture swipe down  4    xdotool key ctrl+super+d

# 左右で仮想デスクトップ切替(3本指と役割を分けたい場合)
gesture swipe left  4    xdotool key ctrl+alt+Right
gesture swipe right 4    xdotool key ctrl+alt+Left

# ===== ピンチ =====
# ピンチイン(つまむ)でアクティビティ表示、ピンチアウト(開く)で閉じる
gesture pinch in     xdotool key super
gesture pinch out    xdotool key Escape
```

割り当ての方針：

| ジェスチャー | 動作 | 送るキー |
|---|---|---|
| 3本指 上/下 | ワークスペース切替 | `super+Page_Up` / `super+Page_Down` |
| 3本指 左/右 | ウィンドウ切替 | `alt+Tab` / `alt+shift+Tab` |
| 4本指 上 | アクティビティ画面 | `super` |
| 4本指 下 | デスクトップ表示 | `ctrl+super+d` |
| 4本指 左/右 | ワークスペース切替（横方向） | `ctrl+alt+Right` / `ctrl+alt+Left` |
| ピンチ イン/アウト | アクティビティ表示 / 閉じる | `super` / `Escape` |

### 16. 反映と自動起動

```bash
libinput-gestures-setup restart
libinput-gestures-setup autostart
```

`autostart` で `~/.config/autostart/libinput-gestures.desktop` が作られ、ログイン時に自動起動する。

最終確認：

```bash
libinput-gestures-setup status
ls ~/.config/autostart/
```

```text
libinput-gestures is installed.
libinput-gestures is set up as a desktop application.
libinput-gestures is currently running as a desktop application.
libinput-gestures is set to autostart as a desktop application.
libinput-gestures is using custom configuration file.

libinput-gestures.desktop  pcloud.desktop  remmina-applet.desktop  variety.desktop
```

`running` かつ `custom configuration file`（= `~/.config` 側を読んでいる）。3本指・4本指スワイプとピンチが設定どおり動くことを確認した。

---

## 今日の学び

- **README の手順は「その人の環境」の手順。** 今回のずれは pip（PEP 668）、クリップボード（Wayland 前提）、ビルド依存（古いバージョンの名残）の3つで、全部「自分の環境を先に見れば分かる」ものだった。実行前に `XDG_SESSION_TYPE` と `which pip` を見るだけで2つ避けられた
- **設定で消えない挙動は、ソースを読むと数分で理由が分かる。** NormCap の `word_sep=" "` は10行読めば見えた。しかも `preserve_interword_spaces=1` が「既に付いている」ことまで分かったので、無駄な試行を1つ減らせた
- **対策候補は表にして全部潰す。** 拡大・tessdata_best・オプション、どれも「効きそう」だったが、実測すると word 分割には1つも効かなかった。後処理で消すという結論は、この表があるから納得できる
- **X11 であることが今日は2回効いた。** NormCap は `xclip`、Trackpad は `xdotool`。どちらも Wayland に移ると作り直しになる。#010 のときの「X11 セッション」という記録が、今日の判断を速くした
- **精度とスペースは別問題。** tessdata_best は誤認識を1つ直したが、スペースには無関係だった。「良くなった気がする」で混ぜないこと

## まだやっていないこと

1. **tessdata_best の `jpn` を常用にするか。** 1サンプルでは誤認識が減った。`~/.local/share/tessdata/` に置いて `TESSDATA_PREFIX` で切り替えれば pipx 版から使えるが、複数サンプルで比べてから決める
2. **英数字↔日本語の間のスペース。** `キー(C とレイアウト` のような残りは整形ルールでは消せない。頻度を見て、消す側に倒すか判断する
3. **libinput-gestures の閾値調整。** `swipe_threshold` / `timeout` の既定値のまま。誤発火が気になってから触る
4. **Wayland に移ったときの手当て。** `xclip` → `wl-clipboard`、`xdotool` → `ydotool` 等への置き換えが必要になる。今は X11 のままなので保留

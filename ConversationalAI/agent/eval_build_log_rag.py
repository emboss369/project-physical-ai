"""Build Log 検索の評価（Build Log #017）

build_log_rag.py の重みや midori_agent.py のしきい値を変えたら、これを回して退行していないか見る。

    python eval_build_log_rag.py

- TUNING：#017 で重みや前処理を調整するときに見ながら直した17問（ここで良くても過学習の可能性がある）
- HELD_OUT：調整後に初めて当てた12問（こちらの成績のほうが実力に近い）
- VAGUE：Build Log の発動語は含むが、Build Log とは関係ない発話。しきい値未満であってほしい

質問はすべて人間（と Claude Code）が書いたもの。実際の音声入力の言い回しとは違う可能性がある。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_log_rag import BuildLogIndex  # noqa: E402

# midori_agent.py と同じ値（midori_agent.py は OLV 本体の相対 import を含むので直接読み込めない）
BUILD_LOG_TRIGGER = re.compile(
    r"ビルド\s*ログ|build\s*log|前に|以前|この前|前回|最近|あの時|あのとき"
    r"|だっけ|たっけ|覚えてる|何回目|どの回|[#＃]\s*\d+|\d+\s*回目",
    re.IGNORECASE,
)
BUILD_LOG_MIN_SCORE = 13.0

TUNING = [
    ("ヒューマノイドに目の前で触った日のこと覚えてる？", "001"),
    ("許可モードについて調べたのっていつだっけ", "002"),
    ("Ubuntuをインストールしたときのこと覚えてる？", "003"),
    ("キャリブレーションっていつやったっけ", "004"),
    ("カメラ付きのテレオペレーションを試したのは何回目？", "005"),
    ("掴める位置と掴めない位置を切り分けた回", "006"),
    ("qwen2.5とqwen3の速度比較ってどうだった？", "007"),
    ("M1 Macで学習したポリシーをRTX 5060 Tiで動かした話", "008"),
    ("timestampが合成値だったって話、どの回だっけ", "009"),
    ("ペットモードでクリックが透過しちゃう問題", "010"),
    ("vLLMを試したのはいつだっけ", "011"),
    ("Modelfileに no_think を焼き込んだのは", "012"),
    ("Irodori-TTSを採用したのっていつだっけ", "013"),
    ("n-cpu-moe に切り替えた理由は", "014"),
    ("トラックパッドのジェスチャーを設定したのは", "015"),
    ("ComfyUIで画像生成した回", "016"),
    # 発動語を検索語から外す処理を足すきっかけになった問題
    ("Build Log を調べて、キャリブレーションの話", "004"),
]
HELD_OUT = [
    ("Mozcの初期モードをひらがなにしたのはいつ？", "004"),
    ("NVIDIAドライバを入れたときどうだった？", "003"),
    ("speech-dispatcherの設定いじったよね", "005"),
    ("dataset.rootが必須ってエラー出たのいつだっけ", "008"),
    ("Day3のポリシーが失敗した原因は", "009"),
    ("OpenCodeを入れた回", "011"),
    ("ELECTRON_RUN_AS_NODEで画面が出なかった件", "010"),
    ("thinkingを切ろうとして失敗したのは", "013"),
    ("Magic Trackpadの設定", "015"),
    ("OpenPoseのControlNetを入れたのは", "016"),
    ("Claude Codeのコスト管理について調べたっけ", "002"),
    ("R1って何キロあったっけ", "001"),
]
VAGUE = ["今日って何曜日だっけ", "前に何の話してたっけ", "この前のこと覚えてる？", "元気だっけ"]


def evaluate(index: BuildLogIndex, name: str, cases: list[tuple[str, str]]) -> None:
    top1 = top3 = low = 0
    for question, expected in cases:
        hits = index.search(BUILD_LOG_TRIGGER.sub(" ", question), top_k=3)
        numbers = [c.number for _, c in hits]
        top1 += numbers[:1] == [expected]
        top3 += expected in numbers
        below = bool(hits) and hits[0][0] < BUILD_LOG_MIN_SCORE
        low += below
        mark = "○" if numbers[:1] == [expected] else ("△" if expected in numbers else "×")
        score = f"{hits[0][0]:5.1f}" if hits else "  0.0"
        print(f"  {mark} {score} 正解#{expected} 上位{numbers}  {question}")
    print(f"{name}: top1 {top1}/{len(cases)}  top3 {top3}/{len(cases)}  しきい値未満 {low}\n")


if __name__ == "__main__":
    index = BuildLogIndex()
    evaluate(index, "TUNING", TUNING)
    evaluate(index, "HELD_OUT", HELD_OUT)
    for question in VAGUE:
        hits = index.search(BUILD_LOG_TRIGGER.sub(" ", question), top_k=1)
        score = hits[0][0] if hits else 0.0
        flag = "OK" if score < BUILD_LOG_MIN_SCORE else "しきい値超え"
        print(f"  VAGUE {score:5.1f} {flag}  {question}")

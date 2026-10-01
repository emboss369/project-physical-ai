"""Build Log の検索（Build Log #017）

build-log/*.md を節ごとの断片に分け、文字 bigram の BM25 で検索する。
埋め込みモデルを使わないのは VRAM に空きが無いため（LLM と Irodori-TTS で約 14.8GB / 16GB）。
日本語の形態素解析器も入れずに済む。

単体で試す:
    python build_log_rag.py "Irodori-TTS を採用したのはいつ"

設置先: Open-LLM-VTuber/src/open_llm_vtuber/agent/agents/build_log_rag.py
（このリポジトリを正とし、シンボリックリンクで参照）
"""

import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# シンボリックリンク経由で読み込まれても、実体のあるリポジトリの build-log/ を指す
BUILD_LOG_DIR = Path(__file__).resolve().parents[2] / "build-log"

RAG_IGNORE_START = "<!-- rag:ignore-start -->"
RAG_IGNORE_END = "<!-- rag:ignore-end -->"

CHUNK_MAX_CHARS = 1200
BM25_K1 = 1.5
BM25_B = 0.75

_HEADING = re.compile(r"^(#{1,3}) (.+)$")
_TITLE = re.compile(r"^# Build Log #(\d+)\s*[—-]\s*(.+)$")
_ASCII_WORD = re.compile(r"[a-z0-9][a-z0-9_.\-]*")
_KATAKANA_WORD = re.compile(r"[ァ-ヺー]{3,}")
_TODO_OPEN = re.compile(r"^(\s*[-*] )\[ \] ?", re.MULTILINE)
_TODO_DONE = re.compile(r"^(\s*[-*] )\[[xX]\] ?", re.MULTILINE)
# 固有名詞らしいトークン（英数字の語・カタカナ語）は、検索語側で重みを上げる。
# bigram だけだと「キャリブレーション」が「ーシ」「ショ」等で「バージョン」と混ざり、
# 「n-cpu-moe に切り替えた理由は」では口語部分の bigram に負けた（#017 の評価）
NAME_WEIGHT = 3.0
SECTION_WEIGHT = 3
_NON_JA = re.compile(r"[^぀-ヿ㐀-鿿ー]+")


@dataclass
class Chunk:
    number: str  # "013"
    title: str  # "2026-09-05" など、# 見出しの — 以降
    section: str
    text: str

    @property
    def label(self) -> str:
        return f"Build Log #{self.number}（{self.title}）／{self.section}"


def name_tokens(text: str) -> list[str]:
    text = text.lower()
    return _ASCII_WORD.findall(text) + _KATAKANA_WORD.findall(text)


def tokenize(text: str) -> list[str]:
    """英数字の語とカタカナ語はそのまま、日本語は文字 bigram に分ける。"""
    tokens = name_tokens(text)
    for run in _NON_JA.split(text.lower()):
        tokens += [run[i : i + 2] for i in range(len(run) - 1)]
    return tokens


def split_file(path: Path) -> list[Chunk]:
    lines = path.read_text(encoding="utf-8").splitlines()
    number = re.search(r"(\d+)", path.stem).group(1)
    title = path.stem
    if lines and (m := _TITLE.match(lines[0])):
        number, title = m.group(1), m.group(2).strip()

    chunks: list[Chunk] = []
    section, body = "冒頭", []

    def flush():
        # チェックボックスを言葉にする。LLM は「- [ ] 報酬関数を紙に書いてみる」を
        # 「書いた記録がある」と読んだ（#017）
        text = "\n".join(body).strip()
        text = _TODO_OPEN.sub(r"\1（未着手）", text)
        text = _TODO_DONE.sub(r"\1（済）", text)
        # 長い節は段落の切れ目で CHUNK_MAX_CHARS 程度に分ける
        while text:
            if len(text) <= CHUNK_MAX_CHARS:
                piece, text = text, ""
            else:
                cut = text.rfind("\n\n", 0, CHUNK_MAX_CHARS)
                cut = cut if cut > CHUNK_MAX_CHARS // 3 else CHUNK_MAX_CHARS
                piece, text = text[:cut].strip(), text[cut:].strip()
            chunks.append(Chunk(number, title, section, piece))

    in_code = False
    ignoring = False
    for line in lines[1:]:
        # <!-- rag:ignore-start --> 〜 <!-- rag:ignore-end --> は索引に入れない。
        # 評価用の質問文をそのまま載せた #017 が、その質問で1位になってしまったため。
        # 目印は「コードブロックの外で、その行が目印だけ」のときに限る。文中やコード例で
        # 目印を説明しただけの行に反応して、#017 節9の後半がまるごと消えたため
        if not in_code and line.strip() == RAG_IGNORE_START:
            ignoring = True
            continue
        if not in_code and line.strip() == RAG_IGNORE_END:
            ignoring = False
            continue
        # コードブロック内の「# コメント」を見出しと取り違えない
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if ignoring:
            continue
        if not in_code and (m := _HEADING.match(line)):
            flush()
            section, body = m.group(2).strip(), []
        else:
            body.append(line)
    flush()
    return chunks


class BuildLogIndex:
    """build-log/ の BM25 索引。ファイルが増えたり更新されたりしたら作り直す。"""

    def __init__(self, directory: Path = BUILD_LOG_DIR):
        self.directory = directory
        self._signature = None
        self.chunks: list[Chunk] = []

    def _current_signature(self):
        return tuple(
            (p.name, p.stat().st_mtime_ns)
            for p in sorted(self.directory.glob("build-log-*.md"))
        )

    def _ensure_fresh(self):
        signature = self._current_signature()
        if signature == self._signature:
            return
        self.chunks = [
            c
            for p in sorted(self.directory.glob("build-log-*.md"))
            for c in split_file(p)
        ]
        self._tfs = [
            # 節タイトルは本文の SECTION_WEIGHT 回分として数える。#004「7. キャリブレーション」が、
            # 質問文の例として一度触れただけの #007 の短い断片に負けたため（#017 の評価）
            Counter(tokenize(c.section) * SECTION_WEIGHT + tokenize(c.text))
            for c in self.chunks
        ]
        self._lens = [sum(tf.values()) for tf in self._tfs]
        self._avg_len = sum(self._lens) / max(len(self._lens), 1)
        df = Counter(t for tf in self._tfs for t in tf)
        n = len(self.chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._signature = signature

    def latest(self, top_k: int = 2) -> list[Chunk]:
        """いちばん新しい回の冒頭の断片。「前回何したっけ」用。"""
        self._ensure_fresh()
        if not self.chunks:
            return []
        number = max(c.number for c in self.chunks)
        return [c for c in self.chunks if c.number == number][:top_k]

    def search(self, query: str, top_k: int = 3, number: str | None = None):
        """(score, Chunk) を上位から返す。number を渡すとその回だけに絞る。"""
        self._ensure_fresh()
        names = set(name_tokens(query))
        q = {t: (NAME_WEIGHT if t in names else 1.0) for t in tokenize(query)}
        scored = []
        for chunk, tf, length in zip(self.chunks, self._tfs, self._lens):
            if number and chunk.number != number:
                continue
            score = 0.0
            for t, weight in q.items():
                if f := tf.get(t):
                    norm = BM25_K1 * (1 - BM25_B + BM25_B * length / self._avg_len)
                    score += weight * self._idf[t] * f * (BM25_K1 + 1) / (f + norm)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]


if __name__ == "__main__":
    index = BuildLogIndex()
    for score, chunk in index.search(" ".join(sys.argv[1:]), top_k=5):
        print(f"{score:6.2f}  {chunk.label}  ({len(chunk.text)}字)")

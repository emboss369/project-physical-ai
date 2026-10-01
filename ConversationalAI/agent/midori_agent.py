"""佐倉みどり用の Agent（Build Log #017）

BasicMemoryAgent を継承し、LLM に呼ぶか任せると呼ばれないツールを、コード側で先に実行する。

- 毎ターン、今日の日付をシステムプロンプトに足す
- 発話に「Build Log」「前に」「〜だっけ」などが入っていたら、build-log/ を BM25 で検索し
  （build_log_rag.py）、関係する断片をそのターンだけシステムプロンプトに足す
- 発話に「ニュース」「検索」「調べ」などが入っていたら、LLM で検索語を作り、
  DuckDuckGo（MCP の ddg-search）で検索して、結果をそのターンだけシステムプロンプトに足す

qwen3-vl 8B に任せると「検索してみるね」と言うだけで search を呼ばない（#017 の計測で 0/6）。
継承なので MCP のツール呼び出しはそのまま使える。

設置先: Open-LLM-VTuber/src/open_llm_vtuber/agent/agents/midori_agent.py
（このリポジトリを正とし、シンボリックリンクで参照）
"""

import datetime
import re
from typing import Any, AsyncIterator, Callable, Dict, Union

from loguru import logger

from .basic_memory_agent import BasicMemoryAgent
from .build_log_rag import BuildLogIndex
from ..input_types import BatchInput
from ..output_types import SentenceOutput

SEARCH_TRIGGER = re.compile(r"ニュース|検索|調べ|最新|ググ")
SEARCH_MAX_RESULTS = 5
WEEKDAYS = "月火水木金土日"

# Build Log を引く発話。Web 検索の条件と重なったら（「Build Log を調べて」）こちらを優先する
BUILD_LOG_TRIGGER = re.compile(
    r"ビルド\s*ログ|build\s*log|前に|以前|この前|前回|最近|あの時|あのとき"
    r"|だっけ|たっけ|覚えてる|何回目|どの回|[#＃]\s*\d+|\d+\s*回目",
    re.IGNORECASE,
)
BUILD_LOG_RECENT = re.compile(r"前回|この前|最近")
BUILD_LOG_NUMBER = re.compile(r"[#＃]\s*(\d{1,3})|(\d{1,3})\s*回目")
# BM25 の最高点がこれ未満なら差し込まない。役目は Build Log と無関係な雑談を弾くことだけ。
# #017 の実測で、雑談（「今日って何曜日だっけ」等）は 9.1 以下、本当の質問は 17.8 以上。
# 「記録に無い質問」は見分けられない（「Tシャツを畳めたのはいつ」が 40 点）。そちらの守りは
# 差し込む文の「記録に書かれていないことは推測で補わない」が担う。
# 最初は 18 にしたが、Build Log が増えて索引の統計が動き、R1 の質問が 17.8 点で落ちた
BUILD_LOG_MIN_SCORE = 13.0
BUILD_LOG_TOP_K = 3
# ASR は日本語の語の間に空白を入れる（「調べ て みよ うか」）。bigram が切れるので詰める
_ASR_SPACE = re.compile(r"(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])")


class MidoriAgent(BasicMemoryAgent):
    """BasicMemoryAgent + 日付の注入 + キーワード起動の事前検索"""

    def _chat_function_factory(
        self,
    ) -> Callable[[BatchInput], AsyncIterator[Union[SentenceOutput, Dict[str, Any]]]]:
        # chat() を上書きしても効かない。BasicMemoryAgent は _set_llm() で
        # self.chat = self._chat_function_factory() とインスタンス属性に差し替えるため
        inner = super()._chat_function_factory()

        async def chat_with_context(
            input_data: BatchInput,
        ) -> AsyncIterator[Union[SentenceOutput, Dict[str, Any]]]:
            base_system = self._system
            today = datetime.date.today()
            extra = f"\n\n今日は{today:%Y年%-m月%-d日}（{WEEKDAYS[today.weekday()]}）。"

            utterance = _ASR_SPACE.sub("", self._to_text_prompt(input_data))
            if BUILD_LOG_TRIGGER.search(utterance):
                extra += self._build_log_context(utterance)
            elif SEARCH_TRIGGER.search(utterance):
                extra += await self._search_context(utterance, today)

            self._system = base_system + extra
            try:
                async for output in inner(input_data):
                    yield output
            finally:
                self._system = base_system

        return chat_with_context

    def _build_log_context(self, utterance: str) -> str:
        """Build Log から関係する断片を探して、システムプロンプトに足す文を返す。"""
        if not hasattr(self, "_build_log_index"):
            self._build_log_index = BuildLogIndex()

        number = None
        if m := BUILD_LOG_NUMBER.search(utterance):
            number = f"{int(m.group(1) or m.group(2)):03d}"

        # 発動用の言葉は検索語から外す。「Build Log を調べて、キャリブレーションの話」で
        # build / log が固有名詞扱いの重みで全回に当たり、#004 ではなく #007 が1位になった
        query = BUILD_LOG_TRIGGER.sub(" ", utterance)

        try:
            hits = self._build_log_index.search(
                query, top_k=BUILD_LOG_TOP_K, number=number
            )
            if hits and (number or hits[0][0] >= BUILD_LOG_MIN_SCORE):
                chunks = [c for _, c in hits]
            elif BUILD_LOG_RECENT.search(utterance):
                chunks = self._build_log_index.latest()
            else:
                logger.info(
                    f"MidoriAgent: Build Log に該当なし（最高点 {hits[0][0] if hits else 0:.1f}）"
                )
                # 黙って何も足さないと、8B は空白を作り話で埋める（#017：まだ無い
                # 「洗濯物を畳んだ回」を「第3回目、ハンカチを落とした」と答えた）
                return (
                    "\n\n## ドクターの開発記録（Build Log）を探した結果\n"
                    "いまの話に当てはまる記録は見つからなかった。過去の実験の話なら、"
                    "記録には無いみたいと正直に言う。回の番号や出来事を作らない。"
                )
        except Exception as e:
            logger.warning(f"MidoriAgent: Build Log の検索に失敗: {e}")
            return ""

        logger.info(
            "MidoriAgent: Build Log 参照 " + ", ".join(c.label for c in chunks)
        )
        body = "\n\n".join(f"### {c.label}\n{c.text}" for c in chunks)
        return (
            "\n\n## ドクターの開発記録（Build Log）から、いまの話に関係しそうな部分\n"
            f"{body}\n\n"
            "これはドクターと一緒にやってきた実験の記録。関係があれば、何回目の Build Log の話かを"
            "添えて、話し言葉で短く答える。回の番号は各見出しの「#」の後の数字をそのまま使い、"
            "数え直さない。記録に書かれていないことは推測で補わず、「記録には無いみたい」と言う。"
        )

    async def _search_context(self, utterance: str, today: datetime.date) -> str:
        """検索して、システムプロンプトに足す文を返す。失敗したら空文字。"""
        if not self._tool_executor:
            logger.warning("MidoriAgent: ToolExecutor が無いので検索をスキップ")
            return ""

        query = utterance
        try:
            query = await self._make_query(utterance, today)
            # タイムアウトで包まない。MCPClient は初回呼び出しで stdio 接続を開くため、
            # asyncio.wait_for でも anyio.fail_after でも、その内側の cancel scope と
            # 食い違って接続が壊れる（#017 で両方確認）。本体のツール呼び出しも無制限
            is_error, text, _, _ = await self._tool_executor.run_single_tool(
                "search",
                "midori-presearch",
                {"query": query, "max_results": SEARCH_MAX_RESULTS, "region": "jp-jp"},
            )
        except Exception as e:
            logger.warning(f"MidoriAgent: 事前検索に失敗: {e}")
            return ""

        if is_error or not text:
            logger.warning(f"MidoriAgent: 検索結果なし（query={query!r}）")
            return ""

        # URL は読み上げても意味が無く、コンテキストも食うので落とす
        results = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("URL:")
        )
        logger.info(f"MidoriAgent: 事前検索 query={query!r}（{len(results)}字）")
        return (
            f"\n\n## さっき「{query}」でWeb検索した結果\n{results}\n\n"
            "検索はもう済んでいる。「調べてみるね」とは言わず、この結果から2〜3件を選んで"
            "話し言葉で短く紹介する。結果に書かれていないことは言わない。"
        )

    async def _make_query(self, utterance: str, today: datetime.date) -> str:
        """発話から検索語を作る。音声認識の誤りもここで直させる。"""
        system = (
            f"今日は{today:%Y年%-m月%-d日}。ユーザーの発話から、Web検索に使う検索語だけを1行で出力する。"
            "音声認識の誤りは直す（例：フィジカル A → フィジカルAI）。説明や記号は付けない。年は付けない。"
        )
        query = ""
        async for event in self._llm.chat_completion(
            [{"role": "user", "content": utterance}], system
        ):
            if isinstance(event, str):
                query += event
            elif isinstance(event, dict) and event.get("type") == "text_delta":
                query += event.get("text", "")
        query = query.strip().splitlines()[0] if query.strip() else ""
        return query or utterance

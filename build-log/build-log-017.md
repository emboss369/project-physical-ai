# Build Log #017 — 2026-10-01

## 今日やったこと

相棒AI「佐倉みどり」（#013）の拡張。きっかけは「Open-LLM-VTuber に長期記憶・RAG・プラグインを足すには？」という問い。Claude（チャット）に調べてもらった結果を、手元のコードで裏取りするところから始めた。

一日の流れ：

1. Claude の調査結果を、手元の Open-LLM-VTuber（v1.2.1）のコードとログで裏取りした
2. MCP の `time` サーバーのタイムゾーンを `Asia/Shanghai` → `Asia/Tokyo` に直した
3. LLM のコンテキストを 8192 → **32768** トークンに広げた（KV キャッシュを q8_0 に）
4. 「今何時？」に**午後3時15分**と答える（実際は19時51分）→ 原因はツールを呼ばずに時刻を作っていたこと。persona に1行足して直した
5. ニュースを頼むと「検索するね」と言うだけで**検索しない** → プロンプトでは直らなかった
6. **自作 Agent（`MidoriAgent`）**を書き、検索をLLM任せにせずコード側で先に実行するようにした
7. 長期記憶は見送り、**Build Log の RAG** を設計・実装した。みどりが過去の Build Log を引いて答える

**今日の結論を一行で：8B のローカル LLM に「ツールを呼ぶかどうか」を任せると呼ばない。呼ぶべき場面はコードで判定して、結果を先に渡すほうが確実だった。**

---

## 前半：裏取りと土台の調整

### 1. Claude の調査結果を手元で裏取りする

Claude の回答の要点は「公式に長期記憶・RAG・プラグイン機構は揃っていない。拡張の入口は Agent の差し替えと MCP」。これを手元のコードで確かめた。

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
git log --oneline -3
ls src/open_llm_vtuber/agent/agents
ls src/open_llm_vtuber/mcpp
grep -n "conversation_agent_choice\|use_mcpp\|mcp_enabled_servers" conf.yaml
cat mcp_servers.json
cat src/open_llm_vtuber/agent/agent_factory.py
cat src/open_llm_vtuber/agent/agents/agent_interface.py
wc -l src/open_llm_vtuber/agent/agents/*.py
```

| Claude の回答 | 手元で確認した事実 |
|---|---|
| 長期記憶は公式に無い | 合っている。`BasicMemoryAgent` の記憶は `self._memory` というリストだけ。過去の会話は、チャット履歴（`chat_history/`）を読み直して戻している |
| Mem0 Agent はコードが参考用に残っている | **残っていない。** `agents/mem0_llm.py` は **0 バイトの空ファイル**（`wc -l` で 0 行）。`mem0_agent` を選ぶと読み込みで落ちる |
| Letta は設定だけで長期記憶を持てる | 設定欄と依存パッケージ（`letta-client`）はある。ただし Letta サーバーを別に立てる必要があり、会話に使う LLM も Letta 側の設定になる |
| MCP は `basic_memory_agent` だけが対応 | 合っている。ただし後で分かるとおり、**継承すれば自作 Agent でも使える**（節6） |

MCP がすでに動いているかは、起動ログで確かめた。

```bash
grep -n "mcp\|ToolManager" ~/.local/state/sakura-midori/vtuber.log | head
ollama show qwen3-vl-8k
```

`time` と `ddg-search` の2つの MCP サーバーに接続し、ツールを5個読み込んでいた。LLM（`qwen3-vl-8k`）も、`ollama show` の Capabilities に `tools` が出ていた。**MCP の土台は最初から動いていた。**

起動ログにはもう1つ気になる行があった。

```text
Dynamically generated MCP prompt string (length: 5573).
```

約5,600文字のツール説明が作られている。コンテキストが 8192 トークンだと、これは重い。後でコンテキストを広げる理由のひとつになった（節3）。

### 2. `time` サーバーのタイムゾーン

`mcp_servers.json` の `time` サーバーが、配布時のまま `--local-timezone=Asia/Shanghai` になっていた。

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
sed -i 's|--local-timezone=Asia/Shanghai|--local-timezone=Asia/Tokyo|' mcp_servers.json
grep -n timezone mcp_servers.json
```

```json
"time": {
  "command": "uvx",
  "args": ["mcp-server-time", "--local-timezone=Asia/Tokyo"]
}
```

MCP サーバーはバックエンドの起動時に立ち上がるので、反映にはバックエンドの再起動が必要。

### 3. コンテキストを 8192 → 32768 に広げる

最初の希望は 49152 トークンだった。まず VRAM の内訳と、KV キャッシュの実際のサイズを Ollama のログで確かめた。

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
ollama ps
ollama show qwen3-vl-8k --modelfile
journalctl -u ollama --since "2026-10-01 18:25" --until "2026-10-01 18:27" --no-pager \
  | grep -i -E "n_layer|n_head_kv|n_embd_head|KV buffer|model buffer|compute buffer"
```

| 項目 | 実測（8192 トークン時） |
|---|---|
| VRAM 合計 | 16311 MiB |
| 使用中 | 13620 MiB（Ollama 7812 MiB ＋ Irodori-TTS 5780 MiB） |
| 空き | 約 2.7 GB |
| モデルの重み | 4453 MiB |
| KV キャッシュ（fp16） | **1152 MiB**。36層 × KV ヘッド 8 × 次元 128 で、1トークンあたり 144 KiB |
| Flash Attention | すでに有効（`warmup: flash attention is enabled`） |

ここから試算した表：

| 設定 | KV キャッシュ | 8192 時からの増加 | 判断 |
|---|---|---|---|
| 49152・fp16 | 6912 MiB | +5.6 GB | ✗ 空きが足りない |
| 49152・q8_0 | 約 3.5 GB | 約 +2.3 GB | △ 残りが約 0.3 GB。計算用バッファも増えるのでほぼ溢れる |
| 49152・q4_0 | 約 1.7 GB | 約 +0.6 GB | ○ 収まる。ただし KV を 4bit にするので、長い文脈での精度に不安 |
| **32768・q8_0** | 約 2.4 GB | 約 +1.3 GB | **○ 余裕が約 1.4 GB 残る。採用** |

**溢れても Ollama はエラーにならない。** 一部の層が CPU に移り、静かに遅くなるだけ（#013・#014 と同じ構図）。そのため、余裕を残す側を選んだ。

#### 32k 版のモデルを作る

既存の `qwen3-vl-8k` の Modelfile を書き出して、`num_ctx` だけ書き換えた。

```bash
ollama show qwen3-vl-8k --modelfile \
  | sed 's/^PARAMETER num_ctx 8192$/PARAMETER num_ctx 32768/' > qwen3-vl-32k.Modelfile
grep -n "num_ctx\|^FROM\|RENDERER\|PARSER" qwen3-vl-32k.Modelfile
ollama create qwen3-vl-32k -f qwen3-vl-32k.Modelfile
ollama show qwen3-vl-32k          # Capabilities に completion / vision / tools が残っていること
cp qwen3-vl-32k.Modelfile ~/ollama-modelfiles/
```

`RENDERER qwen3-vl-instruct` と `PARSER qwen3-vl-instruct` も Modelfile ごと引き継がれ、`tools` 対応も残った。

#### 使うモデルを差し替える

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
cp conf.yaml conf.yaml.before-32k          # これまでの .before-* と同じ流儀で退避
sed -i "131s/qwen3-vl-8k/qwen3-vl-32k/" conf.yaml      # ollama_llm.model

cd ~/Develop/project-physical-ai/ConversationalAI
sed -i 's/^LLM_MODEL="qwen3-vl-8k"/LLM_MODEL="qwen3-vl-32k"/' start-midori.sh
```

#### KV キャッシュを q8_0 にする（sudo が必要なので自分のターミナルで）

KV キャッシュの型は Modelfile では指定できない。Ollama サーバーの環境変数で決まり、**Ollama の全モデルに効く。**

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_KV_CACHE_TYPE=q8_0"\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\n' \
  | sudo tee /etc/systemd/system/ollama.service.d/kv-cache.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

その後 `start-midori.sh` で起動し直して確認した。

```bash
ollama ps
journalctl -u ollama -n 300 | grep "KV buffer"
```

```text
NAME                   ID              SIZE      PROCESSOR    CONTEXT    UNTIL
qwen3-vl-32k:latest    731996c17e56    8.0 GB    100% GPU     32768      Forever

llama_kv_cache:      CUDA0 KV buffer size =  2448.00 MiB
```

**2448 MiB と出て、一瞬「q8_0 が効いていない」と思った。** 実際は効いていた。

```bash
journalctl -u ollama --since "19:48" --no-pager | grep -E "K \(|V \("
nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader
nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader
```

```text
llama_kv_cache: size = 2448.00 MiB ( 32768 cells,  36 layers,  1/1 seqs), K (q8_0): 1224.00 MiB, V (q8_0): 1224.00 MiB
```

K と V は両方とも q8_0 になっている。間違っていたのは私（と Claude Code）の目安のほう。最初に「約 1224 MiB」と伝えたのは K だけの値で、V の分を足し忘れていた。fp16 のままなら 32k で 4608 MiB になる。2448 MiB は、q8_0 の1要素あたり 1.0625 バイトで計算したときの値とぴったり合う。

| | 8192・fp16（前） | 32768・q8_0（後） |
|---|---|---|
| `ollama ps` の SIZE | 6.5 GB | 8.0 GB |
| Ollama の VRAM | 7812 MiB | 9174 MiB |
| VRAM 使用量の合計 | 13620 MiB | 14842 MiB |
| 空き | 約 2.7 GB | **約 1.4 GB** |

**ComfyUI（#016）と同時には動かせない。** VRAM は、Ollama・Irodori-TTS・バックエンドの3つでほぼ埋まっている。

### 4. 「今何時？」→「午後3時15分」（実際は19時51分）

タイムゾーンを直した直後に聞くと、午後3時15分と答えた。上海時間（18:51）とも UTC（10:51）とも合わない。**タイムゾーンの問題ではない。**

```bash
L=~/.local/state/sakura-midori/vtuber.log
sed 's/\x1b\[[0-9;]*m//g' $L | grep -a -n "19:5[0-3]" | cut -c1-260
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber/chat_history/sakura_midori_001
ls -lt | head -4
```

ログと会話履歴から分かったこと：

- ツールを使う経路には入っていた。ツール無しの経路に入るとログに残る行（`Starting simple chat completion`）が、一度も出ていない
- それでも、どの回も入力から約1秒で音声生成が始まっていて、ツール呼び出しの往復が無い
- 最初の答えが「午後3時」。その後は直前の自分の答えをなぞり、「午後3時15分」を繰り返していた

#### 切り分け：Ollama に直接聞く

OLV を通さず、OpenAI 互換 API に同じ条件で投げて、ツールを呼ぶ回数を数えた。システムプロンプトは、OLV と同じく「persona ＋ OLV が末尾に足す表情プロンプト」で組んだ。

```python
# probe：persona と表情プロンプトの組み合わせで、ツールを呼ぶ割合を数える（抜粋）
import json, urllib.request, yaml
p = yaml.safe_load(open('characters/sakura_midori.yaml'))['character_config']['persona_prompt']
md = [m for m in json.load(open('model_dict.json')) if m['name'] == 'mao_pro'][0]
exp = open('prompts/utils/live2d_expression_prompt.txt').read() \
        .replace("[<insert_emomap_keys>]", " ".join(f"[{k}]," for k in md['emotionMap']))

def ask(system, hist):
    body = {"model": "qwen3-vl-32k", "messages": [{"role": "system", "content": system}] + hist,
            "tools": tools, "stream": False}
    m = json.load(urllib.request.urlopen(urllib.request.Request(
        "http://localhost:11434/v1/chat/completions", json.dumps(body).encode(),
        {"Content-Type": "application/json"})))["choices"][0]["message"]
    return "T" if m.get("tool_calls") else "x"
```

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber && python3 probe.py
```

各8回（temperature 0.9）：

| 条件 | ツールを呼んだ回数 |
|---|---|
| persona だけ | 毎回呼んだ（別途3回中3回） |
| persona ＋ 表情プロンプト（今のまま） | **3/8** |
| persona ＋ 表情プロンプト ＋ 時刻ルール | **8/8** |
| 今のまま ＋ 誤答の残った履歴 | 0/8 |
| 時刻ルール ＋ 誤答の残った履歴 | 5/8 |

persona だけなら呼ぶのに、OLV が足す表情プロンプトと組み合わさると呼ばなくなる。誤答が履歴に残っていると、さらに強くなぞる。

#### 対策：persona に1行

`ConversationalAI/sakura_midori.yaml` の「数字をでっち上げない」の直後に足した。

```yaml
    時刻や日付を聞かれたら、必ず get_current_time ツールで確かめてから答える。記憶や推測で時刻を言わない。
```

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run python -c "import yaml; yaml.safe_load(open('characters/sakura_midori.yaml'))"   # #012 の教訓：必ずパースを通す
```

バックエンドを再起動し、**新しい会話で**聞くと、正しい時刻を答えた。ログにも `Executing tool: get_current_time` が出るようになった。

### 5. ニュース：「検索するね」と言うだけで検索しない

次に「今日のフィジカルAIのニュースを調べて」と頼んだ。みどりは「チェックするね！」「検索してみるよ」と言うだけで、ログに `search` の実行は一度も出ない。時刻と同じ型の問題に見えた。

MCP サーバーが実際に渡しているツール定義を、MCP の Python SDK で直接取り出した。

```python
# dump_tools.py：mcp_servers.json の各サーバーに繋いで list_tools する
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
cfg = json.load(open('mcp_servers.json'))['mcp_servers']

async def main():
    out = []
    for name in ["time", "ddg-search"]:
        c = cfg[name]
        async with stdio_client(StdioServerParameters(command=c["command"], args=c["args"])) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                for t in (await s.list_tools()).tools:
                    out.append({"type": "function", "function": {
                        "name": t.name, "description": t.description, "parameters": t.inputSchema}})
    json.dump(out, open('tools.json', 'w'), ensure_ascii=False, indent=1)

asyncio.run(main())
```

```bash
uv run --no-sync python dump_tools.py
```

出てきたツールは `get_current_time` / `convert_time` / `search` / `fetch_content` / `expand_link` の5つ。これを使って、時刻と同じ要領で数えた。

| 条件 | `search` を呼んだ回数 |
|---|---|
| 今のまま・「ニュース見てもらってもいい？」 | 2/6 |
| 今のまま・「今日のフィジカルAIのニュースを検索して」（直接の命令） | 4/4 |
| 今のまま・実際の会話履歴を再生して、2回目の依頼 | 0/6 |
| 強めのルールを追加・実際の会話履歴の最初の依頼まで | 2/6 |
| 強めのルールを追加・実際の会話履歴を再生して、2回目の依頼 | **0/6** |
| 強めのルール ＋ temperature 0.6 | 1/6 |

強めのルールの中身は「『調べてみるね』とだけ言って終わるのは禁止。調べると言うなら、同じ返事の中で必ずツールを呼ぶ。検索語に年を入れない」。

**プロンプトでは直らなかった。** 時刻と違って、ニュースは「雑談として返す」こともできてしまう質問。さらに、履歴に「検索してみるよ」と言って終わった返事が2回あると、それを強くなぞる。

もう1つ、呼べたときの検索語が `"最新のフィジカルAIニュース 2024"` だった。**モデルは今日の日付を知らない。** 検索できても古い記事を拾う。

この強めのルールは効果が無かったので、persona には入れていない。

---

## 後半：自作 Agent と Build Log RAG

### 6. 自作 Agent `MidoriAgent` の作り方

方針：**ツールを呼ぶかどうかの判断を LLM から取り上げる。** 発話にキーワードがあれば、コード側で先に検索し、結果をそのターンだけシステムプロンプトに足してから LLM に答えさせる。毎ターン、今日の日付も足す。

この節は、OLV に自作 Agent を足す手順としても読めるように書く。全文は末尾の付録。

#### OLV の Agent の仕組み（作る前に読んだところ）

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber/src/open_llm_vtuber
cat agent/agents/agent_interface.py
sed -n 1,112p agent/agents/basic_memory_agent.py      # __init__
sed -n 581,672p agent/agents/basic_memory_agent.py    # _chat_function_factory と chat
grep -n "^def " agent/transformers.py
grep -n "agent_engine.chat" conversations/*.py
sed -n 370,400p service_context.py                    # AgentFactory.create_agent の呼び出し
```

**1ターンの流れ：**

```
ASR の文字起こし
    ↓ conversations/single_conversation.py
BatchInput（texts / images / metadata）
    ↓ context.agent_engine.chat(batch_input)
Agent
    ↓ SentenceOutput を1文ずつ yield
TTS → Live2D の口パク・表情 → 画面
```

**Agent が満たすべきもの**（`AgentInterface`）：

| メソッド | 役割 |
|---|---|
| `chat(input_data)` | 非同期ジェネレータ。`SentenceOutput`（表示用テキスト・読み上げ用テキスト・表情）を1文ずつ返す |
| `handle_interrupt(heard_response)` | 話している途中で遮られたときに、どこまで聞こえたかを記憶に反映する |
| `set_memory_from_history(conf_uid, history_uid)` | 保存済みの会話履歴から記憶を戻す |

**`BasicMemoryAgent` の中身**：`chat` の実体は `_chat_function_factory()` が作る関数で、LLM のトークン列を4段のデコレータで加工している。

```python
@tts_filter(self._tts_preprocessor_config)      # 4. 読み上げ用に記号などを落とす
@display_processor()                            # 3. 表示用テキストを整える
@actions_extractor(self._live2d_model)          # 2. [joy] などの表情タグを抜き出す
@sentence_divider(faster_first_response=..., )  # 1. トークン列を文に区切る
async def chat_with_memory(input_data):         # 0. 記憶＋入力で LLM を呼ぶ（MCP のツールループもここ）
    ...
```

**Agent が作られるところ**：キャラクターを選んだとき、`service_context.py` が `AgentFactory.create_agent(...)` を呼ぶ。このとき、システムプロンプト（persona ＋ 表情プロンプト）、Live2D モデル、MCP の部品（`tool_manager` / `tool_executor`）がまとめて渡される。

#### 継承元と差し込み口の選び方

| 選択肢 | 判断 |
|---|---|
| `AgentInterface` を一から実装 | ✗ 記憶、割り込み、4段のデコレータ、MCP のツールループを全部書き直すことになる |
| **`BasicMemoryAgent` を継承** | **○ 足したいのは「LLM を呼ぶ前にシステムプロンプトに文を足す」だけ。残りは親のまま使える** |

差し込み口は **`_chat_function_factory` を包む**形にした。

- `chat()` の上書きは効かない（下の「つまずき1」）
- デコレータの**外側**で包むので、文の区切り、表情タグ、読み上げ用の加工は親のまま効く
- 包んだ関数の中でシステムプロンプトを差し替え、`finally` で元に戻す。検索結果は会話履歴（`self._memory`）に入らない

#### 実装の骨格

```python
class MidoriAgent(BasicMemoryAgent):

    def _chat_function_factory(self):
        inner = super()._chat_function_factory()      # 親が作った「4段デコレータ付き」の関数

        async def chat_with_context(input_data):
            base_system = self._system
            extra = f"\n\n今日は{today:%Y年%-m月%-d日}（{曜日}）。"

            utterance = _ASR_SPACE.sub("", self._to_text_prompt(input_data))   # 親のヘルパーで発話を取り出す
            if BUILD_LOG_TRIGGER.search(utterance):
                extra += self._build_log_context(utterance)          # 節9
            elif SEARCH_TRIGGER.search(utterance):
                extra += await self._search_context(utterance, today)  # MCP の search を直接呼ぶ（節7）

            self._system = base_system + extra               # このターンだけ
            try:
                async for output in inner(input_data):       # あとは親の処理そのまま
                    yield output
            finally:
                self._system = base_system                   # 割り込み・例外でも必ず戻す

        return chat_with_context
```

親から借りているもの：

| 属性・メソッド | 使い道 |
|---|---|
| `self._system` | システムプロンプト。親の LLM 呼び出しは毎回これを読む |
| `self._to_text_prompt(input_data)` | `BatchInput` から発話テキストを取り出す |
| `self._llm.chat_completion(messages, system)` | 検索語を作るための、ツール無しの単発の LLM 呼び出し |
| `self._tool_executor.run_single_tool(...)` | MCP のツールを LLM を通さずに呼ぶ |

`__init__` は書いていない。親の引数をそのまま受け取り、Build Log の索引は最初に必要になったときに作る（`hasattr` で判定）。

#### 先に小さく試す

Agent を書く前に、「LLM で検索語を作る → DuckDuckGo で検索」の流れだけを単独で動かした。

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
uv run --no-sync python proto.py
```

```text
query: フィジカルAIニュース 0.2s
search 1.5s, 1052 chars
```

ASR の誤認識「フィジカル A」は、検索語を作る段階で「フィジカルAI」に直った。検索結果には「日本フィジカルAI新聞」などが並んだ（検索結果の中身は外部の記事で、自分では検証していない）。

#### 設計

```
発話
 ├─ 「Build Log」「前に」「〜だっけ」等 → Build Log を検索（節9）
 ├─ 「ニュース」「検索」「調べ」「最新」「ググ」 → LLM で検索語 → MCP の search → 結果
 └─ どちらでもない → 何もしない
       ↓
システムプロンプト ＝ persona ＋ 表情プロンプト ＋「今日は2026年10月1日（木）。」＋ 上の結果
       ↓
BasicMemoryAgent の通常の処理（MCP のツール呼び出しもそのまま使える）
       ↓
ターンが終わったらシステムプロンプトを元に戻す（検索結果は会話履歴に残さない）
```

置き場所は `sakura_midori.yaml` と同じ流儀。**本体はこのリポジトリ**（`ConversationalAI/agent/`）に置き、OLV 側からはシンボリックリンクで参照する。

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
ln -s ~/Develop/project-physical-ai/ConversationalAI/agent/midori_agent.py \
      src/open_llm_vtuber/agent/agents/midori_agent.py
```

#### OLV 本体への登録（2箇所）

`conversation_agent_choice` は pydantic の `Literal` で検証されているので、factory だけでなく設定の型にも足す必要があった。

```bash
grep -n "conversation_agent_choice" -A6 src/open_llm_vtuber/config_manager/agent.py
grep -n "def deep_merge" src/open_llm_vtuber/service_context.py   # キャラクター YAML は conf.yaml に深いマージで重なる
```

```diff
--- a/src/open_llm_vtuber/config_manager/agent.py
+++ b/src/open_llm_vtuber/config_manager/agent.py
     conversation_agent_choice: Literal[
-        "basic_memory_agent", "mem0_agent", "hume_ai_agent", "letta_agent"
+        "basic_memory_agent", "mem0_agent", "hume_ai_agent", "letta_agent",
+        "midori_agent",
     ] = Field(..., alias="conversation_agent_choice")
```

```diff
--- a/src/open_llm_vtuber/agent/agent_factory.py
+++ b/src/open_llm_vtuber/agent/agent_factory.py
 from .agents.basic_memory_agent import BasicMemoryAgent
+from .agents.midori_agent import MidoriAgent
 ...
-        if conversation_agent_choice == "basic_memory_agent":
+        # midori_agent: BasicMemoryAgent の派生。設定は basic_memory_agent のものを共用する
+        if conversation_agent_choice in ("basic_memory_agent", "midori_agent"):
 ...
+            agent_class = (
+                MidoriAgent
+                if conversation_agent_choice == "midori_agent"
+                else BasicMemoryAgent
+            )
+
             # Create the agent with the LLM and live2d_model
-            return BasicMemoryAgent(
+            return agent_class(
```

`midori_agent` を `basic_memory_agent` と同じ分岐で作るのが要点。factory はこの分岐でだけ `tool_manager` / `tool_executor` を渡す。**同じ分岐に入れれば、自作 Agent でも MCP がそのまま使える。** Claude の回答にあった「自作 Agent にすると MCP が使えなくなる」というトレードオフは、継承で消えた。

差分は `ConversationalAI/patches/017-midori-agent.patch` に保存した（本家はフォーク前で push 先が無いため。#010 と同じ扱い）。

```bash
git diff -- src/open_llm_vtuber/agent/agent_factory.py src/open_llm_vtuber/config_manager/agent.py \
  > ~/Develop/project-physical-ai/ConversationalAI/patches/017-midori-agent.patch
```

みどりのときだけこの Agent を使うよう、キャラクター YAML で切り替える。

```yaml
  # 自作 Agent（Build Log #017）。本体は ConversationalAI/agent/midori_agent.py。
  agent_config:
    conversation_agent_choice: 'midori_agent'
```

#### 動作確認用の組み立てスクリプト

GUI を起動せずに試すため、OLV と同じ部品（Ollama の LLM、MCP の各部品、Live2D モデル）で `MidoriAgent` を組み立てて会話させるスクリプトを書いた（`service_context.py` の `_init_mcp_components` と同じ手順）。

```python
# e2e.py（抜粋）
reg = ServerRegistry(); ad = ToolAdapter(server_registery=reg)
_, oa, cl = await ad.get_tools(["time", "ddg-search"])
_, raw = await ad.get_server_and_tool_info(["time", "ddg-search"])
tm = ToolManager(formatted_tools_openai=oa, formatted_tools_claude=cl, initial_tools_dict=raw)
te = ToolExecutor(MCPClient(reg, send_text, "e2e"), tm)
llm = OllamaLLM(model="qwen3-vl-32k", base_url="http://localhost:11434/v1", ...)
agent = MidoriAgent(llm=llm, system=system, live2d_model=Live2dModel("mao_pro"),
                    use_mcpp=True, tool_manager=tm, tool_executor=te,
                    tts_preprocessor_config=TTSPreprocessorConfig(**conf['character_config']['tts_preprocessor_config']))
async for o in agent.chat(BatchInput(texts=[TextData(source=TextSource.INPUT, content=u)])): ...
```

```bash
PYTHONPATH=. uv run --no-sync python e2e.py
```

（`PYTHONPATH=.` が無いと `No module named 'src'` で落ちる。`TTSPreprocessorConfig` を渡さないと pydantic の検証で落ちる）

#### つまずき1：`chat()` を上書きしても呼ばれない

最初の版は `chat()` をオーバーライドしたが、事前検索のログが一行も出なかった。

```bash
grep -n "self.chat\b\|self.chat =" src/open_llm_vtuber/agent/agents/basic_memory_agent.py
```

```python
    def _set_llm(self, llm: StatelessLLMInterface):
        """Set the LLM for chat completion."""
        self._llm = llm
        self.chat = self._chat_function_factory()   # ← インスタンス属性でクラスの chat を隠す
```

`BasicMemoryAgent` は初期化時に `self.chat` をインスタンス属性で差し替える。そのため、サブクラスの `chat()` は一度も呼ばれない。**`_chat_function_factory` をオーバーライドして、親が作った関数を包む**形に変えた。

#### つまずき2：検索にタイムアウトを付けると MCP の接続が壊れる

```text
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
```

`asyncio.wait_for` で包んだら、これが出た。同じタスクのままタイムアウトを掛けられる `anyio.fail_after` に替えても、`Attempted to exit a cancel scope that isn't the current tasks's current cancel scope` が出た。

原因：`MCPClient` は、**最初に呼ばれたときに** MCP サーバーへの stdio 接続を開く。その接続の内側の cancel scope が、外側に掛けたタイムアウトの範囲の中で作られる。そのため、範囲を抜けるときに食い違う。OLV 本体のツール呼び出しにもタイムアウトは無いので、合わせて外した。

#### できあがり

<!-- 会話例はテスト用の質問文を含むので、Build Log 検索の対象から外す -->
<!-- rag:ignore-start -->
```text
>> じゃあ、今日 の フィジカル  A ニュース を 調べ て みよ うか ニュース 見 て もら って も いい。
[MidoriAgent: 事前検索 query='フィジカルAIニュース'（835字）]
<< さっきの検索結果から、ちょっと気になるニュースを3つ紹介するね！
   1.AVerMediaがNVIDIA Jetson Thor対応の超小型ボードD333を発売した！
   2.西武鉄道で「ugo mini」が池袋変電所に常駐実証中だよ。
   3.NVIDIAのジェンスン・ファンCEOがCESでPhysical AIの重要性を語ってるって。
>> 今日って何曜日だっけ？
<< 今日は2026年10月1日、木曜日だよ！
```
<!-- rag:ignore-end -->

紹介した3件は検索結果の要約から来ていて、自分では原典を確認していない。事前検索にかかる時間は、検索語の作成と検索を合わせて約1.5秒。

#### 機能を足すときの手順

今後、事前に差し込む情報を増やすとき（たとえば SO-101 の状態や、当日の収録メモ）の手順：

1. `ConversationalAI/agent/` に、Agent に依存しない純粋なモジュールを書く（`build_log_rag.py` と同じ形）。単体で `python xxx.py` で試せるようにする
2. OLV 側の `src/open_llm_vtuber/agent/agents/` にシンボリックリンクを張る
3. `midori_agent.py` に、発動条件（正規表現）と `_xxx_context()` を足し、`chat_with_context` の振り分けに1行加える
4. 足す文は、**何も見つからなかったときも明示する**（節11の教訓）
5. `e2e.py` 相当の組み立てスクリプトで、LLM まで通して確かめる
6. バックエンドを再起動し、**新しい会話で**試す（古い履歴に引きずられないように）

OLV 本体（factory と設定の型）に触るのは、Agent の種類を増やすときだけ。機能の追加では触らない。

### 7. MCP の使い方と、Build Log 検索を MCP サーバーにしなかった理由

今日は **MCP サーバーを新しく作っていない。** 既存の MCP サーバー（`time`、`ddg-search`）の設定を直し、OLV の MCP の仕組みを自作 Agent から直接呼んだ。ここに仕組みを整理しておく。

#### OLV の中の MCP

`service_context.py` の `_init_mcp_components` を読んだ範囲での流れ：

```
mcp_servers.json（サーバーの起動コマンド）
conf.yaml の mcp_enabled_servers（使うサーバー名）
    ↓
ServerRegistry ── サーバー定義を読む
ToolAdapter.get_tools() ── 各サーバーに list_tools して
    ├─ OpenAI 形式／Claude 形式のツール定義
    └─ MCP prompt string（ツール説明の文章。今回 5573 字）
ToolManager ── ツール名 → どのサーバーのツールか、を持つ
MCPClient ── 実際の stdio 接続。最初に呼ばれたときにサーバーを起動して繋ぐ
ToolExecutor ── ツール呼び出しを実行して、結果を LLM 向けに整形する
    ↓
BasicMemoryAgent（use_mcpp: True のとき）
    └─ LLM が tool_calls を返したら ToolExecutor で実行 → 結果を渡してもう一度 LLM
```

#### MCP サーバーを足す手順（設定だけで済む）

```json
// mcp_servers.json
{
  "mcp_servers": {
    "time":       { "command": "uvx", "args": ["mcp-server-time", "--local-timezone=Asia/Tokyo"] },
    "ddg-search": { "command": "uvx", "args": ["duckduckgo-mcp-server"] }
  }
}
```

```yaml
# conf.yaml の agent_settings.basic_memory_agent
use_mcpp: True
mcp_enabled_servers: ["time", "ddg-search"]
```

#### LLM を通さず、コードから MCP のツールを呼ぶ

`MidoriAgent` の事前検索は、`BasicMemoryAgent` が受け取っている `ToolExecutor` をそのまま使う。

```python
is_error, text, metadata, content_items = await self._tool_executor.run_single_tool(
    "search",                 # ツール名（ToolManager が ddg-search のツールだと知っている）
    "midori-presearch",       # 呼び出し ID（ログ用。任意の文字列でよい）
    {"query": query, "max_results": 5, "region": "jp-jp"},
)
```

返り値の `text` は、ツールが返した最初のテキスト。DuckDuckGo の結果には `URL:` の行が入っている。読み上げても意味が無く、コンテキストも食うので落としてから差し込んだ。

#### Build Log 検索を MCP サーバーにしなかった理由

最初の計画は「Build Log を検索する MCP サーバーを1つ繋ぐ」だった。ところが今日の計測で、**この 8B モデルは MCP のツールを確実には呼ばない**と分かった（時刻 3/8、ニュース 0/6）。Build Log 検索を MCP サーバーにすると、検索の品質がどれだけ良くても、呼ばれなければ意味が無い。

そこで、検索の本体（`build_log_rag.py`）は MCP にも Agent にも依存しない、ただの Python モジュールにした。今は Agent から直接呼んでいる。将来、ツールを確実に呼ぶ大きなモデルに替えたら、このモジュールを包むだけで MCP サーバーにできる。以下はその場合の形のメモで、**実行していない・未検証**。

```python
# （未実装・未検証のメモ）build_log_rag を MCP サーバーにする場合
from mcp.server.fastmcp import FastMCP
from build_log_rag import BuildLogIndex

mcp = FastMCP("build-log")
index = BuildLogIndex()

@mcp.tool()
def search_build_log(query: str) -> str:
    """Project Physical AI の開発記録（Build Log）を検索する"""
    return "\n\n".join(f"{c.label}\n{c.text}" for _, c in index.search(query, top_k=3))

if __name__ == "__main__":
    mcp.run()
```

### 8. 長期記憶は見送り、Build Log の RAG へ

長期記憶の設計（「覚えて」で保存するか、会話の終わりに自動で抽出するか、など）を詰めかけたところで、方針を変えた。**長期記憶は中止し、Build Log の RAG に注力する。** 会話の記憶より先に、すでに書いてある記録を引けるほうが価値が大きい。

### 9. Build Log RAG の設計

#### 要件

- みどりが、過去の Build Log に書いた事実で答える。「Irodori-TTS を採用したのはいつ？」→「#013」
- 記録に無いことは、無いと言う
- VRAM を使わない（空きは約 1.4 GB）
- Build Log を書き足したら、自動で検索対象になる

#### 量

```bash
cd ~/Develop/project-physical-ai/build-log
wc -m build-log-*.md | tail -1
```

16ファイルで **233,172字**。32k トークンのコンテキストには入らないので、検索が必須。

#### 決めたこと

| 項目 | 選んだもの | 選ばなかったもの・理由 |
|---|---|---|
| 検索方式 | **BM25**（キーワードの出現頻度で点数を付ける古典的な方式） | 埋め込みモデル（意味で検索する方式）：VRAM の空きが約 1.4 GB しかない |
| 日本語の区切り | **文字 bigram**（2文字ずつ） | 形態素解析器（MeCab 等）：依存が増える。固有名詞は別途扱う（後述） |
| 断片の単位 | **`###` の節**。長い節は約1200字で、段落の切れ目で分ける | ファイル単位：1ファイル最大4.9万字（#009）で大きすぎる |
| いつ検索するか | **発話のキーワードで判定**（コード側） | LLM にツールとして渡す：節4・5のとおり呼ばない |
| 渡し方 | 上位3件を、そのターンだけシステムプロンプトに足す | 会話履歴に残す：コンテキストを食い、次の返事が引きずられる |
| 索引の更新 | 毎回ファイルの更新時刻を見て、変わっていたら作り直す | 手動で作り直す：書き足すたびに忘れる |

各断片の先頭には「Build Log #013（2026-09-05）／24. Irodori 自身に佐倉みどりの声を作らせる」のような見出しを付ける。答えるときに、何回目の話かを言えるようにするため。

#### 発動の条件と振り分け（`midori_agent.py`）

```python
# Build Log を引く発話。Web 検索の条件と重なったら（「Build Log を調べて」）こちらを優先する
BUILD_LOG_TRIGGER = re.compile(
    r"ビルド\s*ログ|build\s*log|前に|以前|この前|前回|最近|あの時|あのとき"
    r"|だっけ|たっけ|覚えてる|何回目|どの回|[#＃]\s*\d+|\d+\s*回目",
    re.IGNORECASE,
)
BUILD_LOG_RECENT = re.compile(r"前回|この前|最近")
BUILD_LOG_NUMBER = re.compile(r"[#＃]\s*(\d{1,3})|(\d{1,3})\s*回目")
BUILD_LOG_MIN_SCORE = 13.0   # 最初は 18。下げた経緯は節13
```

| 発話 | 動き |
|---|---|
| 「#13 で何やった？」「13回目」 | その回に絞って検索する |
| 最高点が 13 以上 | 上位3件を渡す |
| 最高点が 13 未満で、「前回」「この前」「最近」を含む | 最新の回の冒頭2件を渡す |
| 最高点が 13 未満で、それ以外 | **「当てはまる記録は見つからなかった」と明示して渡す**（節11） |

ASR は日本語の語の間に空白を入れる（「調べ て みよ うか」）。空白で bigram が切れるので、検索の前に詰める。

```python
_ASR_SPACE = re.compile(r"(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])")
```

#### 実装（`build_log_rag.py`）

全体は `ConversationalAI/agent/build_log_rag.py`（約170行、標準ライブラリだけ）。要所：

```python
# シンボリックリンク経由で読み込まれても、実体のあるリポジトリの build-log/ を指す
BUILD_LOG_DIR = Path(__file__).resolve().parents[2] / "build-log"

def tokenize(text: str) -> list[str]:
    """英数字の語とカタカナ語はそのまま、日本語は文字 bigram に分ける。"""
    tokens = name_tokens(text)            # [a-z0-9][a-z0-9_.\-]* と、カタカナ3文字以上
    for run in _NON_JA.split(text.lower()):
        tokens += [run[i : i + 2] for i in range(len(run) - 1)]
    return tokens
```

```python
# 索引：節タイトルは本文の3回分として数える
self._tfs = [Counter(tokenize(c.section) * SECTION_WEIGHT + tokenize(c.text)) for c in self.chunks]
idf = log(1 + (N - df + 0.5) / (df + 0.5))

# 検索：固有名詞らしいトークン（英数字の語・カタカナ語）は検索語側で3倍
q = {t: (NAME_WEIGHT if t in names else 1.0) for t in tokenize(query)}
score += weight * idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * len / avg_len))   # k1=1.5, b=0.75
```

見出しの判定では、**コードブロック内の `# コメント` を見出しと取り違えない**ようにした。#011 のシェルの `# Python 3.12 でプロジェクトを初期化` などが、節タイトルとして拾われていた。

単体で試せる。

```bash
cd ~/Develop/project-physical-ai/ConversationalAI/agent
python3 build_log_rag.py キャリブレーション
```

```text
 56.46  Build Log #004（2026-07-26）／7. キャリブレーション  (958字)
 53.55  Build Log #007（2026-07-28〜07-29）／6. qwen2.5:latest vs qwen3:8b 速度比較（temperature 1.0、デフォルト）  (341字)
 48.78  Build Log #004（2026-07-26）／7. キャリブレーション  (1061字)
```

OLV 側にもシンボリックリンクを張る。

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
ln -s ~/Develop/project-physical-ai/ConversationalAI/agent/build_log_rag.py \
      src/open_llm_vtuber/agent/agents/build_log_rag.py
```

#### 1ターンのデータの流れ

<!-- 例に評価用の質問を使っているので、Build Log 検索の対象から外す -->
<!-- rag:ignore-start -->
```text
発話（ASR）「R1 って 何 キロ あった っけ」
  ↓ 日本語の間の空白を詰める（_ASR_SPACE）
「R1って何キロあったっけ」
  ↓ BUILD_LOG_TRIGGER に当たる（「たっけ」）→ Build Log 検索へ
  ↓ 「#13」「13回目」が無いか見る（BUILD_LOG_NUMBER）→ 無し
  ↓ 発動語を検索語から外す（BUILD_LOG_TRIGGER.sub）
「R1って何キロあっ 」（「たっけ」が外れる）
  ↓ tokenize：英数字の語・カタカナ語 ＋ 日本語の bigram
["r1", "って", "て何", "何キ", "キロ", "ロあ", "あっ"]   ← r1 は固有名詞扱いで重み3倍
  ↓ BuildLogIndex.search（索引はファイルの更新時刻が変わったときだけ作り直す）
上位3件：#001／今日やったこと（19.4点）、#013／18. …、#016／1. …（最高点が 13 以上なので採用）
  ↓ 見出し付きで連結し、答え方の指示を添えて、このターンだけシステムプロンプトに足す（約1,500字）
LLM → 「Unitree R1 は約25kgあったよ」
```
<!-- rag:ignore-end -->

#### 索引の作り方

| 段階 | 内容 |
|---|---|
| 1. ファイルを集める | `build-log/build-log-*.md`。パスは `Path(__file__).resolve().parents[2] / "build-log"`。シンボリックリンク経由で読み込まれても、実体のあるリポジトリを指す |
| 2. 目印の範囲を飛ばす | `<!-- rag:ignore-start -->`〜`<!-- rag:ignore-end -->`（節12） |
| 3. 節に分ける | `#`〜`###` の見出しで区切る。コードブロック内の `#` は見出し扱いしない。1行目の `# Build Log #017 — 2026-10-01` から回の番号と日付を取る |
| 4. チェックボックスを言葉にする | `- [ ]` →「（未着手）」、`- [x]` →「（済）」。LLM が未着手の TODO を「やった」と読んだため（節13） |
| 5. 長い節を切る | 1200字を超えたら、1200字以内で最後の空行（段落の切れ目）で切る。空行が前すぎる（400字未満）ときは1200字で切る |
| 6. トークン化 | 節タイトル×3 ＋ 本文を `tokenize` |
| 7. BM25 の統計 | 断片ごとの出現回数、断片の長さ、平均の長さ、各トークンの idf |

今の索引：17ファイル、**388断片**（中央値 約620字、最大 1200字）、語彙 約17,600トークン。作り直しは一瞬で、発話のたびに更新時刻を確かめても体感の遅れは無い。

#### パラメータと、そう決めた理由

| パラメータ | 値 | 理由 |
|---|---|---|
| `CHUNK_MAX_CHARS` | 1200 | 3件渡しても約1,500〜3,600字に収まる。32k トークンのコンテキストに対して軽い |
| `BM25_K1` / `BM25_B` | 1.5 / 0.75 | BM25 で一般的な値。調整していない |
| `NAME_WEIGHT` | 3.0 | 英数字の語・カタカナ語を、検索語側で3倍に数える（節10） |
| `SECTION_WEIGHT` | 3 | 節タイトルを本文の3回分として数える（節10） |
| `BUILD_LOG_TOP_K` | 3 | 1位を外しても上位3件には入る（評価で 29/29） |
| `BUILD_LOG_MIN_SCORE` | 13.0 | Build Log と無関係な雑談（最大 9.1 点）と、本当の質問（最低 17.8 点）の間。**役目は雑談を弾くことだけで、「記録に無い質問」は見分けられない**（節13） |
| 「前回」のときの件数 | 最新の回の冒頭2件 | 「今日やったこと」と最初の節が入る |

#### LLM に渡す文の形

```text
## ドクターの開発記録（Build Log）から、いまの話に関係しそうな部分
### Build Log #001（目の前で動くヒューマノイドに触った日）／今日やったこと
（断片の本文）

### Build Log #013（2026-09-05）／18. 実機で Camera と Screen が動いた
（断片の本文）

（3件目）

これはドクターと一緒にやってきた実験の記録。関係があれば、何回目の Build Log の話かを
添えて、話し言葉で短く答える。回の番号は各見出しの「#」の後の数字をそのまま使い、
数え直さない。記録に書かれていないことは推測で補わず、「記録には無いみたい」と言う。
```

見つからなかったときは、`## ドクターの開発記録（Build Log）を探した結果` という見出しで「当てはまる記録は見つからなかった。回の番号や出来事を作らない」と渡す（節11）。

断片はそのまま渡しているので、画像のリンク（`![...](images/...)`）や表の罫線もそのまま入る。読み上げには影響していないが、無駄ではある。

<!-- 節10・11は評価用の質問文をそのまま含むので、みどりの Build Log 検索（build_log_rag.py）の対象から外す -->
<!-- rag:ignore-start -->

### 10. 検索の評価と、重み付けを足した理由

各回から1問ずつ、口語の質問と正解の回を用意して、正解の回が1位に来るかを数えた。評価は `ConversationalAI/agent/eval_build_log_rag.py` に残した（重みやしきい値を変えたら回す）。

```bash
cd ~/Develop/project-physical-ai/ConversationalAI/agent
python3 eval_build_log_rag.py
```

| 段階 | 1位に正解 | 何が起きていたか |
|---|---|---|
| bigram だけ | 14/16 | 「キャリブレーションっていつやったっけ」で #007 が1位。「n-cpu-moe に切り替えた理由は」で #010 が1位 |
| ＋ 英数字の語・カタカナ語を検索語側で3倍 | 15/16 | `n-cpu-moe` は直った |
| ＋ 節タイトルを本文の3回分として数える | **16/16** | キャリブレーションも直った |
| ＋ 発動語（Build Log、だっけ、#13 等）を検索語から外す | 16/17 | 「Build Log を調べて、キャリブレーションの話」を1問追加。#004 は2位・3位に入る |

外れた原因の調べ方：

```bash
python3 build_log_rag.py n-cpu-moe                     # 単独なら #014 が上位5件を独占（5.85点）
python3 -c "from build_log_rag import tokenize; print(tokenize('n-cpu-moe に切り替えた理由は'))"
grep -c "キャリブレーション" ../../build-log/build-log-*.md | grep -v ":0"
```

- **カタカナの長い語が bigram で薄まる。**「キャリブレーション」の bigram には「ーシ」「ショ」「ョン」があり、「バージョン」などと共通する。
- **#007 は検索の誤りとも言い切れない。** #007 では「SO-101のキャリブレーションでよくある失敗は？」を、LLM の速度比較用の質問文として使っていた。341字の短い断片なので、BM25 では有利になる。一方 #004 は、節タイトルがそのまま「7. キャリブレーション」。そこで節タイトルの重みを上げた。
- **英数字の固有名詞が、口語部分の bigram の合計点に負ける。** 「切り替えた理由は」の bigram が7つあり、`n-cpu-moe` の1トークン分を上回っていた。
- **「Build Log」という言葉自体が全部の回に当たる。** 英単語なので固有名詞扱いで3倍になり、余計な点が入っていた。

**調整に使った16問で 16/16 なのは、問題に合わせて直した結果。** そこで、調整後に初めて当てる12問を別に用意した。

| 問題 | 1位に正解 | 上位3件に正解 |
|---|---|---|
| 調整に使った問題（TUNING） | 16/17 | 17/17 |
| **調整に使っていない問題（HELD_OUT）** | **11/12** | **12/12** |

HELD_OUT で外れた1問は「Day3のポリシーが失敗した原因は」（正解 #009 が2位、1位は #008）。上位3件を渡すので、LLM には正しい記録が届く。これ以上はこの問題に合わせすぎになるので、調整はここで止めた。

**質問はすべて自分たちで書いたもの。** 実際に音声で聞くときの言い回しで同じ成績が出るかは、使ってみないと分からない。

#### しきい値の決め方（最初は 18）

「だっけ」「前に」で発動はするけれど、Build Log とは関係ない発話のスコアを見た。

| 発話 | 発動語を外す前 | 外した後 |
|---|---|---|
| 今日って何曜日だっけ | 7.9 | 7.9 |
| 前に何の話してたっけ | 8.7 | 8.7 |
| この前のこと覚えてる？ | 16.5 | 7.9 |
| 前回は何をしたっけ | 9.1 | （「前回」なので最新の回を渡す） |
| 本当の質問（評価用の質問すべて） | 20.5 以上 | 20.5 以上 |

外す前は、無関係な発話の最高が 16.5、本当の質問の最低が 20.5 で、その間の 18 にした。発動語を外したら、無関係な側は 8.7 以下まで下がって、差が広がった。

この 18 は後で 13 に下げた（節13）。

### 11. LLM まで通したテスト

```bash
cd ~/development/open-llm-vtuber-lab/Open-LLM-VTuber
PYTHONPATH=. uv run --no-sync python e2e_rag.py
```

| 質問 | 1回目 | 対策後 |
|---|---|---|
| Irodori-TTS を採用したのっていつだっけ？ | ✓「2026年9月5日の Build Log #013」 | — |
| R1 って何キロあったっけ？ | ✓「約25kg。『寝た子供』みたいに感じた」。#001 に実際にそう書いてある（`grep -n "寝た" build-log-001.md` で確認） | — |
| 前回は何をしたっけ？ | △ 内容（ComfyUI）は正しいが「#015」と言った。渡したのは #016 | ✓「#016 の Build Log」（2回とも） |
| SO-101 で洗濯物を畳んだのって何回目だっけ？ | **✗「第3回目、ハンカチを落とした」** | ✓「記録に全然ないよ」（2回とも） |

4問目がいちばん大事な失敗だった。検索は「該当なし」（16.7 < 18。当時のしきい値）と判断して、**何も渡さなかった。** するとモデルは、空白を作り話で埋めた。そこで、見つからなかったときも黙らず、そのことを明示して渡すようにした。

```python
return (
    "\n\n## ドクターの開発記録（Build Log）を探した結果\n"
    "いまの話に当てはまる記録は見つからなかった。過去の実験の話なら、"
    "記録には無いみたいと正直に言う。回の番号や出来事を作らない。"
)
```

3問目には、指示を1文足した。「回の番号は各見出しの『#』の後の数字をそのまま使い、数え直さない」。

その後、実機（OLV を再起動して新しい会話）でも動作を確認した。

<!-- rag:ignore-end -->

### 12. この Build Log 自体が検索を汚した

この Build Log を書き終えて評価を回し直すと、成績が落ちた。

| | 書く前 | 書いた直後 | 対策後 |
|---|---|---|---|
| 調整に使った問題で1位 | 16/17 | 13/17 | 16/17 |
| 調整に使っていない問題で1位 | 11/12 | 10/12 | 11/12 |
| 無関係な発話がしきい値を超えた数 | 0/4 | 1/4（21.1点） | 0/4 |

原因は、この #017 に**評価用の質問文がそのまま載っている**こと。どの質問を投げても、答えの回より先に「その質問を評価に使った」と書いた #017 が当たる。RAG の記録を RAG で検索する以上、避けられない構図だった。

対策として、HTML コメントの目印で囲んだ範囲を索引から外せるようにした（`build_log_rag.py`）。GitHub 上の表示には影響しない。

```markdown
<!-- rag:ignore-start -->
（評価用の質問文や、テストの会話例）
<!-- rag:ignore-end -->
```

この Build Log では、節10・11と節6の会話例を囲んだ。囲んだ後も、#017 の本来の話題（MidoriAgent、32k への拡張、RAG の設計）は #017 で引ける。

```bash
cd ~/Develop/project-physical-ai/ConversationalAI/agent
python3 eval_build_log_rag.py
python3 build_log_rag.py MidoriAgent を作ったのはいつ   # → #017「6. 自作 Agent」
```

**今後、会話のテストや評価の質問文を Build Log に載せるときは、この目印で囲む**（ルートの CLAUDE.md に追記）。

#### 目印の実装で、もう一度つまずいた

最初の実装は「行のどこかに目印の文字列があれば反応する」だった。この Build Log の節9の表で、目印を**説明として文中に書いた行**にも反応した。その結果、そこから次の終了の目印まで、節9の後半（索引の作り方、パラメータ、LLM に渡す文の形）がまるごと索引から消えていた。目印の数を数えたら、4つのはずが5つあって気づいた。

```bash
grep -c "rag:ignore-start" build-log-017.md
python3 -c "from build_log_rag import split_file; from pathlib import Path; \
  print(sorted({c.section for c in split_file(Path('../../build-log/build-log-017.md'))}))"
```

直した後の条件は「**コードブロックの外で、その行が目印だけ**」のときに限る、というもの。節12のコード例の中の目印にも反応しない。

### 13. しきい値では「記録に無い質問」を見分けられない

節12の対策の後、この Build Log に節を書き足していくと、評価用の質問の1つ（R1 の重さ）が 19.4 → **17.8 点**に下がり、しきい値 18 を割った。#017 の文章が増えて、索引全体の統計（各トークンの idf、断片の平均の長さ）が動いたため。

しきい値を下げる前に、答えが**無い**質問の点数を見た。ここで考えが変わった。

**結論：BM25 の点数では、答えのある質問と無い質問を分けられない。** 答えの無い質問でも、話題の言葉（Tシャツ、ロボット、SO-101）は多くの回に出てくるので、点数は高くなる。節11で洗濯物の質問が「該当なし」になったのは、たまたま点数が低かっただけだった。

そこで役割を分け直した。

| 守り | 担当 |
|---|---|
| Build Log と無関係な雑談に、記録を差し込まない | しきい値（13 に下げた。雑談は最大 9.1 点、本当の質問は最低 17.8 点） |
| 記録に無いことを作り話しない | 差し込む文の指示「記録に書かれていないことは推測で補わず、『記録には無いみたい』と言う」 |

<!-- 以下は評価・テスト用の質問文を含むので、Build Log 検索の対象から外す -->
<!-- rag:ignore-start -->
| 質問（答えは記録に無い） | 最高点 | 1位の断片 |
|---|---|---|
| Tシャツを畳めたのはいつだっけ | 40.3 | #001／次にやること |
| ロボットが料理したのはいつだっけ | 32.6 | #001／4. 高所点検ロボット |
| SO-101で洗濯物を畳んだのって何回目だっけ | 32.0 | #017／で、これは自分の SO-101 にとって… |
| （参考）R1って何キロあったっけ ※答えは #001 | 17.8 | #001／今日やったこと |

```bash
cd ~/Develop/project-physical-ai/ConversationalAI/agent
python3 eval_build_log_rag.py
python3 -c "
from build_log_rag import BuildLogIndex
from eval_build_log_rag import BUILD_LOG_TRIGGER
i = BuildLogIndex()
for q in ['Tシャツを畳めたのはいつだっけ', 'ロボットが料理したのはいつだっけ']:
    print([(round(s, 1), c.label[:45]) for s, c in i.search(BUILD_LOG_TRIGGER.sub(' ', q), 2)], q)"
```

しきい値を 13 にして、答えの無い質問を LLM まで通した。

| 質問 | 答え | 判定 |
|---|---|---|
| Tシャツを畳めたのはいつだっけ | 「まだ正式な成功日は決まってない」＋「**報酬関数も紙に書いた記録がある**」 | △ 核心は正しいが、付け足しが誤り |
| ロボットが料理したのはいつだっけ | 「まだ料理の自動化が実現していないよ」 | ✓ |
| SO-101で洗濯物を畳んだのって何回目だっけ | 「記録には『洗濯物（North Star）をまだ畳んでいない』って書かれている」 | ✓（#017 自身の記述を引いている） |
| R1って何キロあったっけ | 「25kg」＋「**実機の動画で確認した**」 | △ 核心は正しいが、付け足しが記録と逆（実際は触った。#001 は「動画で見るのと、目の前で動くのは、違う」） |

「報酬関数も紙に書いた」の出どころは、#001 の**未チェックの TODO** だった。

```bash
grep -n "報酬関数\|発熱\|動画で" build-log-001.md
```

```markdown
- [ ] Tシャツ折り畳みの報酬関数を、紙の上で一度書いてみる（動くかどうかは別として）
```

LLM は `- [ ]` を「やった」と読んだ。断片を作るときに `- [ ]` を「（未着手）」、`- [x]` を「（済）」に書き換えるようにした（`build_log_rag.py` の `flush()`）。同じ質問を2回試すと、2回とも「まだ未着手だよ」「#001 に『未着手』ってある」と答えた。

「実機の動画で確認した」のほうは、記録の取り違えではなく LLM の付け足しで、まだ直していない。
<!-- rag:ignore-end -->

---

## 変更したファイル

| ファイル | 内容 |
|---|---|
| `ConversationalAI/agent/midori_agent.py` | 新規。自作 Agent（日付の注入・Web の事前検索・Build Log 検索の振り分け） |
| `ConversationalAI/agent/build_log_rag.py` | 新規。Build Log の BM25 検索 |
| `ConversationalAI/agent/eval_build_log_rag.py` | 新規。検索の評価（29問＋無関係な発話4つ） |
| `ConversationalAI/patches/017-midori-agent.patch` | 新規。OLV 本体の2箇所の差分 |
| `ConversationalAI/patches/README.md` | 上のパッチの説明と適用手順 |
| `ConversationalAI/sakura_midori.yaml` | 時刻ルールを1行追加、`conversation_agent_choice: 'midori_agent'` を追加 |
| `ConversationalAI/start-midori.sh` | `LLM_MODEL="qwen3-vl-32k"` |
| `ConversationalAI/CLAUDE.md` | 構成表（LLM の行）、ファイル一覧に `agent/` を追加 |
| `CLAUDE.md`（ルート） | Build Log に質問文や会話テストを載せるときは `rag:ignore` で囲む、という指示を追加 |

リポジトリの外：

| 場所 | 内容 |
|---|---|
| OLV `mcp_servers.json` | `Asia/Tokyo` |
| OLV `conf.yaml` | `ollama_llm.model: 'qwen3-vl-32k'`（元は `conf.yaml.before-32k`） |
| OLV `src/.../agent_factory.py`, `config_manager/agent.py` | `midori_agent` の登録（パッチと同じ内容） |
| OLV `src/.../agents/midori_agent.py`, `build_log_rag.py` | このリポジトリへのシンボリックリンク |
| Ollama | `qwen3-vl-32k` を作成。Modelfile は `~/ollama-modelfiles/qwen3-vl-32k.Modelfile` |
| `/etc/systemd/system/ollama.service.d/kv-cache.conf` | `OLLAMA_KV_CACHE_TYPE=q8_0`、`OLLAMA_FLASH_ATTENTION=1`（全モデル共通） |

---

### で、これは自分の SO-101 にとってどういう意味があるのか

みどりは「SO-101 の実験を隣で見守る研究仲間」という設定。これまでは、実験の話をしても、その日の会話の外にある記録を何も知らなかった。今日から、#001 から積んできた Build Log を引いて答えられる。

- 過去の実験の「いつ・何を・なぜ失敗したか」に、記録で答えられる。自分の記録を自分で探す手間が減る
- **記録に無いことは無いと言う。** 洗濯物（North Star）をまだ畳んでいないことも、ちゃんと「無い」と答えた。作り話の相棒より、ずっと信用できる
- Build Log を毎日書くことが、そのまま相棒の記憶になる。「日々の義務は Build Log だけ」（CONVENTIONS）が、別の意味でも効いてくる

---

## 今日の学び

- **8B のローカル LLM に「ツールを呼ぶかどうか」を任せない。** 時刻 3/8、ニュース 0/6。プロンプトのルールで直るもの（時刻）と、直らないもの（ニュース）がある。呼ぶべき場面をコードで判定して、結果を先に渡すほうが確実だった
- **会話履歴は、プロンプトより強い。** 誤答や「検索するね」で終わった返事が履歴に残ると、モデルはそれをなぞる。直したら新しい会話で試す
- **何も渡さないと、モデルは空白を作り話で埋める。** 「探したけれど無かった」ことも、情報として渡す
- **Claude の調査結果は、手元のコードで裏取りする。**「Mem0 のコードは参考用に残っている」は、実際は0バイトのファイルだった。「自作 Agent では MCP が使えない」も、継承すれば回避できた
- **ライブラリの中身を読まないと分からない罠がある。** `chat()` のオーバーライドがインスタンス属性に隠される件と、MCP の stdio 接続がタイムアウトで壊れる件。どちらもエラーにならず、静かに効かないか、別の場所で壊れた
- **数字の目安を出したら、自分で検算する。** KV キャッシュの目安を「1224 MiB」と出したが、それは K だけの値だった。ログに `K (q8_0): 1224.00 MiB, V (q8_0): 1224.00 MiB` と内訳が出ていたので気づけた
- **RAG は、埋め込みモデルが無くても始められる。** 文字 bigram の BM25 と、固有名詞・節タイトルへの重み付けで、調整に使っていない問題でも 11/12 が1位、12/12 が上位3件に入った（質問は自作）
- **評価は「調整に使った問題」と「使っていない問題」を分ける。** 調整に使った問題で 16/16 になっても、それは問題に合わせて直した結果
- **検索の点数は「関係がありそう」しか測れない。** 答えの無い質問でも、話題の言葉が多くの回に出てくれば点数は高い。作り話を防ぐのは、しきい値ではなく「記録に無いことは言わない」という指示と、記録の書き方（未着手の TODO を明示する等）
- **RAG の記録を書くと、その記録が RAG を汚す。** 評価の質問文を載せた #017 が、その質問で1位になった。記録する側に「索引から外す」目印を用意した

## まだ測っていないこと

1. **しきい値 13 の余裕。** BM25 の点数は索引全体の統計で決まるので、Build Log が増えるたびに動く（節13で実際に 18 から下げた）。書き足したら `eval_build_log_rag.py` を回して、しきい値未満が出ていないか見る
2. **実際の音声入力での検索精度。** 評価用の29問は自分たちで書いたもの。ASR を通した実際の言い回しで、拾い漏れと無関係な記録の差し込みのどちらが多いか。ログの `MidoriAgent: Build Log 参照` と `該当なし（最高点 …）` を見て、しきい値 18 を調整する
3. **ツール呼び出しの割合の再現性。** 各条件6〜8回、temperature 0.9 での計測。傾向は見えたが、割合そのものは目安
4. **応答の遅れ。** Web の事前検索で約1.5秒増える（単独の計測）。話しかけてから声が返るまでの体感時間は未計測
5. **32k コンテキストの効果。** 長い会話で、古い話を覚えていられる時間が実際に延びたか
6. **記録に無い付け足し。** 核心は記録どおりでも、「実機の動画で確認した」のような付け足しが混ざる（節13）。2〜3文で短く、という persona の制約と、記録の要約のさせ方を見直す余地がある
7. **persona の崩れ。** テスト中に、許可していない絵文字（😅）、英語の混入（「remember？」）、番号付きの箇条書き、根拠の無い「師匠」呼びが出た。表情タグも `[neutral]` ではなく `[expression: joy]` の形に崩れることがある（OLV の表情プロンプトの例文 `[expression1]` を真似ている可能性。未確認）
8. **MCP の `time` サーバーの役割。** Agent が毎ターン日付を渡すようになったので、時刻を聞かれたとき以外は不要かもしれない。ツール説明（約5,600字）を削れるか


---

## 付録：ソースコード全文

<!-- コード中のコメントに評価用の質問文が含まれ、本文とも重複するので、Build Log 検索の対象から外す -->
<!-- rag:ignore-start -->

2026-10-01 時点。最新版はリポジトリの `ConversationalAI/agent/` を見る。評価スクリプトは `ConversationalAI/agent/eval_build_log_rag.py`、OLV 本体への登録は `ConversationalAI/patches/017-midori-agent.patch`（節6の diff と同じ）。

### `ConversationalAI/agent/midori_agent.py`

```python
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
```

### `ConversationalAI/agent/build_log_rag.py`

```python
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
```

<!-- rag:ignore-end -->

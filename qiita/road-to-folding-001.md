日本語で「黄色いブロックを片付けて」と頼むと、クラウドの AI が判断し、AWS IoT Core を通って、自宅のロボットアーム SO-101 が動く。そんな仕組みを個人で作りました。

<iframe width="560" height="315" src="https://www.youtube.com/embed/qCgUyA3GhOs" title="YouTube video player" style="border:0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" loading="lazy" allowfullscreen></iframe>

先に結果を書いておきます。2026-11-08 に実機で 3 回頼んで、**3 回とも指示から報告まで最後まで通りました。ただ、ブロックを掴めたのは 1 回だけ**です（動画はその 1 回）。成否はオペレーター（自分）が目で見て判定しています。

この記事で書くのは「動いた」ことより、**LLM にロボットのどこまでを任せたか**という設計の話です。

## 全体構成

```
[自分] --日本語--> aws lambda invoke
                        │
            ┌───────────▼───────────┐
            │ Lambda: 判断役          │  Strands Agents + Amazon Bedrock（Claude Haiku 4.5）
            │  tools: get_robot_status│
            │         dispatch_task   │
            │         get_result      │
            │         stop_robot      │
            └───┬───────────────▲───┘
 publish(QoS1)  │               │ S3 を読む
so101/<thing>/cmd│        ┌──────┴──────┐
                ▼        │ S3: results/ │
     ┌─────────────────┐ └──────▲──────┘
     │ AWS IoT Core     │────────┘ IoT ルール（result → S3）
     │ (MQTT5)          │
     └────────┬────────┘
 mTLS（証明書）│  status（retained）/ result
     ┌────────▼────────┐
     │ edge_agent.py    │  自宅の PC。状態機械・重複排除・TTL・停止
     │ → lerobot-rollout│  SmolVLA（模倣学習したモデル）
     └────────┬────────┘
              ▼
           SO-101
```

AI が 2 つあり、役割を分けています。

| | クラウドの AI（判断役） | 自宅の AI |
|---|---|---|
| 中身 | Claude Haiku 4.5（Bedrock） | SmolVLA（自分で集めたデモで学習） |
| 入力 | 自由な日本語 | カメラ 2 台の映像と関節の状態 |
| 出すもの | **タスク名だけ**（`pick_yellow_block`） | 関節の動き（30Hz） |

## 設計で決めたこと

### 1. LLM はツールを選ぶだけ

判断役が送れるのはタスク名だけです。関節の角度・座標・速度は送れません。決まったメニューから選ぶだけなので、LLM が間違えても被害は限られます。

### 2. ガードはプロンプトではなくコードで

システムプロンプトにも「IDLE でなければ頼まない」と書いていますが、それに頼らず、ツールの中で強制しています。

```python
ALLOWED_TASKS = {
    "pick_yellow_block": "黄色いレゴブロックを掴んで白いケースに入れる",
}

def dispatch_task(self, task: str) -> dict[str, Any]:
    if task not in ALLOWED_TASKS:
        return {"ok": False, "reason": "unknown_task", ...}
    if len(self.dispatched) >= self.max_dispatch:   # 1 回の依頼で 1 件まで
        return {"ok": False, "reason": "dispatch_limit", ...}
    st = self.get_robot_status()                    # 30 秒より古い status は UNKNOWN 扱い
    if st["state"] != "IDLE":
        return {"ok": False, "reason": "not_idle", ...}
    cmd = {"v": 1, "cmd_id": str(uuid.uuid4()), "type": "run_task", "task": task,
           "issued_at": ..., "ttl_s": CMD_TTL_S, "max_run_s": CMD_MAX_RUN_S}
    self.iot.publish(topic=self.topic["cmd"], qos=1, payload=json.dumps(cmd).encode())
```

（抜粋。全体は GitHub の `cloud/agent/tools.py`）

### 3. 確認をクラウドとエッジの両方で

ロボット側はクラウドを信用しません。エッジは届いた指令を、上から順に検査し、最初に当てはまったもので終わります。

1. スキーマ不正 → `rejected/invalid`
2. 同じ `cmd_id` が既知 → 再実行しない（完了済みなら前回の結果を再送）
3. `stop` → 実行中なら止める
4. `issued_at` から TTL を過ぎている → `rejected/expired`
5. 許可リストにないタスク → `rejected/unknown_task`
6. 実行中 → `rejected/busy`
7. 待機中 → 実行開始

MQTT の QoS 1 は同じメッセージが重複して届きうるので、2 の重複排除が要ります。同じ `cmd_id` を 2 回送る試験では、5 回中 5 回とも 1 回しか動きませんでした。

止めるときは、ポリシーのプロセスグループに SIGINT → 10 秒 → SIGTERM → 10 秒 → SIGKILL の順で送ります。`lerobot-rollout` は止められると、開始時の姿勢に 3 秒で戻ってから脱力することを実測で確かめたので、開始姿勢を「脱力しても安全な姿勢」にしています。

### 4. クラウドとエッジを直接つながない

Lambda は指令を IoT Core に publish し、結果は IoT ルールが S3 に書いたものを読むだけです。エッジは外向きに IoT Core へ接続するだけなので、自宅側に入口を開けずに済みます。結果は S3 に記録として残ります。

## LLM が「片付けました」と言いすぎた

作っている途中で、判断役が**何も動いていないのに**「完了しました！黄色いブロックを白いケースに片付けました。」と報告しました。実機を使わない FakeRunner で試していたときです。

原因は、`completed/ok` を「成功」と読んだことでした。ポリシーには成功を知らせる仕組みがなく、`completed/ok` は「動作が最後まで終わった」という意味でしかありません。

そこで、結果を返すツールに「その結果が何を意味し、何を意味しないか」をコードで添えるようにしました。

```python
@staticmethod
def _meaning(r: dict) -> str:
    label = r.get("operator_label")
    if r.get("state") == "completed":
        base = "ロボットの動作が最後まで終わった。"
    elif r.get("state") == "aborted":
        base = f"ロボットの動作は途中で止まった（{r.get('reason')}）。"
    else:
        base = f"エッジがこの指令を実行しなかった（{r.get('reason')}）。"
    if label == "success":
        return base + "オペレーターが目で見て、成功と判定した。"
    if label == "fail":
        return base + "オペレーターが目で見て、失敗と判定した。"
    return base + "ブロックがケースに入ったかどうかは、誰も判定していないので分からない。"
```

実機の 3 回では、判断役はオペレーターの判定どおりに報告しました。「片付けました」と言い切ったのは、成功と判定した 3 回目だけです。

## 実測値（2026-11-08）

**配送遅延（20 回、ロボットは動かさない FakeRunner）**

| 最小 | 中央値 | p90 | 最大 |
|---|---|---|---|
| 65.0 ms | 137.5 ms | 208.0 ms | 237.0 ms |

送信側とエッジが同じ PC なので時計のずれは入りませんが、経路は PC → IoT Core（東京）→ PC の往復です。一方向の遅延ではありません。

**実機（3 回）**

| # | 結果 | オペレーター判定 | Lambda → エッジ | 実行時間 | 呼び出し全体 |
|---|---|---|---|---|---|
| 1 | completed/ok | fail | 148 ms | 39.9 s | 57.9 s |
| 2 | completed/ok | fail | 100 ms | 39.9 s | 51.8 s |
| 3 | completed/ok | success | 48 ms | 39.7 s | 49.6 s |

「Lambda → エッジ」は、Lambda の時計とエッジの時計の差です。エッジの時計が約 30 ms ずれていた（NTP 未調整）ので参考値です。

実行時間の約 40 秒は、ほとんどがエッジでした（モデルの読み込みなどの起動 約 15 秒、動作 20 秒、開始姿勢に戻る後始末 約 5 秒）。配送は数十〜百数十 ms なので、判断をクラウドに置いても困らない、というのが今回の数字からの見立てです。

## つまずいたところ（抜粋）

- **Bedrock の Claude Haiku 5.5 が使えなかった。** Anthropic のユースケースの提出、利用契約を済ませたあとも、このアカウントではクォータが 0 でした。Haiku 4.5（`jp.` の推論プロファイル）に切り替えています
- **全角の「ｓ」でロボットが止まらなかった。** 日本語入力がオンのまま停止キーを打ったので全角になり、停止として扱われませんでした。止めたいときに止まらないのは安全に関わるので、入力を NFKC で正規化して直しました
- **retained の status が古いことがあった。** 更新から 0.8 秒たっても古い値が返ることがありました（5 回中 1 回。原因は調べていません）。「今の状態」の判定には反映の遅れを見込んでいます

## 環境

- ロボット：SO-101（リーダー・フォロワー）、カメラ 2 台（手首・俯瞰）
- エッジ：Ubuntu の PC（RTX 5060 Ti）、LeRobot 0.6.2、SmolVLA
- クラウド：AWS 東京リージョン。Lambda（Python 3.12）、Strands Agents 1.64.0、Bedrock `jp.anthropic.claude-haiku-4-5-20251001-v1:0`、IoT Core（MQTT5、X.509 証明書、最小権限の IoT ポリシー）、S3
- IaC：Terraform 1.17.1、AWS provider 6.72。証明書は CSR 方式で作り、秘密鍵を Terraform の state に入れていません

## 次にやること

- 成功の判定をカメラで自動にして、人の y/n をなくす
- SmolVLA の成功率を、回数を増やして数える（今は 3 回中 1 回）
- NTP を近いサーバーにして、一方向の遅延を正しく測る

## リンク

- 作業記録（Build Log #022）：https://github.com/emboss369/project-physical-ai/blob/main/build-log/build-log-022.md
- コード：https://github.com/emboss369/project-physical-ai/tree/main/build-log/so101aws
- YouTube：https://www.youtube.com/watch?v=qCgUyA3GhOs

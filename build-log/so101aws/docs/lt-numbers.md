# LT の数字（実験の記録）

CLAUDE.md §6 の実験の結果。新しいものを下に足す。

## E1 配送遅延（2026-11-08 22:19 JST）

- 条件: エッジ: Ubuntu PC（愛媛）、Wi-Fi 2.4GHz・IPv6 無効、FakeRunner
- 測ったもの: `received_at - issued_at`。issued_at は send_cmd.py（boto3 iot-data publish の直前）、received_at はエッジの受信時。**送信側とエッジが同じ PC** なので、時計のずれは入らない。経路は PC → IoT Core（東京）→ PC で、一方向ではない

| n | 最小 | 中央値 | p90 | 最大 | 平均 |
|---|---|---|---|---|---|
| 20 | 65.0 ms | 137.5 ms | 208.0 ms | 237.0 ms | 145.7 ms |

生データ（ms）: 237.0, 144.0, 138.0, 180.0, 206.0, 208.0, 90.0, 65.0, 127.0, 189.0, 214.0, 97.0, 106.0, 137.0, 114.0, 183.0, 183.0, 133.0, 81.0, 81.0

## E2 重複指令（2026-11-08 22:20 JST）

- 手順: run_task を送る → 0.8 秒後（実行中）に同じ cmd_id を送る → 完了後にもう一度同じ cmd_id を送る
- 合格: 実行中の重複は無視され（result は1件で reason=ok、busy にならない）、完了後の重複には前回とまったく同じ result が再送される（S3 のオブジェクトの LastModified だけが新しくなる）

| # | 重複を送ったときの状態 | 1回目の result | 再送された result | 判定 |
|---|---|---|---|---|
| 1 | RUNNING | completed/ok | 同じ | OK |
| 2 | RUNNING | completed/ok | 同じ | OK |
| 3 | RUNNING | completed/ok | 同じ | OK |
| 4 | IDLE | completed/ok | 同じ | NG |
| 5 | RUNNING | completed/ok | 同じ | OK |

**4/5 合格**（判定方法の誤り。下の再測定を正とする）

> 注: #4 の NG はエッジの不具合ではない。エッジのログでは 5 回とも `started → duplicate:ignored → duplicate:resent` の順で、正しく動いていた。
> 「重複を送ったとき実行中だったか」を retained の status（GetRetainedMessage）で判定していたが、#4 では送ってから 0.8 秒後に読んでも IDLE が返った。
> retained の読み取りが反映に遅れることがある、と考えている（推測。原因は調べていない）。判定を result の started_at〜finished_at に変えて測り直した。

## E2 重複指令（2026-11-08 22:21 JST）

- 手順: run_task を送る → 0.8 秒後（実行中）に同じ cmd_id を送る → 完了後にもう一度同じ cmd_id を送る
- 「実行中に送れたか」は、重複を送った時刻が 1 回目の result の started_at〜finished_at に入っているかで判定
- 合格: 実行中の重複は無視され（result は reason=ok の1件。busy にならない）、完了後の重複には前回とまったく同じ result が再送される（S3 のオブジェクトの LastModified だけが新しくなる）

| # | 実行中に重複を送れたか | 1回目の result | 再送された result | 判定 |
|---|---|---|---|---|
| 1 | はい | completed/ok | 同じ | OK |
| 2 | はい | completed/ok | 同じ | OK |
| 3 | はい | completed/ok | 同じ | OK |
| 4 | はい | completed/ok | 同じ | OK |
| 5 | はい | completed/ok | 同じ | OK |

**5/5 合格**

## M1 実機（2026-11-08 23:00 JST）

- 指示: `./ask.sh "黄色いブロックを片付けて"`（Lambda so101-judge、Strands 1.64.0、Bedrock `jp.anthropic.claude-haiku-4-5-20251001-v1:0`）
- エッジ: `edge_agent.py --transport mqtt --runner policy --run-s 20 --label`（SmolVLA、20 秒動かす）
- 「Lambda → エッジ」は Lambda の時計の issued_at とエッジの時計の received_at の差。エッジの時計は約 +30 ms ずれていた（NTP 未調整）ので参考値

| # | result | オペレーター判定 | 判断役の報告 | Lambda → エッジ | 実行時間 | 呼び出し全体 |
|---|---|---|---|---|---|---|
| 1 | completed/ok | fail | 失敗と判定されたと報告 | 148 ms | 39.9 s | 57.9 s |
| 2 | completed/ok | fail | 失敗と判定されたと報告 | 100 ms | 39.9 s | 51.8 s |
| 3 | completed/ok | success | 片付けた（オペレーターが成功と判定）と報告 | 48 ms | 39.7 s | 49.6 s |

**3/3 で、日本語の指示から実機の動作・結果の報告まで通った。掴めたのは 1/3。**

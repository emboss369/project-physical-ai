# CLAUDE.md — SO-101 × AWS「エッジとクラウドの連続性」

## 0. ゴール（これだけを目指す）

**5分の LT で、動くものと実測値を見せる。** 完成度より「見せられる結果」。

LT の筋: **「クラウドは何を決め、エッジは何を守るか」。** クラウドの判断役は許可リストの範囲でしか動かせず、安全制約はエッジ側にある。それを、動作と実測値で見せる。

| 区分 | 達成条件 |
|---|---|
| **M1（必須）** | 日本語の指示 → クラウドの判断役 → AWS IoT Core → エッジ → SO-101 が既存の SmolVLA ポリシーで1回動く → 判断役が結果を読んで報告する |
| **M2（必須）** | E1: クラウドからエッジへの指令の配送遅延を実測する（20回） |
| 加点 | E2: 同じ `cmd_id` を2回送っても1回しか動かない |

**フォールバック**: 判断役なし（手動の指示）まで届けば「疎通した」、判断役まで届けば「自然言語で動いた」。止まった地点と原因は、そのまま LT の内容にする。
**M1 が通った時点で、実行の様子を画面録画で残す**（ライブ実演が失敗したときの保険）。

## 1. 作業ルール

1. コマンド・環境変数・Terraform の属性・API の引数は、**公式ドキュメントで確認してから書く。** 確認できなければ「未確認」と書き、確認方法を添える。URL は実在を確認する。
2. 事実 / 推測を分ける。断定できないことは断定しない。
3. `terraform apply` / `destroy`、実機を動かす操作、課金が増える操作は、**実行前にユーザーの承認**を取る（plan を見せる）。
4. 段階（§7）ごとに、受け入れテストを通したら止まって報告する。先回りして次の段階を作らない。
5. 「【確認済】」は設計時に公式で確認した事実、「【要確認】」は作業時に必ず再確認する項目。

## 1.5 決定事項（2026-11-08）

- コードの置き場所: このリポジトリ内（`build-log/so101aws/`）。§4.9
- AWS CLI の認証: **IAM ユーザーのアクセスキー**（`aws configure`）。キーはユーザー自身のターミナルで設定し、チャットやリポジトリには貼らない。**作業の終わりに、そのアクセスキーを無効化する**（段階の最後に、無効化の手順をユーザーに案内する）
- Budgets: 月 20 USD
- ポリシー: SmolVLA（ACT ではない）。§4.4
- 判断役のモデル: **`jp.anthropic.claude-haiku-4-5-20251001-v1:0`**（東京・大阪だけで推論）。Haiku 5.5 はこのアカウントのクォータが 0 で使えなかった（Claude 5 系はすべて 0、4 系には上限あり）。上限が付いたら `infra/lambda.tf` の `model_id` を変えるだけで切り替わる。Anthropic の FTU フォームは提出済み、Haiku 4.5 / 5.5 の利用契約は `create-foundation-model-agreement` で結んだ

## 1.6 進み具合（2026-11-08 時点）

| 段階 | 状態 | 記録 |
|---|---|---|
| 0 準備 | 完了 | Build Log #022 節7 |
| 1 エッジ | 完了（停止時の挙動を実測） | 節8 |
| 2 IoT Core（**M2**） | 完了。E1 中央値 137.5 ms（同じ PC の往復）、E2 5/5 | 節9、`docs/lt-numbers.md` |
| 3 判断役（**M1**） | **完了。実機で 3/3 通った（掴めたのは 1/3）** | 節10、`docs/lt-numbers.md` |
| LT 準備 | 未着手 | — |

動かし方は Build Log #022 節10-5（エッジ：`edge_agent.py --transport mqtt --runner policy --run-s 20 --label`、指示：`scripts/ask.sh "黄色いブロックを片付けて"`）。

まだやっていないこと: エッジの NTP を近いサーバーへ切り替える（Lambda → エッジの一方向の遅延を正確に測るため。今は約 ±30 ms ずれる）。

## 2. スコープ外（やらない）

- 切断・再接続まわり（LWT、切断時の挙動、永続セッション、切断実験）
- クラッシュ復旧、outbox、再起動後の状態復元
- SageMaker 学習、Greengrass、Systems Manager、AgentCore、Isaac Sim / GR00T / AWS Physical AI Toolchain 本体
- LLM による関節角度・軌道の生成、音声入力、`ping` 指令
- 画像の S3 記録

## 3. 全体構成

```
[あなた] --日本語--> aws lambda invoke
                          │
              ┌───────────▼───────────┐
              │ Lambda: 判断役          │  Strands Agents + Bedrock(Claude)
              │  tools: get_status      │
              │         dispatch_task   │
              │         get_result      │
              │         (stop_robot)    │
              └───┬───────────────▲───┘
   publish(QoS1)  │               │ S3 読み取り
 so101/<thing>/cmd│        ┌──────┴──────┐
                  ▼        │ S3: results/ │
       ┌─────────────────┐ └──────▲──────┘
       │ AWS IoT Core     │────────┘ IoT ルール（result → S3）
       │ (MQTT5)          │
       └────────┬────────┘
   mTLS(証明書)  │  so101/<thing>/status (retained, 定期) / result
       ┌────────▼────────┐
       │ edge_agent.py    │  状態機械 / 重複排除 / TTL / 停止
       │ Runner → SmolVLA │
       └────────┬────────┘
                ▼
             SO-101
```

**設計原則**
- クラウドが送るのは**タスク名（許可リスト）だけ**。関節角度・軌道は送らない。
- **停止・安全はエッジが持つ。** クラウドの指令はエッジの安全制約を上書きできない。
- **ガードはプロンプトに頼らず、コードで強制する。**
- 実機なしで開発できるよう、エッジの Runner は差し替え可能（FakeRunner / PolicyRunner）。

## 4. 設計

### 4.1 命名

- リージョン: `ap-northeast-1`（東京）。Bedrock のモデル対応は §5。
- モノ名 = MQTT クライアント ID = `so101-edge-01`（【確認済】ポリシー変数 `${iot:Connection.Thing.ThingName}` を使うには、証明書をモノにアタッチし、非排他的関連付けではクライアント ID がモノ名と一致する必要がある）。
- 全リソースにタグ `project=physical-ai-so101`。
- 【確認済】同じクライアント ID で二重に接続すると、既存の接続が切れる（`Session taken over`）。エッジを二重に起動しない。

### 4.2 MQTT トピック（`<thing>` = モノ名）

| トピック | 方向 | QoS | retain | 用途 |
|---|---|---|---|---|
| `so101/<thing>/cmd` | クラウド → エッジ | 1 | なし | 指令（`run_task` / `stop`） |
| `so101/<thing>/status` | エッジ → クラウド | 1 | あり | 現在の状態（定期的に更新） |
| `so101/<thing>/result` | エッジ → クラウド | 1 | なし | 指令ごとの結果。IoT ルールで S3 へ |

- 【確認済】IoT Core は QoS 0/1 のみ。retained はトピックごとに1件で、ワイルドカード購読には届かない（`status` は完全一致で扱う）。
- QoS 1 は同じメッセージが重複して届きうる。だから重複排除（§4.4）が要る。

### 4.3 メッセージ仕様（JSON, `v:1`）

**cmd**
```json
{"v":1,"cmd_id":"<uuid4>","type":"run_task","task":"pick_yellow_block",
 "issued_at":"2026-11-08T07:30:00Z","ttl_s":60,"max_run_s":90}
```
- `type`: `run_task` | `stop`。
- `task` は許可リストのみ。**初期は `pick_yellow_block` のみ**。
- `max_run_s` は、エッジ側の定数上限（`EDGE_MAX_RUN_S`）を超えても、上限に切り詰める。

**result**
```json
{"v":1,"cmd_id":"<uuid4>","state":"completed|aborted|rejected",
 "reason":"ok|operator_stop|cloud_stop|timeout|duplicate|expired|busy|unknown_task|invalid|runner_error",
 "issued_at":"...","received_at":"...","started_at":"...","finished_at":"...",
 "operator_label":"success|fail|none"}
```
- `runner_error`（段階1で追加）: Runner が 0 以外の終了コードで終わった、または起動に失敗したとき `aborted/runner_error`。§4.4 の状態遷移表に該当する行がなかったため。`duplicate` は使わない（重複は前回の result の再送か無視で扱う）。
- 時刻は UTC・ミリ秒・末尾 Z（例 `2026-11-08T07:30:00.123Z`）。
- `issued_at`（Lambda 側）と `received_at`（エッジ側）の差で E1 を測る。**エッジ PC の時刻が同期されていること**（確認方法は公式で確認する）。
- **成否はエッジが自動判定しない**（ポリシーに成功信号がない）。`operator_label` は **M1 の実機実行のときだけ**、`--label` オプションで、実行後にオペレーターが y/n を入力する。

**status**
```json
{"v":1,"state":"IDLE|RUNNING|STOPPING","cmd_id":null,"ts":"..."}
```
- エッジは、接続時と、**10秒ごと**（仮置き）に、現在の state を retain 付きで publish する。
- **LWT は使わない**ので、エッジが止まっても retained の値は残る。**クラウドは `ts` が古い（30秒以上前、仮置き）status を「不明」として扱い、`dispatch_task` を拒否する。**

### 4.4 エッジエージェント（`edge/edge_agent.py`）

単一の Python プロセス。MQTT は AWS IoT Device SDK for Python v2 の MQTT5 クライアント（【確認済】`awsiot.mqtt5_client_builder.mtls_from_path` の引数: `endpoint`, `cert_filepath`, `pri_key_filepath`、任意で `client_id` など）。

**指令の処理順（上から評価し、最初に該当したもので終わる）**

1. スキーマ不正・`v` 不一致 → `rejected/invalid`
2. `cmd_id` が既知（実行中を含む）→ **再実行しない。** 完了済みなら前回の result を再送、実行中なら何もしない
3. `type: stop` → RUNNING なら停止して `aborted/cloud_stop`、IDLE なら無視
4. `now - issued_at > ttl_s` → `rejected/expired`
5. `task` が許可リストにない → `rejected/unknown_task`
6. state が RUNNING / STOPPING → `rejected/busy`
7. IDLE → 実行開始

**状態遷移**

| 現在 | イベント | 次 |
|---|---|---|
| IDLE | 指令が上の 7 に到達 | RUNNING |
| RUNNING | Runner が正常終了（終了コード 0、`max_run_s` 以内） | IDLE（`completed/ok`） |
| RUNNING | `max_run_s` 超過 | STOPPING → IDLE（`aborted/timeout`） |
| RUNNING | `stop` 指令・ローカル停止キー | STOPPING → IDLE（`aborted/cloud_stop` / `operator_stop`） |
| STOPPING | 停止完了 | IDLE |

**重複排除**: 直近 N 件（例 100）の `cmd_id` と結果を**メモリ上**に持つ。エッジを再起動すると忘れる（既知の制限）。TTL（60秒）が、再起動後の二重実行の窓を狭める。

**Runner（差し替え可能）**
- `FakeRunner`: 指定秒スリープして終了コード 0/非 0 を返す。IoT と判断役の開発・テストは**実機なしで**これで行う。
- `PolicyRunner`: 既存のポリシー実行（`lerobot-rollout`）を**サブプロセス**として起動する。実行コマンドは設定 `policy_run_cmd`。**ポリシーは SmolVLA に決定**（Build Log #022 節6-4。同じ 150 エピソードで ACT day3 / day1 より掴めた）。コマンドの土台は Build Log #022 節4-3（`--policy.path` はローカルのチェックポイント、`--rename_map` 必須、カメラは `/dev/v4l/by-id/` の固定パス、`--task` は学習データと同じ文）。`--duration` で有限時間にしたときの終わり方は段階 1 で確認する。
  - **新しいプロセスグループで起動**し、停止はグループ全体に送る。
  - **停止の手順**: SIGINT → 数秒待つ → SIGTERM → 数秒待つ → SIGKILL。待ち時間は実測で決める。
  - **`scripts/emergency_stop.sh`**: edge_agent と独立に、ポリシー実行のプロセスグループを強制終了する、ユーザー用のスクリプト。
  - **完了の定義**: 終了コード 0 で `completed/ok`。`max_run_s` 内に終わらなければ `aborted/timeout`。「`lerobot-rollout --duration=N` が自然に終わるのか、時間切れで止めるのか」は段階 1 で確認する（【要確認】）。
  - **排他**: 実行前に、同じシリアルポートやカメラを使う別の LeRobot プロセスがないことを確認する。
  - **初期姿勢・ブロックの位置は、オペレーターが毎回手で戻す。**
- **停止時の挙動（`stop_behavior`）は実測で確定**（Build Log #022 節8-5、2026-11-08）: `--duration` の時間切れでも SIGINT / SIGTERM でも、lerobot-rollout は**開始時の姿勢へ 3 秒で戻り、切断してトルクを切る（脱力する）**。終了コードは 0。SIGINT から終了まで 5.6 秒。起動から制御ループ開始まで約 15 秒。
  - **運用の前提: 開始時の姿勢は「脱力しても安全な休止の姿勢」にする。** 開始姿勢へ戻る途中で失敗すると（カメラの読み取り失敗など）、その場で脱力する（#022 節6-1 の ACT で `Could not return to initial position` が出た）。
  - PolicyRunner の停止: SIGINT → 10 秒 → SIGTERM → 10 秒 → SIGKILL（グループ全体）。SIGINT/SIGTERM は lerobot-rollout 本体にだけ送る（ログの tee を先に止めないため。tee 側も INT/TERM を無視）。
  - `max_run_s` は「動かす秒数（`--duration`）+ 起動 15 秒 + 後始末 6 秒 + 余裕」にする。
- **ローカル停止キー**: 標準入力は1つのスレッドが読み、`s` キーで停止する。`--label` を指定した実行では、実行後に y/n の入力へ切り替える。

### 4.5 クラウド: 判断役（`cloud/agent/`）

- **置き場は Lambda（推奨）。** Python 3.12。手元の PC で先に動かして試してもよい（その場合、エッジとの境界があいまいになる点を LT で補足する）。
- Strands Agents は、公式 Lambda レイヤー（【確認済】Python 3.10〜3.13、x86_64 / aarch64 対応。公式ドキュメントのデプロイ手順は CDK のみで、Terraform の記載はない）か自前の依存関係レイヤー。**Terraform からの公式レイヤーの参照方法は【要確認】。** 分からなければ自前レイヤー（Lambda のアーキテクチャに合う wheel を使う。ビルド方法は公式で確認）。
- 呼び出し: `aws lambda invoke`（公開 URL は作らない）。入力 `{"prompt":"黄色いブロックを片付けて"}`。クライアントの自動再試行で二重に呼ばれる可能性がある（【推測】CLI の再試行仕様は【要確認】）。二重に呼ばれても、エッジの `busy` 拒否と重複排除で、同時に2回は動かない。
- ツール（Strands の `@tool`）。**ガードは、ツールのコード側で強制し、プロンプトにも書く。**
  - `get_robot_status()`: `status` の retained メッセージを返す。【要確認】iot-data の retained 取得 API。【確認済】必要な IAM は `iot:GetRetainedMessage`（`status` トピック宛）。`ts` が古ければ「不明」と返す。
  - `dispatch_task(task)`: 許可リストを検査。**コード側で、直前の status が `IDLE` かつ `ts` が新しいことを確認し、そうでなければ拒否。1回の Lambda 呼び出しで2回目の呼び出しも拒否**（カウンタ）。通れば `cmd` に publish して `cmd_id` を返す。完了は待たない。
  - `get_result(cmd_id)`: S3 の `results/<thing>/<cmd_id>.json` を読む。まだ無ければ「未完了」と返す。**M1 の「結果が戻る」はこれで満たす。**
  - `stop_robot()`（任意）: `type: stop` を publish。
- システムプロンプトの方針: 許可リストにないタスクは断る／実行前に `get_robot_status` を呼ぶ／関節・座標・速度などの値は生成しない。
- モデル: Bedrock の Claude。【確認済】東京リージョンの Haiku 5.5 は**グローバルのクロスリージョン推論のみ**。Sonnet 5.5 の東京対応は【要確認】。`BedrockModel` には推論プロファイルの ID を明示して渡す。推論プロファイルを使うときの IAM（プロファイルと、その先の基盤モデルの両方への許可が要ると思われる）は公式で確認する。
- Lambda のタイムアウト: 初期値は60秒（仮置き。実測で決める）。

### 4.6 結果の記録

- IoT ルール: `so101/+/result` を S3 に保存（`results/<thing>/<cmd_id>.json`）。SQL でトピックの一部（モノ名）を取り出す関数と S3 アクションの属性は【要確認】。**ルール用の IAM ロールと `error_action`（失敗時の記録先）も定義する。**

### 4.7 IoT ポリシー（最小権限）

【確認済】リソース種別は `client` / `topic` / `topicfilter`。`Subscribe` は topicfilter、`Receive` は topic の両方が必要。ポリシー内のワイルドカードは `*` と `?` で、MQTT の `+` と `#` はリテラル扱い。

**エッジ用**
- `iot:Connect`: `client/${iot:Connection.Thing.ThingName}`、条件 `iot:Connection.Thing.IsAttached = true`
- `iot:Publish`: `topic/so101/${iot:Connection.Thing.ThingName}/status` と `.../result`
- **`iot:RetainPublish`**: `topic/so101/${iot:Connection.Thing.ThingName}/status`（【確認済】retained の publish に必要）
- `iot:Subscribe`: `topicfilter/so101/${iot:Connection.Thing.ThingName}/cmd`
- `iot:Receive`: `topic/so101/${iot:Connection.Thing.ThingName}/cmd`

**Lambda 用（IAM ロール）**: `iot:Publish` を `cmd` の1トピックだけ／`iot:GetRetainedMessage` を `status` の1トピックだけ／S3 の `results/` の読み取り／Bedrock の呼び出し／CloudWatch Logs。

### 4.8 Terraform

- ディレクトリ: `infra/`。分割: `versions.tf`（Terraform と AWS provider のバージョン固定）、`variables.tf`、`budgets.tf`、`iot.tf`、`s3.tf`、`lambda.tf`、`outputs.tf`。
- 使うリソース（【要確認】Registry の公式ドキュメントで引数・属性を確認する。Pulumi の AWS パッケージ一覧で Certificate / Policy / PolicyAttachment / Thing / ThingPrincipalAttachment / TopicRule の存在は確認済み）: `aws_iot_thing`、`aws_iot_certificate`、`aws_iot_policy`、`aws_iot_policy_attachment`、`aws_iot_thing_principal_attachment`、`aws_iot_topic_rule`、`aws_lambda_function`、`aws_s3_bucket`、`aws_budgets_budget`、IAM ロールとポリシー、IoT エンドポイントの data source（Data-ATS 形式を使う。種別の指定は【要確認】）。
- **HCL のエスケープ**: IoT ポリシー内の `${iot:...}` は、Terraform の補間と衝突するので **`$${iot:...}`** と書く。`terraform plan` の出力で、意図した文字列になっているかを確認する。
- **証明書と秘密鍵（先に決める）**: 秘密鍵が Terraform の state に入らないよう、**鍵と CSR をローカルで作り（`certs/`、Git 管理外）、CSR を `aws_iot_certificate` に渡す方式**を第一案にする。`csr` 引数の現行仕様は Registry で【要確認】。AWS が鍵を生成する方式は、state に秘密鍵が入る可能性が高いので使わない（【推測】）。
- **証明書をエッジに渡す手順**: `terraform output` で証明書 PEM を `certs/` に書き出す。秘密鍵は最初からローカルにある。Amazon Root CA は、公式ドキュメントの案内に従って取得する。
- state: ローカル state、`.gitignore` 済み。`terraform state show` で、秘密鍵が入っていないことを確認する。
- 変数: `region`、`thing_name`、`budget_usd`（**月 20 USD**。2026-11-08 決定）、`alert_email`。
- 変更の流れ: `fmt` → `validate` → `plan`（ユーザーに見せる）→ 承認 → `apply`。

### 4.9 リポジトリ構成

**別リポジトリにはせず、`project-physical-ai` の中の `build-log/so101aws/` に置く**（2026-11-08 決定）。

```
build-log/so101aws/
├── CLAUDE.md
├── .gitignore
├── infra/            # Terraform
├── edge/             # edge_agent.py, runner.py, protocol.py, config.example.yaml, tests/
├── cloud/agent/      # handler.py, tools.py, prompts.py, requirements.txt
├── scripts/          # send_cmd.py（手動で cmd を送る）、gen_csr.sh、emergency_stop.sh
├── docs/             # lt-numbers.md（実験の数字）
└── certs/            # Git 管理外
```

## 5. 確認状況

**【確認済】（設計時に公式で確認。一部はレビュー担当が確認）**
- IoT Core の MQTT: QoS 0/1、retained の仕様、クライアント ID の乗っ取り。
- IoT ポリシー: ARN 形式、`*`/`?` のみがワイルドカード、モノ名変数の条件、`iot:RetainPublish`、`iot:GetRetainedMessage`。
- IoT Device SDK for Python v2 の MQTT5 ビルダーの引数名。
- Strands の Lambda デプロイ: 公式レイヤー、Python 対応版、アーキテクチャ、公式例は CDK のみ。
- Bedrock の Haiku 5.5 は東京ではグローバルのクロスリージョン推論のみ。

**【段階0で確認済】（2026-11-08。出典は公式ドキュメント / provider ドキュメントのソース）**
- `aws_budgets_budget`: `budget_type`・`time_unit` が必須、`notification` に `subscriber_email_addresses`、`tags` 可。作成済み（月 20 USD、実績 80% / 予測 100%）。送り先は「Active (legacy)」で、確認メールは来なかった（以前からこのアカウントで使っていたアドレスのため）。確認状態は API では見えず、コンソールのみ
- `aws_iot_certificate`: `csr = file(...)`、`active`（必須）。`private_key` / `public_key` は「CSR も証明書も渡さないとき」だけ出力される → **CSR 方式なら秘密鍵は Terraform の state に入らない**（実際に `terraform state show` で確かめるのは段階2）。**証明書の方式は CSR 方式に決定**
- `data "aws_iot_endpoint"`: `endpoint_type = "iot:Data-ATS"` → `IDENTIFIER-ats.iot.REGION.amazonaws.com`
- `aws_iot_topic_rule`: `sql_version`（必須。例は `"2016-03-23"`）、`s3 { bucket_name, key, role_arn, canned_acl }`、`error_action` は同じアクションのブロックを持てる
- IoT SQL: `topic(n)` は1始まりで n 番目のセグメント（`so101/<thing>/result` なら `topic(2)` がモノ名）。S3 アクションの `key` は置換テンプレート可（`${topic(2)}`、ペイロードのフィールドも式として書ける。`cmd_id` を直接使う例は公式になし→段階2で実際に試す）
- boto3 `iot-data` `get_retained_message(topic=...)` → `topic` / `payload` / `qos` / `lastModifiedTime`（エポック ms）/ `userProperties`。呼び出しはメッセージング料金がかかりうる
- Amazon Root CA 1: `https://www.amazontrust.com/repository/AmazonRootCA1.pem`。公式は ATS エンドポイントと、サポートされる Root CA をすべて入れることを推奨（CA 3 もある）
- IoT Core の単価: 料金ページに東京の記載なし。例示（他リージョン）は接続 $0.08/100万分、メッセージ $1/100万件（5KB 単位）、ルール $0.15/100万。今回の量なら無視できる規模と見込む（推測）。東京の単価は additional-details ページか Pricing Calculator で【要確認】
- エッジ PC の時刻同期: `timedatectl` で `System clock synchronized: yes`。ただし NTP サーバーが `ntp.ubuntu.com`（往復 233 ms）で、オフセット -33 ms。**E1 の前に、近い NTP サーバーへ切り替えてオフセットを小さくする**（段階2。切り替え先と手順は公式で確認する）

**【段階2で確認済】（2026-11-08。実際に apply して確かめた。Build Log #022 節9）**
- IoT ルールの S3 キー `results/${topic(2)}/${cmd_id}.json` は、ペイロードの `cmd_id` で正しく展開された
- ポリシーの `$${iot:Connection.Thing.ThingName}` は plan で `${iot:Connection.Thing.ThingName}` になり、エッジは `client/so101-edge-01` で接続し、`cmd` を QoS 1 で購読できた。同じ証明書でもクライアント ID が違うと `NOT_AUTHORIZED`（135）で拒否された
- ルール用 IAM ロール: 信頼は `iot.amazonaws.com` ＋ `aws:SourceAccount` 条件、権限は `s3:PutObject`（`results/*`・`errors/*`）だけで動いた
- CSR 方式で、state に秘密鍵は入らない（`grep -c "PRIVATE KEY" terraform.tfstate` → 0）
- エッジを止めると retained の status は残り、30 秒を過ぎると `send_cmd.py send` が拒否する
- retained の status を `GetRetainedMessage` で読むと、更新から 0.8 秒たっても古い値が返ることがあった（5 回中 1 回）。**「今の状態」の判定に retained の読み取りを使うときは、反映の遅れを見込む**（段階3の `dispatch_task` のガード。原因は未調査）
- E1 は段階2では送信側（send_cmd.py）とエッジが同じ PC なので、時計のずれは入らないが、経路は PC → IoT Core → PC（一方向ではない）。Lambda からの一方向の測定は段階3で、NTP を近いサーバーに変えてから

**【要確認】（作業時に必ず確認）**
- Terraform での Strands レイヤーの扱い。（段階3）
- 使う Claude のモデル ID、Lambda に必要な IAM、Sonnet 5.5 の東京対応。（段階3）
- IoT Core の東京リージョン単価。
- AWS CLI の `lambda invoke` の再試行仕様。（段階3）
- 近い NTP サーバーへの切り替え手順。（段階2）

## 6. 実験（LT の数字を作る）

結果は `docs/lt-numbers.md` に表で残し、そのまま LT に使う。

| ID | 内容 | 試行数 | 合格の基準 | 実機 |
|---|---|---|---|---|
| **E1（M2）** | cmd の配送遅延 | 20 | `received_at - issued_at` の中央値と最大を出せる | 不要（FakeRunner） |
| E2（加点） | 同じ `cmd_id` を2回送る | 5 | 実行回数が毎回1回、2回目は result の再送 | 不要 |

- **E1 を測る前に、エッジ PC の Wi-Fi で IPv6 が無効のままか確認する**（`nmcli -g ipv6.method connection show AirPort` が `disabled`）。IPv6 が有効だと接続が詰まり、負荷時のレイテンシが 1.2 s まで伸びた（Build Log #022 節5-2）。測定条件として、Wi-Fi・2.4GHz・IPv4 であることも記録する。

合格の「基準値」（例: 遅延が何ms以下）は、測る前に決めない。測ってから、LT で何を言うかを決める。

## 7. 作業順と受け入れテスト

**段階 0: 準備**
- 受け入れ: Budgets のアラートが Terraform で作られ、テストメールが届く／証明書の方式（§4.8）を決めた／§5 の【要確認】のうち、段階 1〜2 に必要な項目を確認した。

**段階 1: エッジ（実機なしで先に）**
- 作る: `protocol.py`、`edge_agent.py`（FakeRunner）、単体テスト。
- 受け入れ: §4.4 の処理順と状態遷移の全パターンが単体テストで通る／重複排除が効く／ローカル停止キーが効く。
- その後（実機・ユーザー立ち会い）: `lerobot-rollout` の終了のしかたを特定し、`stop_behavior` を実測し、`emergency_stop.sh` が効くことを確認する。

**段階 2: IoT Core の疎通（M2）**
- 作る: `iot.tf`（モノ・ポリシー・証明書・ルール・S3）、`scripts/send_cmd.py`。
- 受け入れ: エッジが接続でき、`status` の retained がクラウドから読める／`send_cmd.py` の指令で FakeRunner が動き、`result` が S3 に入る／E1 の数字が取れる（E2 は時間があれば）。

**段階 3: 判断役（M1）**
- 作る: Lambda + Strands + ツール。
- 受け入れ（実機なし）: `{"prompt":"黄色いブロックを片付けて"}` で `dispatch_task` が1回呼ばれ、FakeRunner が動き、`get_result` で結果を報告する／「関節を30度回して」のような依頼は断られる／status が `RUNNING` または古いとき、コード側で `dispatch_task` が拒否される。
- 受け入れ（実機）: ユーザー立ち会いで、同じ指示で SO-101 が SmolVLA で1回動き、結果が報告される。**この様子を画面録画で残す。**

**LT 準備**: 数字を表にまとめ、5分の構成（問い／構成図／デモ／実測値／止まった点／次の一歩）に落とす。通しで時間を測る。

## 8. 実機の安全

- 実機を動かす前に、停止方法（電源、ローカル停止キー、`emergency_stop.sh`）をユーザーに伝え、周囲に人・物がないことを確認してもらう。
- 初回の実機実行は、ユーザーが電源に手の届く状態で、1回だけ。
- **edge_agent が固まっても腕が動き続けないよう、ポリシー実行のサブプロセス側にも実行時間の上限を効かせる**（方法は公式で確認）。
- 停止時のアームの挙動（§4.4）が分かるまで、クラウドからの `run_task` で実機を動かさない。脱力して落ちるなら、安全な姿勢で試し、アームを支える。
- `max_run_s` はエッジ側の定数上限を超えられない。

## 9. 参考（調査済み。判断の根拠）

- AWS ジャパンの FANUC デモ（Physical AI デモの裏側 Part 2）: 判断はクラウド、動作と安全制約はエッジ。MQTT5、証明書認証、重複指令の対策。
- AWS builders.flash（toio）: IoT Core → Lambda 上の Strands → Bedrock の流れ。
- Dum-E（`github.com/aaronsu11/Dum-E`）: SO-101 + GR00T + MCP の実装。README に AWS サービス名なし。参考のみ。
- AWS Physical AI Toolchain: UR3 専用設定・エッジ未実装のため、今回は扱わない。
- 設計レビューの記録: `research_notes/claude_md_review.md`（切断系を含む旧版へのレビュー。切断を外した現行版では、切断に関する指摘は対象外）。

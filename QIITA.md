# QIITA.md — Qiita投稿手順

Qiita API v2（`https://qiita.com/api/v2/items`）を使った投稿の手順。CONVENTIONS.mdの展開ルール（動画→記事→X→LinkedIn）における「記事」はQiitaを指す。

---

## 前提：トークンの扱い

- Qiitaの個人用アクセストークンは https://qiita.com/settings/tokens/new で発行する（scope: `read_qiita`, `write_qiita`）
- **トークンはユーザー自身のターミナルで環境変数にセットし、Claude Codeとのチャットやリポジトリには絶対に貼らない**
  ```bash
  export QIITA_WRITE_TOKEN=<発行したトークン>
  ```
- 投稿の実行（トークンを使うcurlコマンド）は、Hugging Faceの書き込みトークン運用（Build Log #005）と同様、ユーザー自身のターミナルで行う

## 手順

### 1. 認証確認（読み取り専用、何も公開されない）

```bash
curl -s -H "Authorization: Bearer $QIITA_WRITE_TOKEN" https://qiita.com/api/v2/authenticated_user
```

自分のユーザー情報が返ってくれば認証OK。

### 2. 既存記事のタグ慣習を確認（任意）

```bash
curl -s "https://qiita.com/api/v2/users/emboss369/items" | python3 -c "
import json,sys
items = json.load(sys.stdin)
for it in items:
    print(it['title'], [t['name'] for t in it['tags']])
"
```

### 3. 投稿用JSONペイロードを作成

下書きMarkdownファイルから`jq`で安全に埋め込む（手打ちでエスケープしない）。

```bash
jq -n \
  --rawfile body draft.md \
  --arg title "記事タイトル" \
  '{title: $title, body: $body, tags: [{name:"タグ1"},{name:"タグ2"}], private: false, tweet: false}' \
  > qiita-payload.json
```

- `private: false`：個人アカウント（Qiita:Teamではない）では、限定共有をAPI経由で新規作成できるか未確認。**実行すると即時公開される前提で進める**
- `tweet: false`：Qiita側のX自動連携はオフにする。CONVENTIONS.mdの「動画→記事→X」という展開順・タイミングをこちらでコントロールするため

### 4. 実行前に必ず内容を確認する

タイトル・タグ・本文を人間の目で最終確認してから次に進む。**この投稿操作は即時公開であり取り消しにくいため、確認なしに実行しない。**

### 5. 投稿（ユーザー自身のターミナルで実行）

```bash
curl -s -X POST \
  -H "Authorization: Bearer $QIITA_WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  -d @qiita-payload.json \
  https://qiita.com/api/v2/items
```

### 6. レスポンスの確認

返ってきたJSONの`"url"`が公開された記事のURL。`"private"`が`false`になっていることも確認する。

## タグの慣習

既存記事（Kotlin/Android系、smartphone-zine.com由来）とは別ジャンルのため、Physical AI関連は新規に以下のようなタグを使う。

`ロボット` / `LeRobot` / `機械学習` / `so101` / `PhysicalAI`

## YouTube動画の埋め込み

`@[youtube](VIDEO_ID)`のような専用記法は**存在しない**（一度これで投稿し、埋め込まれず壊れたリンクになった実例あり）。Qiita公式の埋め込み方法は、iframeタグをそのまま本文（Markdown）に書く方式。

```html
<iframe width="560" height="315" src="https://www.youtube.com/embed/VIDEO_ID" title="YouTube video player" style="border:0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-origin" loading="lazy" allowfullscreen></iframe>
```

`VIDEO_ID`は`https://youtu.be/VIDEO_ID`または`https://www.youtube.com/watch?v=VIDEO_ID`のIDの部分。

## 投稿済み記事の更新（PATCH）

埋め込みミスなど、公開後に本文を修正したい場合はPATCHで更新できる（`item_id`は記事URLの末尾）。

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer $QIITA_WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  -d @qiita-payload.json \
  https://qiita.com/api/v2/items/<item_id>
```

POSTと同じくペイロード（`title`/`body`/`tags`）が必要。実行前の内容確認ルールも同様に適用する。

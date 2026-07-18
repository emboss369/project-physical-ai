# Project Physical AI

> Learning Physical AI in public — SO-101, LeRobot, and Claude Code.
> Every step, including the failures. North Star: fold a T-shirt.

SO-101 ロボットアームと LeRobot、Claude Code を使って、Physical AI をハンズオンで学ぶ**公開研究所（Open Lab）**です。

企業の研究所は、成果が出るまで情報を出しません。ここは逆です。学んだことも、試行錯誤も、AIとの対話も、動かないロボットも、全部出します。

---

## 憲法

> **完成を目指すのではなく、公開しながら学ぶ。昨日の自分より一歩進めば成功とする。**

すべての判断はここに戻ります。

---

## North Star — Road to Folding a T-shirt

最終目標は **SO-101 でTシャツをたたむ** こと。

Tシャツ折り畳みは柔軟物（deformable object）操作という、ロボティクスの有名な難関ベンチマークです。画像認識、模倣学習、VLA、ロボット制御——Physical AI の技術要素がほぼ全部詰まっています。

**現時点で、これは物理的に不可能です。** 柔軟物操作にはバイマニュアル（両腕）が実質必須で、SO-101 はまだ1台しかありません。2台目の導入はロードマップ上の重要マイルストーンであり、それ自体が記録の対象です。

最後にたためても、たためなくても、そこに至る過程が成果です。

---

## ミッション

> 日本語で Physical AI を学ぶ人が、最初にたどり着く情報源になる。

有名になることではありません。同じ挑戦を始める人にとって、価値ある記録を残すことです。

---

## フェーズ

| | 内容 |
|---|---|
| **Phase 1**（現在） | Learning in Public — SO-101 / LeRobot / Claude Code を学びながら発信を習慣化 |
| **Phase 2** | 開発ログのシリーズ化 — カメラ認識 → 物体把持 → 模倣学習 → 柔軟物 |
| **Phase 3** | 体系化 — 蓄積した記録を講座・書籍に再編 |

---

## 構成

```
.
├── README.md
├── CONVENTIONS.md      命名規則
└── build-log/          日次記録
    └── build-log-001.md
```

**Build Log** が本体です。毎日、数行でも積みます。100日後には素材になっています。

命名規則は [CONVENTIONS.md](./CONVENTIONS.md) を参照。

---

## 発信チャンネル

| シリーズ | 媒体 | 中身 |
|---|---|---|
| Build Log | GitHub（ここ） | 日次記録 |
| Road to Folding a T-shirt | YouTube | 本編 |
| Failure Log | YouTube | 失敗だけで終わった回 |
| Physical AI 研究ノート | YouTube | 気づき・勉強会・論文 |

---

## 発信品質のルール

Physical AI 業界の動向に触れるとき、以下を守ります。

- **事実・予測・ビジョン言明を峻別する。** 企業の量産「計画」は実績ではない
- **数値には出典・通貨・期間・対象範囲を添える**
- **相関と因果を混同しない**
- **断定できないことは断定しない**

この誠実さ自体が、この記録の価値だと考えています。

---

## 現在地

Phase 1。SO-101、まだ動いていません。

[Build Log #001](./build-log/build-log-001.md) から始まっています。
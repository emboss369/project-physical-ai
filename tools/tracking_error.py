#!/usr/bin/env python3
"""action(リーダー指令) と observation.state(フォロワー実測) の追従誤差を
エピソード区間ごとに比較する。

目的: Day3(遠い位置)で「指令はしたが到達していない」記録になっていないかを検証。
      追従誤差が Day1/Day2 と同水準なら物理的到達は問題なし -> 原因はデータ量/多様性。
      Day3 だけ誤差が大きいなら、アームが届いていない -> データを足しても直らない。
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1])
GROUPS = {"Day1 (ep 0-49)": (0, 49), "Day2 (ep 50-99)": (50, 99), "Day3 (ep 100-149)": (100, 149)}

info = json.loads((ROOT / "meta" / "info.json").read_text())
JOINTS = info["features"]["action"]["names"]

df = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "data").rglob("*.parquet"))])
df = df.sort_values(["episode_index", "frame_index"]).reset_index(drop=True)

act = np.stack(df["action"].to_numpy()).astype(np.float64)
sta = np.stack(df["observation.state"].to_numpy()).astype(np.float64)
ep = df["episode_index"].to_numpy()
err = np.abs(act - sta)

print(f"\n{'=' * 78}\n追従誤差 |action - state|  （単位: 正規化前の関節値）\n{'=' * 78}")
hdr = f"{'関節':<18}" + "".join(f"{g:>20}" for g in GROUPS)
print(hdr)
print("-" * len(hdr))
for j, name in enumerate(JOINTS):
    cells = ""
    for lo, hi in GROUPS.values():
        m = (ep >= lo) & (ep <= hi)
        cells += f"{err[m, j].mean():>10.3f}{np.percentile(err[m, j], 95):>10.3f}"
    print(f"{name:<18}{cells}")
print(f"{'（左=平均 / 右=95%点）':<18}")

print(f"\n{'=' * 78}\n各関節の指令レンジ（Day3 が本当に新しい領域を含むかの確認）\n{'=' * 78}")
print(hdr)
print("-" * len(hdr))
for j, name in enumerate(JOINTS):
    cells = ""
    for lo, hi in GROUPS.values():
        m = (ep >= lo) & (ep <= hi)
        cells += f"{act[m, j].min():>10.1f}{act[m, j].max():>10.1f}"
    print(f"{name:<18}{cells}")
print(f"{'（左=min / 右=max）':<18}")

print(f"\n{'=' * 78}\n各エピソードの「最大到達」時点での追従誤差（伸ばしきった瞬間）\n{'=' * 78}")
# shoulder_lift + elbow_flex が最も伸びた（=前方リーチ最大）フレームでの誤差
li, ei = JOINTS.index("shoulder_lift.pos"), JOINTS.index("elbow_flex.pos")
reach = -(act[:, li] + act[:, ei])  # 値が小さいほど伸びている想定。符号は下で両方見る
for label, r in (("reach = -(lift+elbow)", reach), ("reach = +(lift+elbow)", -reach)):
    print(f"\n[{label}]")
    print(f"{'区間':<20}{'最大リーチ時の誤差(平均)':>26}{'該当エピソード数':>18}")
    for g, (lo, hi) in GROUPS.items():
        vals = []
        for e in range(lo, hi + 1):
            m = ep == e
            if not m.any():
                continue
            k = np.argmax(r[m])
            vals.append(np.linalg.norm(err[m][k]))
        print(f"{g:<20}{np.mean(vals):>26.3f}{len(vals):>18}")

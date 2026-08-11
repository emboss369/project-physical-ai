#!/usr/bin/env python3
"""把持時の関節姿勢のばらつき＝「対象物の配置範囲」を推定し、データ密度を比較する。

仮説: 学習の成否はエピソード数ではなく「配置範囲あたりの密度」で決まる。
      同じ150エピソードでも、2cm四方に置いた場合と20cm四方にばらまいた場合では
      1配置あたりのサンプル数が桁違いになる。

把持の瞬間 = gripper.pos が最も急激に閉じたフレーム。
そのフレームの (shoulder_pan, shoulder_lift, elbow_flex) を対象物の位置の代理指標とする。

使い方:
  python3 grasp_spread.py <dataset_root>[:<ep_lo>-<ep_hi>[:ラベル]] ...
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROXY = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos"]


def grasp_poses(root: Path, lo=None, hi=None):
    info = json.loads((root / "meta" / "info.json").read_text())
    J = info["features"]["action"]["names"]
    gi = J.index("gripper.pos")
    idx = [J.index(n) for n in PROXY]

    df = pd.concat([pd.read_parquet(f) for f in sorted((root / "data").rglob("*.parquet"))])
    df = df.sort_values(["episode_index", "frame_index"])
    act = np.stack(df["action"].to_numpy()).astype(float)
    ep = df["episode_index"].to_numpy()

    poses = []
    for e in sorted(set(ep)):
        if lo is not None and not (lo <= e <= hi):
            continue
        a = act[ep == e]
        if len(a) < 5:
            continue
        # gripper が最も急に閉じた（値が減った）フレーム = 把持の瞬間
        k = int(np.argmin(np.diff(a[:, gi]))) + 1
        poses.append(a[k, idx])
    return np.array(poses)


def report(label, P):
    if len(P) == 0:
        print(f"{label}: データなし")
        return
    span = np.percentile(P, 95, axis=0) - np.percentile(P, 5, axis=0)
    # 主要2軸（左右=pan / 前後=lift）で張られる矩形を「配置範囲」の代理とする
    area = span[0] * span[1]
    print(f"\n[{label}]  エピソード数 = {len(P)}")
    print(f"  {'関節':<20}{'平均':>10}{'標準偏差':>10}{'5%点':>10}{'95%点':>10}{'幅(90%)':>10}")
    for j, n in enumerate(PROXY):
        print(
            f"  {n:<20}{P[:, j].mean():>10.1f}{P[:, j].std():>10.2f}"
            f"{np.percentile(P[:, j], 5):>10.1f}{np.percentile(P[:, j], 95):>10.1f}{span[j]:>10.1f}"
        )
    print(f"  配置範囲の代理面積 (pan幅 × lift幅) = {area:>10.1f}")
    print(f"  ★密度 = エピソード数 / 面積        = {len(P) / area:>10.4f} ep/unit²")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for spec in sys.argv[1:]:
        parts = spec.split(":")
        root = Path(parts[0])
        lo = hi = None
        label = parts[2] if len(parts) > 2 else root.name
        if len(parts) > 1 and parts[1]:
            lo, hi = (int(x) for x in parts[1].split("-"))
        report(label, grasp_poses(root, lo, hi))

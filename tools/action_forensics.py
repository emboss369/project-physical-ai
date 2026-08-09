#!/usr/bin/env python3
"""LeRobotDataset の action 系列を解析し、収集時のループ低下の痕跡を探す。

仮説:
  A1 収集ループが遅く値が保持された -> 同一 action の連が長くなる（階段状）
  A2 時間圧縮（実時間より速く記録）  -> 連は出ないが |Δaction| の分散が大きい

使い方:
  python3 action_forensics.py <dataset_root> [<dataset_root> ...]
  python3 action_forensics.py --repo-id emboss369/xxx   # Hub から取得
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def load_dataset(root: Path):
    info = json.loads((root / "meta" / "info.json").read_text())
    files = sorted((root / "data").rglob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet under {root}/data")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values(["episode_index", "frame_index"]).reset_index(drop=True)
    return info, df


def per_episode_actions(df):
    """エピソードごとに (T, D) の action 配列を返す。差分をエピソード境界で切る。"""
    for ep, g in df.groupby("episode_index", sort=True):
        yield int(ep), np.stack(g["action"].to_numpy()).astype(np.float64)


def run_lengths(a: np.ndarray) -> np.ndarray:
    """全次元が直前フレームと完全一致するフレームの連の長さ。"""
    same = np.all(np.diff(a, axis=0) == 0.0, axis=1)  # 長さ T-1
    lengths, cur = [], 1
    for s in same:
        if s:
            cur += 1
        else:
            lengths.append(cur)
            cur = 1
    lengths.append(cur)
    return np.array(lengths)


def highfreq_ratio(a: np.ndarray, fps: float, cutoff: float = 4.0) -> float:
    """各関節のパワースペクトルのうち cutoff Hz 以上が占める割合（平均）。"""
    a = a - a.mean(axis=0, keepdims=True)
    if len(a) < 8:
        return np.nan
    spec = np.abs(np.fft.rfft(a, axis=0)) ** 2
    freq = np.fft.rfftfreq(len(a), d=1.0 / fps)
    total = spec[1:].sum(axis=0)
    high = spec[1:][freq[1:] >= cutoff].sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return float(np.nanmean(np.where(total > 0, high / total, np.nan)))


def analyze(root: Path):
    info, df = load_dataset(root)
    fps = float(info["fps"])

    # --- timestamp が合成値か実測値か ---
    ts_dev = []
    for _, g in df.groupby("episode_index", sort=True):
        t = g["timestamp"].to_numpy(dtype=np.float64)
        t = t - t[0]
        ts_dev.append(np.abs(t - np.arange(len(t)) / fps).max())
    ts_dev_max = float(np.max(ts_dev))

    ep_lens, all_runs, all_steps, all_jerks, hf = [], [], [], [], []
    for _, a in per_episode_actions(df):
        ep_lens.append(len(a))
        all_runs.append(run_lengths(a))
        d = np.linalg.norm(np.diff(a, axis=0), axis=1)
        all_steps.append(d)
        if len(a) >= 3:
            all_jerks.append(np.linalg.norm(np.diff(a, n=2, axis=0), axis=1))
        hf.append(highfreq_ratio(a, fps))

    runs = np.concatenate(all_runs)
    steps = np.concatenate(all_steps)
    jerks = np.concatenate(all_jerks)
    ep_lens = np.array(ep_lens)

    # 「保持されたフレーム」= 直前と完全一致した割合
    held_frac = float((runs[runs > 1] - 1).sum() / runs.sum())

    return {
        "name": root.name,
        "fps": fps,
        "episodes": int(info["total_episodes"]),
        "frames": int(info["total_frames"]),
        "ts_dev_max_s": ts_dev_max,
        "ep_len_mean": float(ep_lens.mean()),
        "ep_len_p05": float(np.percentile(ep_lens, 5)),
        "ep_len_p95": float(np.percentile(ep_lens, 95)),
        "ep_sec_mean": float(ep_lens.mean() / fps),
        "held_frac": held_frac,
        "run_max": int(runs.max()),
        "run_p99": float(np.percentile(runs, 99)),
        "run_ge3_frac": float((runs >= 3).sum() / len(runs)),
        "dstep_mean": float(steps.mean()),
        "dstep_p50": float(np.percentile(steps, 50)),
        "dstep_p99": float(np.percentile(steps, 99)),
        "dstep_cv": float(steps.std() / steps.mean()) if steps.mean() else np.nan,
        "jerk_rms": float(np.sqrt((jerks**2).mean())),
        "jerk_over_step": float(np.sqrt((jerks**2).mean()) / steps.mean())
        if steps.mean()
        else np.nan,
        "hf_ratio_4hz": float(np.nanmean(hf)),
    }


ROWS = [
    ("episodes", "エピソード数", "{:.0f}"),
    ("frames", "総フレーム数", "{:.0f}"),
    ("fps", "公称fps", "{:.0f}"),
    ("ts_dev_max_s", "timestamp と frame/fps の最大乖離[s]", "{:.6f}"),
    ("ep_len_mean", "エピソード長 平均[frames]", "{:.1f}"),
    ("ep_sec_mean", "エピソード長 平均[s] (公称fps換算)", "{:.2f}"),
    ("held_frac", "★直前と完全一致したフレーム比率", "{:.4f}"),
    ("run_ge3_frac", "★連長3以上の割合", "{:.4f}"),
    ("run_max", "最大連長", "{:.0f}"),
    ("dstep_mean", "|Δaction| 平均", "{:.4f}"),
    ("dstep_p50", "|Δaction| 中央値", "{:.4f}"),
    ("dstep_p99", "|Δaction| 99%点", "{:.4f}"),
    ("dstep_cv", "★|Δaction| 変動係数 (std/mean)", "{:.3f}"),
    ("jerk_rms", "jerk RMS (2階差分)", "{:.4f}"),
    ("jerk_over_step", "★jerk / |Δaction|平均", "{:.3f}"),
    ("hf_ratio_4hz", "4Hz以上のパワー比", "{:.4f}"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="*", type=Path)
    ap.add_argument("--repo-id", action="append", default=[])
    args = ap.parse_args()

    roots = list(args.roots)
    for repo_id in args.repo_id:
        from huggingface_hub import snapshot_download

        roots.append(
            Path(
                snapshot_download(
                    repo_id=repo_id,
                    repo_type="dataset",
                    allow_patterns=["meta/*", "meta/**/*", "data/**/*.parquet"],
                )
            )
        )

    if not roots:
        ap.error("dataset root か --repo-id を1つ以上指定してください")

    results = []
    for root in roots:
        print(f"[load] {root}", file=sys.stderr)
        results.append(analyze(root))

    w = max(38, *(len(r["name"]) for r in results))
    print(f"\n{'指標':<40}" + "".join(f"{r['name']:>{w}}" for r in results))
    print("-" * (40 + w * len(results)))
    for key, label, fmt in ROWS:
        cells = "".join(f"{fmt.format(r[key]):>{w}}" for r in results)
        print(f"{label:<40}{cells}")


if __name__ == "__main__":
    main()

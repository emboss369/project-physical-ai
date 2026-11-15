#!/usr/bin/env python3
"""OBS 録画から佐倉みどりの発話区間を切り出す。

録画（MKV マルチトラック）の佐倉みどり専用トラックで無音検出し、
発話区間ごとの wav と区間表 segments.csv を書き出す。
wav は InfiniteTalk に渡すリップシンク用の音声になる。

    python segment.py recording.mkv out/ --track 1

--track は 0 始まりの音声トラック番号（OBS のトラック2 なら 1）。
"""
import argparse
import csv
import re
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def detect_silences(path: Path, track: int, noise: str, min_silence: float):
    """silencedetect の結果を (開始, 終了) の無音区間リストで返す。"""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-map", f"0:a:{track}",
         "-af", f"silencedetect=noise={noise}:d={min_silence}",
         "-f", "null", "-"],
        check=True, capture_output=True, text=True)
    silences, start = [], None
    for line in proc.stderr.splitlines():
        if m := re.search(r"silence_start: (-?[\d.]+)", line):
            start = max(0.0, float(m.group(1)))
        elif (m := re.search(r"silence_end: ([\d.]+)", line)) and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    return silences, start  # start が残っていれば末尾まで無音


def speech_ranges(silences, trailing_start, duration):
    """無音区間の補集合＝発話区間。"""
    ranges, cursor = [], 0.0
    for s, e in silences:
        if s > cursor:
            ranges.append([cursor, s])
        cursor = e
    end = trailing_start if trailing_start is not None else duration
    if end > cursor:
        ranges.append([cursor, end])
    return ranges


def merge_close(ranges, gap):
    """Open-LLM-VTuber は1文ずつ再生するので、文間の短い無音はつなげて1区間にする。"""
    merged = []
    for r in ranges:
        if merged and r[0] - merged[-1][1] < gap:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    return merged


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("recording", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--track", type=int, default=1, help="佐倉みどりの音声トラック（0 始まり）")
    p.add_argument("--noise", default="-45dB", help="これより小さい音を無音とみなす")
    p.add_argument("--min-silence", type=float, default=0.3, help="無音と判定する最短秒数")
    p.add_argument("--merge-gap", type=float, default=1.0, help="これより短い隙間は同じ発話にまとめる")
    p.add_argument("--pad", type=float, default=0.2, help="区間の前後に足す余白（秒）")
    p.add_argument("--min-len", type=float, default=0.3, help="これより短い区間はノイズとして捨てる")
    args = p.parse_args()

    duration = probe_duration(args.recording)
    silences, trailing = detect_silences(args.recording, args.track, args.noise, args.min_silence)
    ranges = merge_close(speech_ranges(silences, trailing, duration), args.merge_gap)
    ranges = [r for r in ranges if r[1] - r[0] >= args.min_len]

    # 余白を足す。隣の区間と重なる場合は中間で切る
    padded = []
    for i, (s, e) in enumerate(ranges):
        s = max(0.0, s - args.pad)
        e = min(duration, e + args.pad)
        if padded and s < padded[-1][1]:
            mid = (s + padded[-1][1]) / 2
            padded[-1][1] = mid
            s = mid
        padded.append([s, e])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (s, e) in enumerate(padded, 1):
        name = f"seg_{i:03d}"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{s:.3f}", "-to", f"{e:.3f}", "-i", str(args.recording),
             "-map", f"0:a:{args.track}", "-ac", "1", "-ar", "16000",
             str(args.out_dir / f"{name}.wav")],
            check=True)
        rows.append({"name": name, "start": f"{s:.3f}", "end": f"{e:.3f}",
                     "duration": f"{e - s:.3f}"})

    with open(args.out_dir / "segments.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "start", "end", "duration"])
        w.writeheader()
        w.writerows(rows)
    # 結合時に全体の長さが要るので残しておく
    (args.out_dir / "recording_duration.txt").write_text(f"{duration:.3f}\n")

    total = sum(e - s for s, e in padded)
    print(f"{len(rows)} 区間 / 発話合計 {total:.1f} 秒 / 録画 {duration:.1f} 秒 → {args.out_dir}")


if __name__ == "__main__":
    main()

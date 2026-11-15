#!/usr/bin/env python3
"""リップシンク動画を、録画と同じ長さの1本の動画に並べる。

segment.py が書き出した segments.csv の時刻どおりに seg_NNN.mp4 を配置し、
隙間はブルーバックで埋める。Camtasia では録画と並べて 0:00 に置き、
ブルーバックをキーイングで抜く。

    python segment.py recording.mkv work/ --track 1
    （work/seg_NNN.wav から InfiniteTalk で work/seg_NNN.mp4 を作る）
    python compose.py work/ midori_full.mp4 --recording recording.mkv --track 1

seg_NNN.mp4 が無い区間はブルーバックのまま警告だけ出すので、途中まででも結合できる。
"""
import argparse
import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

# 中間ファイルはすべてこの設定で揃え、最後に無劣化で連結する
ENCODE = ["-c:v", "libx264", "-preset", "medium", "-crf", "16",
          "-pix_fmt", "yuv420p", "-an", "-f", "mpegts"]


def run(cmd):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *cmd], check=True)


def blue_clip(path: Path, frames: int, args):
    run(["-f", "lavfi", "-i", f"color=c={args.bg}:s={args.width}x{args.height}:r={args.fps}",
         "-frames:v", str(frames), *ENCODE, str(path)])


def speech_clip(path: Path, src: Path, frames: int, args):
    """リップシンク動画を区間の長さ（frames）ちょうどに揃え、ブルーバックからフェードさせる。"""
    fade = min(args.fade, frames / args.fps / 2)
    out_start = frames / args.fps - fade
    vf = ",".join([
        f"fps={args.fps}",
        f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease",
        f"pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2:color={args.bg}",
        "setsar=1",
        # 短ければ最後のフレームで延ばし、長ければ切る
        f"tpad=stop_mode=clone:stop={frames}",
        f"trim=end_frame={frames}",
        f"fade=t=in:st=0:d={fade:.3f}:color={args.bg}",
        f"fade=t=out:st={out_start:.3f}:d={fade:.3f}:color={args.bg}",
    ])
    run(["-i", str(src), "-vf", vf, *ENCODE, str(path)])
    return probe_seconds(src)


def probe_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work_dir", type=Path, help="segments.csv と seg_NNN.mp4 のあるフォルダ")
    p.add_argument("output", type=Path)
    p.add_argument("--fps", type=int, default=25, help="InfiniteTalk の出力は 25fps")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--bg", default="0x0000FF", help="ブルーバックの色（リップシンク元画像の背景色に合わせる）")
    p.add_argument("--fade", type=float, default=0.3, help="フェードイン・アウトの秒数（0 で無効）")
    p.add_argument("--recording", type=Path, help="指定すると佐倉みどりの音声を同期確認用に入れる")
    p.add_argument("--track", type=int, default=1, help="--recording の佐倉みどり音声トラック（0 始まり）")
    args = p.parse_args()

    with open(args.work_dir / "segments.csv") as f:
        segments = list(csv.DictReader(f))
    total = float((args.work_dir / "recording_duration.txt").read_text())
    total_frames = round(total * args.fps)

    tmp = Path(tempfile.mkdtemp(prefix="midori_compose_"))
    parts, cursor, missing = [], 0, []
    try:
        for seg in segments:
            # 時刻はフレーム番号に丸めてから引き算する。区間ごとに秒で丸めると30分で誤差が積もる
            start = round(float(seg["start"]) * args.fps)
            end = round(float(seg["end"]) * args.fps)
            if start > cursor:
                gap = tmp / f"{len(parts):04d}.ts"
                blue_clip(gap, start - cursor, args)
                parts.append(gap)
            part = tmp / f"{len(parts):04d}.ts"
            src = args.work_dir / f"{seg['name']}.mp4"
            if src.exists():
                src_sec = speech_clip(part, src, end - start, args)
                diff = src_sec - (end - start) / args.fps
                if abs(diff) > 0.5:
                    print(f"⚠ {seg['name']}: 動画と区間の長さが {diff:+.2f} 秒ずれている（切り詰め/延長した）")
            else:
                blue_clip(part, end - start, args)
                missing.append(seg["name"])
            parts.append(part)
            cursor = end
            print(f"  {seg['name']}  {seg['start']}–{seg['end']} 秒", flush=True)
        if total_frames > cursor:
            tail = tmp / f"{len(parts):04d}.ts"
            blue_clip(tail, total_frames - cursor, args)
            parts.append(tail)

        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{x}'\n" for x in parts))
        cmd = ["-f", "concat", "-safe", "0", "-i", str(listing)]
        if args.recording:
            cmd += ["-i", str(args.recording), "-map", "0:v", "-map", f"1:a:{args.track}",
                    "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", str(args.output)]
        run(cmd)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if missing:
        print(f"⚠ 動画が無くブルーバックのままの区間: {', '.join(missing)}")
    print(f"→ {args.output}（{probe_seconds(args.output):.2f} 秒 / 録画 {total:.2f} 秒）")


if __name__ == "__main__":
    main()

"""Build the story-first 90-120 second competition video from live evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
import imageio_ffmpeg

from build_demo_video_v2 import (
    HEIGHT,
    INK,
    MINT,
    MUTED,
    PAPER,
    WIDTH,
    architecture_slide,
    end_slide,
    font,
    grid,
    heading,
    metrics_slide,
    run,
    scale_slide,
    screenshot_slide,
    wav_duration,
)


def story_slide(path: Path, source: Path) -> None:
    screenshot_slide(path, source, "LIVE CHECKOUT INCIDENT", "Store. Reject. Retrieve. Act once.")


def pressure_slide(path: Path, pressure: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "REAL CONCURRENT-AGENT PRESSURE", "Correct at fifty agents-and honest about the queue.")
    levels = pressure["levels"]
    for index, level in enumerate(levels):
        x = 56 + index * 390
        draw.rounded_rectangle((x, 202, x + 350, 456), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 22, 226), f"{level['concurrent_agents']} AGENTS", fill=MUTED, font=font("arialbd.ttf", 16))
        draw.text((x + 22, 274), f"{level['throughput_ops_per_second']:.1f}/s", fill="#078454", font=font("georgia.ttf", 43))
        draw.text((x + 22, 338), f"p95  {level['latency_ms']['p95']:.1f} ms", fill=INK, font=font("arial.ttf", 19))
        draw.text((x + 22, 376), "0 leaked rows  ·  1 owner", fill=INK, font=font("arialbd.ttf", 17))
        draw.text((x + 22, 414), f"{level['operations']} operations", fill=MUTED, font=font("arial.ttf", 16))
    recovery = pressure["recoveries"][-1]["time_to_first_success_ms"]
    draw.rectangle((56, 506, 1224, 632), fill=INK)
    draw.text((82, 534), f"POOL RECOVERY  {recovery:.1f} ms", fill=MINT, font=font("arialbd.ttf", 24))
    draw.text((82, 578), "50-agent queue is the measured bottleneck  ·  next: admission control", fill="white", font=font("arial.ttf", 20))
    image.save(path)


def release_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "ONE-CLICK, READ-ONLY PROOF", "Every claim resolves to a receipt.", dark=True)
    items = [
        "commit + deployed artifact SHA",
        "workflow run + control-plane version",
        "RLS checksum + key-rotation receipt",
        "vector-scale + agent-pressure reports",
        "Devpost submission receipt",
    ]
    for index, item in enumerate(items):
        y = 210 + index * 72
        draw.ellipse((62, y, 88, y + 26), fill=MINT)
        draw.line((69, y + 14, 75, y + 20), fill=INK, width=3)
        draw.line((75, y + 20, 83, y + 8), fill=INK, width=3)
        draw.text((112, y - 2), item, fill="white", font=font("arial.ttf", 23))
    draw.text((748, 592), "NO LOGIN · NO TOKEN · NO WRITE", fill=MINT, font=font("arialbd.ttf", 18))
    image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--scale-evidence", type=Path, required=True)
    parser.add_argument("--pressure-evidence", type=Path, required=True)
    parser.add_argument("--story-screenshot", type=Path, required=True)
    parser.add_argument("--verifier-screenshot", type=Path, required=True)
    parser.add_argument("--narration-wav", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = [args.judge_evidence, args.scale_evidence, args.pressure_evidence, args.story_screenshot, args.verifier_screenshot, args.narration_wav]
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))
    judge = json.loads(args.judge_evidence.read_text(encoding="utf-8"))
    scale = json.loads(args.scale_evidence.read_text(encoding="utf-8"))
    pressure = json.loads(args.pressure_evidence.read_text(encoding="utf-8"))
    if scale.get("gate", {}).get("status") != "PASS":
        raise SystemExit("vector scale evidence is not PASS")
    if pressure.get("gate", {}).get("status") != "PASS":
        raise SystemExit("agent pressure evidence is not PASS")
    duration = wav_duration(args.narration_wav)
    if not 90 <= duration <= 120:
        raise SystemExit(f"narration must be 90-120 seconds, got {duration:.3f}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v3-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(8)]
        story_slide(slides[0], args.story_screenshot)
        architecture_slide(slides[1])
        metrics_slide(slides[2], judge)
        scale_slide(slides[3], scale)
        pressure_slide(slides[4], pressure)
        screenshot_slide(slides[5], args.verifier_screenshot, "PUBLIC JUDGE VERIFIER", "All read-only gates passed.")
        release_slide(slides[6])
        end_slide(slides[7])
        weights = [0.15, 0.12, 0.12, 0.15, 0.17, 0.11, 0.09, 0.09]
        manifest = temp / "slides.txt"
        lines: list[str] = []
        for slide, weight in zip(slides, weights, strict=True):
            lines.extend([f"file '{slide.as_posix()}'", f"duration {duration * weight:.3f}"])
        lines.append(f"file '{slides[-1].as_posix()}'")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        silent = temp / "silent.mp4"
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(silent)])
        run([ffmpeg, "-y", "-i", str(silent), "-i", str(args.narration_wav), "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(args.output)])
    print(f"demo_video_seconds={duration:.3f}")
    print(f"demo_video_sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(f"demo_video_path={args.output}")


if __name__ == "__main__":
    main()

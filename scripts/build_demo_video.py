"""Build the short, secret-free competition demo from captured proof frames."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg


WIDTH = 1280
HEIGHT = 720
BACKGROUND = "#f4f0e6"
INK = "#101815"
GREEN = "#087f57"
MUTED = "#5f6863"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = Path("C:/Windows/Fonts") / name
    if not path.exists():
        return ImageFont.truetype("arial.ttf", size)
    return ImageFont.truetype(str(path), size)


def draw_grid(draw: ImageDraw.ImageDraw) -> None:
    for x in range(0, WIDTH, 32):
        draw.line((x, 0, x, HEIGHT), fill="#e6e0d3", width=1)
    for y in range(0, HEIGHT, 32):
        draw.line((0, y, WIDTH, y), fill="#e6e0d3", width=1)


def title_card(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw_grid(draw)
    draw.rectangle((48, 38, 92, 82), fill=INK)
    draw.text((62, 42), "C", fill=BACKGROUND, font=font("georgia.ttf", 26))
    draw.text((112, 40), "CONTINUUM", fill=INK, font=font("arialbd.ttf", 22))
    draw.text((112, 66), "MEMORY FIREWALL", fill=MUTED, font=font("arial.ttf", 12))
    draw.text((48, 178), "A model may propose.", fill=INK, font=font("georgia.ttf", 62))
    draw.text((48, 250), "The database grants authority.", fill=GREEN, font=font("georgiai.ttf", 57))
    draw.text((48, 370), "Identity-bound semantic memory for long-running AI agents", fill=INK, font=font("arial.ttf", 25))
    draw.rounded_rectangle((48, 474, 1220, 604), radius=8, fill=INK)
    draw.text((78, 506), "LIVE  ·  COGNITO 300s  ·  COCKROACHDB RLS  ·  TITAN v2", fill="#b9f0d7", font=font("arialbd.ttf", 23))
    draw.text((78, 548), "Recall@3  1.0     |     Cross-scope leakage  0.0", fill="white", font=font("arial.ttf", 22))
    image.save(path)


def result_card(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    draw.text((60, 54), "THE RESULT", fill="#b9f0d7", font=font("arialbd.ttf", 18))
    draw.text((60, 112), "Similarity is not authority.", fill="white", font=font("georgia.ttf", 54))
    draw.text((60, 178), "Database presence is not provenance.", fill="#b9f0d7", font=font("georgiai.ttf", 48))
    metrics = [
        ("CALLER IDENTITY", "Cognito client token · 300 seconds"),
        ("ROW ISOLATION", "Three CockroachDB tables · forced RLS"),
        ("SEMANTIC QUALITY", "Titan v2 · Recall@3 = 1.0 across 4 queries"),
        ("LEAKAGE", "0 forbidden documents · rate 0.0"),
    ]
    y = 304
    for label, value in metrics:
        draw.line((60, y - 16, 1220, y - 16), fill="#35433d", width=1)
        draw.text((60, y), label, fill="#83d6b1", font=font("arialbd.ttf", 16))
        draw.text((350, y - 2), value, fill="white", font=font("arial.ttf", 21))
        y += 74
    draw.text((60, 642), "github.com/YongHwan2161/continuum-memory-firewall", fill="#a9b1ad", font=font("arial.ttf", 17))
    image.save(path)


def normalized_screenshot(source: Path, target: Path) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGB")
        image.thumbnail((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        canvas.paste(image, ((WIDTH - image.width) // 2, (HEIGHT - image.height) // 2))
        canvas.save(target)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        return stream.getnframes() / stream.getframerate()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--narration-wav", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    required = [
        args.frames_dir / "continuum-live-overview.png",
        args.frames_dir / "continuum-policy-rejection.png",
        args.frames_dir / "continuum-idempotent-failover.png",
        args.narration_wav,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = max(wav_duration(args.narration_wav) + 2.0, 42.0)
    durations = [5.5, total * 0.25, total * 0.24, total * 0.25]
    durations.append(total - sum(durations))
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    with tempfile.TemporaryDirectory(prefix="continuum-demo-") as directory:
        temporary = Path(directory)
        slides = [temporary / f"slide-{index}.png" for index in range(5)]
        title_card(slides[0])
        normalized_screenshot(required[0], slides[1])
        normalized_screenshot(required[1], slides[2])
        normalized_screenshot(required[2], slides[3])
        result_card(slides[4])

        manifest = temporary / "slides.txt"
        lines: list[str] = []
        for slide, duration in zip(slides, durations, strict=True):
            lines.extend([f"file '{slide.as_posix()}'", f"duration {duration:.3f}"])
        lines.append(f"file '{slides[-1].as_posix()}'")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

        silent = temporary / "silent.mp4"
        run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-vf",
                "fps=30,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                str(silent),
            ]
        )
        run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(silent),
                "-i",
                str(args.narration_wav),
                "-filter_complex",
                "[1:a]apad=pad_dur=2[a]",
                "-map",
                "0:v:0",
                "-map",
                "[a]",
                "-t",
                f"{total:.3f}",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(args.output),
            ]
        )

    print(f"demo_video_seconds={total:.3f}")
    print(f"demo_video_path={args.output}")


if __name__ == "__main__":
    main()


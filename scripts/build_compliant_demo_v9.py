"""Build the under-three-minute live-browser Devpost demo with burned-in captions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import wave

def narration_paragraphs(path: Path) -> list[str]:
    body = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    return [paragraph.strip().replace("\n", " ") for paragraph in body.split("\n\n") if paragraph.strip()]


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, environment: dict[str, str] | None = None) -> None:
    print("RUN", " ".join(command))
    subprocess.run(command, check=True, env=environment)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--narration-text", type=Path, required=True)
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paragraphs = narration_paragraphs(args.narration_text)
    if len(paragraphs) != 9:
        raise SystemExit(f"narration must contain exactly nine paragraphs, found {len(paragraphs)}")
    narration_files = [args.narration_dir / f"segment-{index:02d}.wav" for index in range(1, 10)]
    missing = [str(item) for item in narration_files if not item.is_file()]
    if missing:
        raise SystemExit("missing narration files: " + ", ".join(missing))
    durations = [wav_duration(item) for item in narration_files]
    narration_total = sum(durations)
    if not 90 <= narration_total <= 165:
        raise SystemExit(f"narration must be 90-165 seconds, got {narration_total:.3f}")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.subtitles.parent.mkdir(parents=True, exist_ok=True)
    timing_path = args.work_dir / "timings.json"
    marker_path = args.work_dir / "markers.json"
    timing_path.write_text(json.dumps({
        "segments": [
            {"number": index, "caption": paragraph, "duration_ms": round(duration * 1000)}
            for index, (paragraph, duration) in enumerate(zip(paragraphs, durations, strict=True), start=1)
        ]
    }, indent=2) + "\n", encoding="utf-8")

    environment = os.environ.copy()
    runtime_modules = Path(r"C:\Users\ant71\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules")
    environment["NODE_PATH"] = str(runtime_modules)
    run([
        "node", str(Path(__file__).with_name("capture_compliant_demo_v9.cjs")),
        "--base-url", args.base_url,
        "--timings", str(timing_path),
        "--output-dir", str(args.work_dir),
        "--markers", str(marker_path),
    ], environment=environment)

    markers = json.loads(marker_path.read_text(encoding="utf-8"))["markers"]
    if len(markers) != 9:
        raise SystemExit("browser recording did not produce nine scene markers")
    video_input = args.work_dir / "continuum-live-browser-v9.webm"
    if not video_input.is_file():
        raise SystemExit("browser recording is missing")

    srt_lines: list[str] = []
    for index, (marker, paragraph) in enumerate(zip(markers, paragraphs, strict=True), start=1):
        start = marker["start_ms"] / 1000
        end = (marker["start_ms"] + marker["duration_ms"]) / 1000
        srt_lines.extend((str(index), f"{timestamp(start)} --> {timestamp(end)}", paragraph, ""))
    args.subtitles.write_text("\n".join(srt_lines), encoding="utf-8")

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-y", "-i", str(video_input)]
    for narration in narration_files:
        command.extend(("-i", str(narration)))
    delayed = []
    for index, marker in enumerate(markers, start=1):
        delay = int(marker["start_ms"])
        delayed.append(f"[{index}:a]adelay={delay}|{delay},aresample=48000[a{index}]")
    mix_inputs = "".join(f"[a{index}]" for index in range(1, 10))
    filter_graph = ";".join(delayed + [f"{mix_inputs}amix=inputs=9:duration=longest:normalize=0[aout]"])
    command.extend((
        "-filter_complex", filter_graph,
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(args.output),
    ))
    run(command)

    probe = subprocess.run(
        [ffmpeg, "-i", str(args.output)], capture_output=True, text=True, check=False
    )
    if "Video:" not in probe.stderr or "Audio:" not in probe.stderr:
        raise SystemExit("rendered demo does not contain both video and audio")
    print(f"narration_seconds={narration_total:.3f}")
    print(f"video_sha256={sha256(args.output)}")
    print(f"subtitles_sha256={sha256(args.subtitles)}")
    print(f"video_path={args.output.resolve()}")
    print(f"subtitles_path={args.subtitles.resolve()}")


if __name__ == "__main__":
    main()

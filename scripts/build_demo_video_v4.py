"""Build the paired-outcome, judge-first 90-120 second competition video."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import textwrap

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
    font,
    grid,
    heading,
    run,
    wav_duration,
)


CAPTIONS = (
    "The most relevant memory can still be unsafe. Authority must be earned.",
    "Live: accept trusted evidence, reject poison, retrieve verified memory, act once.",
    "Same incidents: raw RAG succeeds 52.8% and proposes unsafe actions 88.9% of the time.",
    "Continuum: 100% verified outcomes, 0 unsafe proposals, 0 poison exposure.",
    "Search and fetch issue handles; provider receipts gate canonical promotion.",
    "Verified caller -> server scope -> SQL identity -> CockroachDB RLS.",
    "50K vectors and 50 agents: natural ANN, bounded pool, zero leaked rows.",
    "One public button verifies the live service and immutable signed release.",
    "Similarity finds memory. Outcomes earn trust. CockroachDB decides authority.",
)


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _caption(image: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 624, WIDTH, HEIGHT), fill="#08130f")
    lines = textwrap.wrap(text, width=82)
    y = 642 if len(lines) == 1 else 633
    for line in lines[:2]:
        box = draw.textbbox((0, 0), line, font=font("arialbd.ttf", 22))
        x = (WIDTH - (box[2] - box[0])) // 2
        draw.text((x, y), line, fill="white", font=font("arialbd.ttf", 22))
        y += 31


def _finish(path: Path, image: Image.Image, caption: str) -> None:
    _caption(image, caption)
    image.save(path)


def title_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    draw.rectangle((56, 42, 100, 86), fill=INK)
    draw.text((70, 47), "C", fill=PAPER, font=font("georgia.ttf", 25))
    draw.text((120, 44), "CONTINUUM MEMORY FIREWALL", fill=INK, font=font("arialbd.ttf", 21))
    draw.text((56, 164), "Relevant", fill=INK, font=font("georgia.ttf", 62))
    draw.text((305, 164), "does not mean", fill=MUTED, font=font("georgia.ttf", 49))
    draw.text((56, 238), "authorized.", fill="#078454", font=font("georgiai.ttf", 68))
    draw.text((56, 350), "Outcome-gated agent memory on CockroachDB + AWS", fill=MUTED, font=font("arial.ttf", 25))
    draw.rounded_rectangle((56, 454, 1224, 590), radius=10, fill=INK)
    draw.text((84, 486), "STATELESS  ·  RAW RAG  ·  CONTINUUM", fill=MINT, font=font("arialbd.ttf", 22))
    draw.text((84, 534), "540 paired episodes  ·  five seeds  ·  provider receipts", fill="white", font=font("arial.ttf", 22))
    _finish(path, image, CAPTIONS[0])


def screenshot_crop_slide(path: Path, source: Path, *, crop_y: tuple[int, int], eyebrow: str, title: str, caption: str) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, eyebrow, title)
    with Image.open(source) as opened:
        shot = opened.convert("RGB")
        top = max(0, min(crop_y[0], shot.height - 1))
        bottom = max(top + 1, min(crop_y[1], shot.height))
        shot = shot.crop((0, top, shot.width, bottom))
        shot.thumbnail((1160, 420), Image.Resampling.LANCZOS)
        x = (WIDTH - shot.width) // 2
        y = 174 + (420 - shot.height) // 2
        image.paste(shot, (x, y))
        draw.rectangle((x - 2, y - 2, x + shot.width + 2, y + shot.height + 2), outline=INK, width=2)
    _finish(path, image, caption)


def raw_rag_slide(path: Path, ablation: dict) -> None:
    raw = ablation["arms"]["raw_rag"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "THE SAME 180 INCIDENTS", "Raw RAG remembers the attack.", dark=True)
    cards = (
        ("VERIFIED OUTCOME", _percent(raw["verified_outcome_success_rate"])),
        ("UNSAFE PROPOSAL", _percent(raw["unsafe_proposal_rate_under_memory_pressure"])),
        ("POISON EXPOSURE", _percent(raw["poison_exposure_rate"])),
        ("FALSE PROMOTIONS", str(raw["false_canonical_promotions"])),
    )
    for index, (label, value) in enumerate(cards):
        x = 56 + index * 292
        draw.rounded_rectangle((x, 230, x + 260, 442), radius=10, fill="#18221e", outline="#44534c", width=2)
        draw.text((x + 18, 256), label, fill="#aab5af", font=font("arialbd.ttf", 14))
        draw.text((x + 18, 320), value, fill="#ff958f", font=font("georgia.ttf", 43))
    draw.text((56, 508), "Stale, poison, and conflicting memory can become the next action.", fill="white", font=font("arial.ttf", 23))
    draw.text((56, 552), "Append-all memory has no verified outcome boundary.", fill=MINT, font=font("arialbd.ttf", 22))
    _finish(path, image, CAPTIONS[2])


def continuum_slide(path: Path, ablation: dict) -> None:
    arm = ablation["arms"]["continuum"]
    paired = ablation["paired_comparisons"]["continuum_vs_raw_rag"]
    interval = paired["paired_cluster_bootstrap_95_percentage_points"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "OUTCOME-GATED MEMORY", "Continuum remembers only verified success.")
    cards = (
        ("VERIFIED OUTCOME", _percent(arm["verified_outcome_success_rate"])),
        ("UNSAFE PROPOSAL", _percent(arm["unsafe_proposal_rate_under_memory_pressure"])),
        ("POISON EXPOSURE", _percent(arm["poison_exposure_rate"])),
        ("PROMOTION PRECISION", _percent(arm["canonical_promotion_precision"])),
    )
    for index, (label, value) in enumerate(cards):
        x = 56 + index * 292
        draw.rounded_rectangle((x, 224, x + 260, 426), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 18, 250), label, fill=MUTED, font=font("arialbd.ttf", 14))
        draw.text((x + 18, 308), value, fill="#078454", font=font("georgia.ttf", 43))
    draw.rectangle((56, 478, 1224, 588), fill=INK)
    draw.text((82, 501), f"OUTCOME LIFT  +{paired['difference_percentage_points']:.1f} pp", fill=MINT, font=font("arialbd.ttf", 25))
    draw.text((82, 545), f"paired bootstrap 95% CI  +{interval['lower']:.1f} to +{interval['upper']:.1f} pp", fill="white", font=font("arial.ttf", 21))
    _finish(path, image, CAPTIONS[3])


def episode_contract_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "EPISODE CONTRACT", "A receipt, not a model guess, promotes memory.", dark=True)
    cards = (
        ("01", "SEARCH", "server-issued\nhandles"),
        ("02", "PROPOSE", "typed action\nno hidden fields"),
        ("03", "RECEIPT", "provider outcome\nreconciled"),
        ("04", "PROMOTE", "verified success\nonly"),
    )
    for index, (number, label, detail) in enumerate(cards):
        x = 56 + index * 302
        draw.rounded_rectangle((x, 224, x + 252, 506), radius=10, fill="#18221e", outline="#53615a", width=2)
        draw.text((x + 22, 246), number, fill=MINT, font=font("arialbd.ttf", 17))
        draw.text((x + 22, 342), label, fill="white", font=font("arialbd.ttf", 20))
        draw.multiline_text((x + 22, 390), detail, fill="#aeb8b3", font=font("arial.ttf", 18), spacing=7)
        if index < 3:
            draw.text((x + 266, 346), "→", fill=MINT, font=font("arialbd.ttf", 26))
    _finish(path, image, CAPTIONS[4])


def architecture_caption_slide(path: Path) -> None:
    architecture_slide(path)
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    _finish(path, image, CAPTIONS[5])


def scale_pressure_slide(path: Path, pressure: dict, ablation: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "COCKROACHDB AT REAL SCALE", "Relevant, isolated, and bounded under pressure.")
    facts = (
        ("50,000", "512d synthetic vectors"),
        ("96.9%", "Recall@10 · beam 512"),
        ("50", "concurrent agents"),
        ("0", "foreign rows returned"),
    )
    for index, (value, label) in enumerate(facts):
        x = 56 + index * 292
        draw.rounded_rectangle((x, 224, x + 260, 426), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 18, 270), value, fill="#078454", font=font("georgia.ttf", 47))
        draw.text((x + 18, 348), label, fill=MUTED, font=font("arial.ttf", 17))
    fifty_agent = next(level for level in pressure["levels"] if level["concurrent_agents"] == 50)
    draw.rectangle((56, 478, 1224, 588), fill=INK)
    draw.text((82, 501), "20 SQL CONNECTIONS  ·  ONE ACTION OWNER", fill=MINT, font=font("arialbd.ttf", 23))
    draw.text((82, 545), f"50-agent p99 {fifty_agent['latency_ms']['p99']:.1f} ms  ·  Continuum p95 {ablation['arms']['continuum']['latency_ms']['p95']:.1f} ms", fill="white", font=font("arial.ttf", 20))
    _finish(path, image, CAPTIONS[6])


def release_slide(path: Path, judge: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "IMMUTABLE RELEASE ENVELOPE", "One judge button resolves every claim to a receipt.", dark=True)
    items = (
        "live health + exact workflow heads",
        "540 paired episodes + artifact digest",
        "RLS checksum + sandbox provider receipt",
        "GitHub immutable release + signed provenance",
    )
    for index, item in enumerate(items):
        y = 214 + index * 74
        draw.ellipse((62, y, 88, y + 26), fill=MINT)
        draw.text((112, y - 2), item, fill="white", font=font("arial.ttf", 23))
    draw.rounded_rectangle((740, 508, 1224, 584), radius=8, fill=MINT)
    draw.text((778, 532), judge["release_envelope"]["tag"].upper() + "  ·  SIGNED", fill=INK, font=font("arialbd.ttf", 21))
    _finish(path, image, CAPTIONS[7])


def end_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((60, 84), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 18))
    draw.text((60, 194), "Similarity finds memory.", fill="white", font=font("georgia.ttf", 54))
    draw.text((60, 266), "Outcomes earn trust.", fill=MINT, font=font("georgiai.ttf", 52))
    draw.text((60, 338), "CockroachDB decides authority.", fill="white", font=font("georgia.ttf", 48))
    draw.text((60, 476), "ONE-CLICK READ-ONLY PROOF", fill="#aeb8b3", font=font("arialbd.ttf", 17))
    draw.text((60, 516), "yonghwan2161.github.io/continuum-memory-firewall/verify.html", fill="white", font=font("consola.ttf", 20))
    _finish(path, image, CAPTIONS[8])


def _narration_paragraphs(path: Path) -> list[str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]
    paragraphs = [part.strip().replace("\n", " ") for part in re.split(r"\n\s*\n", "\n".join(lines)) if part.strip()]
    if len(paragraphs) != 9:
        raise SystemExit(f"narration must contain 9 paragraphs, got {len(paragraphs)}")
    return paragraphs


def _timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(path: Path, paragraphs: list[str], durations: list[float]) -> None:
    cues: list[str] = []
    cursor = 0.0
    cue = 1
    for paragraph, duration in zip(paragraphs, durations, strict=True):
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", paragraph) if item.strip()]
        weights = [max(len(item), 1) for item in sentences]
        total_weight = sum(weights)
        segment_cursor = cursor
        for index, (sentence, weight) in enumerate(zip(sentences, weights, strict=True)):
            end = cursor + duration if index == len(sentences) - 1 else segment_cursor + duration * weight / total_weight
            cues.append(f"{cue}\n{_timestamp(segment_cursor)} --> {_timestamp(end)}\n{sentence}\n")
            cue += 1
            segment_cursor = end
        cursor += duration
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(cues), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--ablation-evidence", type=Path, required=True)
    parser.add_argument("--pressure-evidence", type=Path, required=True)
    parser.add_argument("--story-screenshot", type=Path, required=True)
    parser.add_argument("--verifier-screenshot", type=Path, required=True)
    parser.add_argument("--narration-text", type=Path, required=True)
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = [args.judge_evidence, args.ablation_evidence, args.pressure_evidence, args.story_screenshot, args.verifier_screenshot, args.narration_text]
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))
    narration_files = [args.narration_dir / f"segment-{index:02d}.wav" for index in range(1, 10)]
    missing_audio = [str(item) for item in narration_files if not item.is_file()]
    if missing_audio:
        raise SystemExit("missing narration segment: " + ", ".join(missing_audio))

    judge = json.loads(args.judge_evidence.read_text(encoding="utf-8"))
    ablation = json.loads(args.ablation_evidence.read_text(encoding="utf-8"))
    pressure = json.loads(args.pressure_evidence.read_text(encoding="utf-8"))
    if judge.get("schema_version") != 5 or not judge.get("release_envelope", {}).get("tag", "").startswith("hackathon-v"):
        raise SystemExit("judge evidence is not a release-bound schema v5 document")
    if ablation.get("schema_version") != 3 or ablation.get("methodology", {}).get("case_count_per_arm") != 180:
        raise SystemExit("ablation evidence is not the 180-case-per-arm schema v3 report")
    if pressure.get("gate", {}).get("status") != "PASS":
        raise SystemExit("agent pressure evidence is not PASS")
    continuum = ablation["arms"]["continuum"]
    if continuum["verified_outcome_success_rate"] != 1.0 or continuum["false_canonical_promotions"] != 0:
        raise SystemExit("Continuum outcome gates are not PASS")

    durations = [wav_duration(path) for path in narration_files]
    total_duration = sum(durations)
    if not 90 <= total_duration <= 120:
        raise SystemExit(f"narration must be 90-120 seconds, got {total_duration:.3f}")
    paragraphs = _narration_paragraphs(args.narration_text)
    write_srt(args.subtitles, paragraphs, durations)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v4-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(9)]
        title_slide(slides[0])
        screenshot_crop_slide(slides[1], args.story_screenshot, crop_y=(480, 1120), eyebrow="LIVE AWS + COCKROACHDB INCIDENT", title="Store. Reject. Retrieve. Act once.", caption=CAPTIONS[1])
        raw_rag_slide(slides[2], ablation)
        continuum_slide(slides[3], ablation)
        episode_contract_slide(slides[4])
        architecture_caption_slide(slides[5])
        scale_pressure_slide(slides[6], pressure, ablation)
        screenshot_crop_slide(slides[7], args.verifier_screenshot, crop_y=(0, 1050), eyebrow="ONE-CLICK JUDGE PROOF", title="The release verifies itself.", caption=CAPTIONS[7])
        end_slide(slides[8])

        video_manifest = temp / "slides.txt"
        video_lines: list[str] = []
        for slide, duration in zip(slides, durations, strict=True):
            video_lines.extend([f"file '{slide.as_posix()}'", f"duration {duration:.3f}"])
        video_lines.append(f"file '{slides[-1].as_posix()}'")
        video_manifest.write_text("\n".join(video_lines) + "\n", encoding="utf-8")

        audio_manifest = temp / "audio.txt"
        audio_manifest.write_text("\n".join(f"file '{path.resolve().as_posix()}'" for path in narration_files) + "\n", encoding="utf-8")
        silent = temp / "silent.mp4"
        narration = temp / "narration.wav"
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(video_manifest), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(silent)])
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(audio_manifest), "-c:a", "pcm_s16le", str(narration)])
        run([ffmpeg, "-y", "-i", str(silent), "-i", str(narration), "-map", "0:v:0", "-map", "1:a:0", "-t", f"{total_duration:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(args.output)])

    print(f"demo_video_seconds={total_duration:.3f}")
    print(f"demo_video_sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(f"demo_subtitles_sha256={hashlib.sha256(args.subtitles.read_bytes()).hexdigest()}")
    print(f"demo_video_path={args.output}")


if __name__ == "__main__":
    main()

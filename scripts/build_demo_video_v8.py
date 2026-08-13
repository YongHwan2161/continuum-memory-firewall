"""Render the receipt-bound v27 provider-origin story as a 90–120 second video."""

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
    font,
    grid,
    heading,
    run,
    wav_duration,
)
from build_demo_video_v4 import _finish, _narration_paragraphs, write_srt
from continuum.provider_origin_story import verify_provider_origin_story


RED = "#b23a34"
SOFT_RED = "#ff958f"
SOFT_GREEN = "#d9f4e8"
DARK_CARD = "#18221e"


def _center(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    *,
    face: str,
    size: int,
    fill: str,
) -> None:
    chosen = font(face, size)
    bounds = draw.textbbox((0, 0), text, font=chosen)
    draw.text(((WIDTH - bounds[2] + bounds[0]) // 2, y), text, fill=fill, font=chosen)


def _caption(story: dict, index: int) -> str:
    return str(story["story"]["scenes"][index]["caption"])


def problem_slide(path: Path, story: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((58, 54), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 20))
    draw.text((58, 150), "The action worker", fill="white", font=font("georgia.ttf", 59))
    draw.text((58, 230), "cannot certify success.", fill=SOFT_RED, font=font("georgiai.ttf", 54))
    draw.rounded_rectangle((58, 382, 1222, 562), radius=12, fill=DARK_CARD, outline="#53615a", width=2)
    draw.text((88, 416), "MODEL CLAIM", fill="#aeb8b3", font=font("arialbd.ttf", 16))
    draw.text((88, 462), "≠  PROVIDER EFFECT  ≠  CANONICAL MEMORY", fill=MINT, font=font("arialbd.ttf", 28))
    draw.text((88, 520), "v27 · receipt-compiled · claim boundary enforced", fill="white", font=font("arial.ttf", 20))
    _finish(path, image, _caption(story, 0))


def provider_slide(path: Path, story: dict) -> None:
    provider = story["live_proof"]["provider"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "RE-READ THE REAL PROVIDER", "Provider truth comes before memory authority.")
    boxes = (
        ("ACTION", "bounded\nproposal"),
        ("S3", "HeadObject\n+ GetObject"),
        ("VERIFIER", "receipt\ncommitment"),
    )
    for index, (label, detail) in enumerate(boxes):
        x = 60 + index * 398
        draw.rounded_rectangle((x, 220, x + 330, 458), radius=12, fill="white", outline="#8d948e", width=2)
        draw.text((x + 22, 266), label, fill="#078454", font=font("arialbd.ttf", 22))
        draw.multiline_text((x + 22, 337), detail, fill=INK, font=font("arial.ttf", 24), spacing=7)
        if index < 2:
            draw.text((x + 342, 320), "→", fill="#078454", font=font("arialbd.ttf", 31))
    draw.rounded_rectangle((60, 510, 1188, 587), radius=8, fill=INK)
    draw.text((86, 532), f"{provider['lookup_count']} FRESH LOOKUPS  ·  REAL S3 RECEIPTS  ·  MODEL TEXT NOT TRUSTED", fill=MINT, font=font("arialbd.ttf", 20))
    _finish(path, image, _caption(story, 1))


def handle_slide(path: Path, story: dict) -> None:
    attestation = story["live_proof"]["attestation"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "ISSUE A SHORT-LIVED CAPABILITY", "The verifier binds authority to one exact effect.", dark=True)
    chips = ("PROPOSAL", "PROVIDER", "IDEMPOTENCY", "RECEIPT", "STATUS", "NONCE")
    for index, label in enumerate(chips):
        column = index % 3
        row = index // 3
        x = 64 + column * 394
        y = 224 + row * 118
        draw.rounded_rectangle((x, y, x + 344, y + 82), radius=9, fill=DARK_CARD, outline="#53615a", width=2)
        _center_in = font("arialbd.ttf", 18)
        bounds = draw.textbbox((0, 0), label, font=_center_in)
        draw.text((x + (344 - bounds[2] + bounds[0]) // 2, y + 29), label, fill=MINT, font=_center_in)
    draw.rounded_rectangle((64, 499, 1216, 585), radius=8, fill=MINT)
    draw.text((90, 523), f"TTL {attestation['ttl_seconds']} SECONDS  ·  KEY ID {attestation['key_id']}  ·  RAW HANDLE STORED 0", fill=INK, font=font("consola.ttf", 20))
    _finish(path, image, _caption(story, 2))


def atomic_slide(path: Path, story: dict) -> None:
    live = story["live_proof"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "ONE COCKROACHDB TRANSACTION", "Authority consumption and memory promotion cannot split.")
    values = (
        (str(live["attestation"]["consumed_rows"]), "ATTESTATION\nCONSUMED"),
        (str(live["cas"]["outcome_rows"]), "VERIFIED\nOUTCOME"),
        (str(live["cas"]["canonical_promotions"]), "CANONICAL\nMEMORY"),
        (str(live["attestation"]["atomic_join_rows"]), "ATOMIC\nJOIN"),
    )
    for index, (value, label) in enumerate(values):
        x = 57 + index * 292
        draw.rounded_rectangle((x, 220, x + 260, 465), radius=11, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 25, 270), value, fill="#078454", font=font("georgia.ttf", 59))
        draw.multiline_text((x + 25, 376), label, fill=INK, font=font("arialbd.ttf", 16), spacing=6)
    draw.text((57, 525), "consume handle digest  +  write outcome  +  promote memory  =  COMMIT", fill=INK, font=font("consola.ttf", 21))
    _finish(path, image, _caption(story, 3))


def attack_slide(path: Path, story: dict) -> None:
    negatives = story["live_proof"]["attestation"]["negative_codes"]
    labels = (
        ("MISSING", negatives["missing_handle"]),
        ("FORGED", negatives["forged_handle"]),
        ("EXPIRED", negatives["expired_handle"]),
        ("CROSS PROPOSAL", negatives["cross_proposal"]),
        ("CROSS PROVIDER", negatives["cross_provider"]),
        ("RECEIPT MISMATCH", negatives["receipt_mismatch"]),
    )
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "ATTACK THE AUTHORITY BOUNDARY", "Invalid authority must create zero memory.", dark=True)
    for index, (label, code) in enumerate(labels):
        column = index % 2
        row = index // 2
        x = 62 + column * 596
        y = 202 + row * 107
        draw.rounded_rectangle((x, y, x + 553, y + 78), radius=8, fill=DARK_CARD, outline="#53615a", width=2)
        draw.text((x + 18, y + 17), label, fill="white", font=font("arialbd.ttf", 17))
        draw.text((x + 211, y + 20), code.replace("OUTCOME_ATTESTATION_", ""), fill=SOFT_RED, font=font("consola.ttf", 15))
    draw.rounded_rectangle((62, 550, 1211, 611), radius=8, fill=MINT)
    _center(draw, "BLOCKED 6 / 6   ·   NEGATIVE OUTCOME ROWS 0", 565, face="arialbd.ttf", size=22, fill=INK)
    _finish(path, image, _caption(story, 4))


def replay_slide(path: Path, story: dict) -> None:
    live = story["live_proof"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "RLS + REPLAY STAY FAIL-CLOSED", "One identity, one durable outcome, explicit conflict.")
    steps = (
        ("01", "ACCEPTED", "new receipt"),
        ("02", "EXACT REPLAY", "same identity"),
        ("03", "CONFLICT", "different receipt"),
    )
    for index, (number, label, detail) in enumerate(steps):
        x = 64 + index * 395
        draw.rounded_rectangle((x, 228, x + 344, 444), radius=11, fill="white", outline="#8d948e", width=2)
        draw.text((x + 21, 252), number, fill="#078454", font=font("arialbd.ttf", 17))
        draw.text((x + 21, 315), label, fill=INK if index < 2 else RED, font=font("arialbd.ttf", 22))
        draw.text((x + 21, 376), detail, fill=MUTED, font=font("arial.ttf", 20))
        if index < 2:
            draw.text((x + 354, 315), "→", fill="#078454", font=font("arialbd.ttf", 29))
    draw.rounded_rectangle((64, 500, 1210, 586), radius=8, fill=INK)
    draw.text((88, 522), f"ATTESTATION ROWS VISIBLE 1  ·  INSERT DENIED {live['rls']['runtime_attestation_insert_sqlstate']}  ·  JOURNAL ROWS {live['cas']['journal_rows']}", fill=MINT, font=font("consola.ttf", 19))
    _finish(path, image, _caption(story, 5))


def architecture_slide(path: Path, story: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "THE CAUSAL MEMORY CONTRACT", "Each authority owns one decision.", dark=True)
    boxes = (
        ("AMAZON BEDROCK", "bounded\nproposal", "MODEL"),
        ("S3 VERIFIER", "fresh provider\nreceipt", "TRUTH"),
        ("COCKROACHDB", "RLS + vector\ncanonical memory", "AUTHORITY"),
    )
    for index, (label, detail, owner) in enumerate(boxes):
        x = 57 + index * 400
        draw.rounded_rectangle((x, 220, x + 340, 475), radius=12, fill=DARK_CARD, outline="#53615a", width=2)
        draw.text((x + 22, 255), owner, fill=MINT, font=font("arialbd.ttf", 15))
        draw.text((x + 22, 313), label, fill="white", font=font("arialbd.ttf", 21))
        draw.multiline_text((x + 22, 376), detail, fill="#aeb8b3", font=font("arial.ttf", 22), spacing=7)
        if index < 2:
            draw.text((x + 352, 325), "→", fill=MINT, font=font("arialbd.ttf", 30))
    draw.text((57, 532), "verified caller → server scope → SQL identity → same-scope memory", fill="white", font=font("consola.ttf", 20))
    _finish(path, image, _caption(story, 6))


def proof_slide(path: Path, story: dict) -> None:
    source = story["source_release"]
    proof = story["release_proof"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "PUBLIC PROOF SURVIVES API FAILURE", "The judge recomputes static, release-bound receipts.")
    rows = (
        ("IMMUTABLE RELEASE", source["tag"].upper()),
        ("ENVELOPE SHA-256", source["envelope_sha256"][:28] + "…"),
        ("NETWORK SIGN-ONCE", "1 AUTHOR  +  1 PLATFORM"),
        ("JUDGE CHECKS", f"{proof['online_check_count']} / {proof['online_check_count']}  ·  GITHUB API {proof['judge_github_api_requests']}")
    )
    for index, (label, value) in enumerate(rows):
        y = 192 + index * 91
        draw.text((66, y + 9), label, fill=MUTED, font=font("arialbd.ttf", 15))
        draw.rounded_rectangle((350, y - 12, 1212, y + 56), radius=7, fill="white", outline="#b8b2a6", width=2)
        draw.text((373, y + 7), value, fill="#078454", font=font("consola.ttf", 21))
    draw.rounded_rectangle((66, 558, 1212, 616), radius=8, fill=MINT)
    _center(draw, "PASS  ·  ZERO CREDENTIALS  ·  ZERO GITHUB API REQUESTS", 572, face="arialbd.ttf", size=21, fill=INK)
    _finish(path, image, _caption(story, 7))


def close_slide(path: Path, story: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((60, 76), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 19))
    draw.text((60, 175), "The model proposes.", fill="white", font=font("georgia.ttf", 55))
    draw.text((60, 251), "The provider proves.", fill=MINT, font=font("georgiai.ttf", 52))
    draw.text((60, 327), "CockroachDB remembers.", fill="white", font=font("georgia.ttf", 52))
    draw.text((60, 466), "PROVIDER-ORIGIN AUTHORITY  ·  ATOMIC MEMORY  ·  RLS  ·  REPLAY CAS", fill="#aeb8b3", font=font("arialbd.ttf", 17))
    draw.text((60, 535), "yonghwan2161.github.io/continuum-memory-firewall/outcome-replay-cas.html", fill="white", font=font("consola.ttf", 18))
    _finish(path, image, _caption(story, 8))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--narration-text", type=Path, required=True)
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.story, args.narration_text):
        if not path.is_file():
            raise SystemExit(f"missing demo input: {path}")

    story = json.loads(args.story.read_text(encoding="utf-8"))
    verify_provider_origin_story(story)
    narration_files = [
        args.narration_dir / f"segment-{index:02d}.wav" for index in range(1, 10)
    ]
    missing_audio = [str(path) for path in narration_files if not path.is_file()]
    if missing_audio:
        raise SystemExit("missing narration segment: " + ", ".join(missing_audio))
    durations = [wav_duration(path) for path in narration_files]
    total_duration = sum(durations)
    duration_contract = story["story"]["required_duration_seconds"]
    if not duration_contract["minimum"] <= total_duration <= duration_contract["maximum"]:
        raise SystemExit(f"narration must be 90-120 seconds, got {total_duration:.3f}")
    paragraphs = _narration_paragraphs(args.narration_text)
    if len(paragraphs) != 9:
        raise SystemExit("narration must contain exactly nine scene paragraphs")
    write_srt(args.subtitles, paragraphs, durations)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v8-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(9)]
        problem_slide(slides[0], story)
        provider_slide(slides[1], story)
        handle_slide(slides[2], story)
        atomic_slide(slides[3], story)
        attack_slide(slides[4], story)
        replay_slide(slides[5], story)
        architecture_slide(slides[6], story)
        proof_slide(slides[7], story)
        close_slide(slides[8], story)

        video_manifest = temp / "slides.txt"
        lines: list[str] = []
        for slide, duration in zip(slides, durations, strict=True):
            lines.extend((f"file '{slide.as_posix()}'", f"duration {duration:.3f}"))
        lines.append(f"file '{slides[-1].as_posix()}'")
        video_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        audio_manifest = temp / "audio.txt"
        audio_manifest.write_text(
            "\n".join(f"file '{path.resolve().as_posix()}'" for path in narration_files)
            + "\n",
            encoding="utf-8",
        )
        silent = temp / "silent.mp4"
        narration = temp / "narration.wav"
        run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(video_manifest),
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
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(audio_manifest),
                "-c:a",
                "pcm_s16le",
                str(narration),
            ]
        )
        run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(silent),
                "-i",
                str(narration),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-t",
                f"{total_duration:.3f}",
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

    print(f"demo_video_seconds={total_duration:.3f}")
    print(f"demo_video_sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(f"demo_subtitles_sha256={hashlib.sha256(args.subtitles.read_bytes()).hexdigest()}")
    print(f"story_receipt_sha256={story['receipt_sha256']}")
    print(f"demo_video_path={args.output}")


if __name__ == "__main__":
    main()

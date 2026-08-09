"""Render the receipt-bound v14 evidence story as a 90-120 second video."""

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
from continuum.evidence_story import verify_evidence_story_receipt


RED = "#b23a34"
SOFT_RED = "#ff958f"
SOFT_GREEN = "#d9f4e8"


def _center(draw: ImageDraw.ImageDraw, text: str, y: int, *, face: str, size: int, fill: str) -> None:
    chosen = font(face, size)
    bounds = draw.textbbox((0, 0), text, font=chosen)
    draw.text(((WIDTH - bounds[2] + bounds[0]) // 2, y), text, fill=fill, font=chosen)


def _caption(story: dict, index: int) -> str:
    return str(story["story"]["scenes"][index]["caption"])


def title_slide(path: Path, story: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((58, 55), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 20))
    draw.text((58, 157), "Failed outcomes", fill="white", font=font("georgia.ttf", 62))
    draw.text((58, 238), "must not become memory.", fill=SOFT_RED, font=font("georgiai.ttf", 53))
    draw.rounded_rectangle((58, 384, 1222, 568), radius=12, fill="#18221e", outline="#53615a", width=2)
    draw.text((89, 418), "MODEL OUTPUT", fill="#aeb8b3", font=font("arialbd.ttf", 17))
    draw.text((89, 463), "→  PROVIDER RECEIPT  →  CANONICAL MEMORY", fill=MINT, font=font("arialbd.ttf", 27))
    draw.text((89, 518), "Evidence-to-story compiler · immutable v14 inputs", fill="white", font=font("arial.ttf", 20))
    _finish(path, image, _caption(story, 0))


def sealed_run_slide(path: Path, story: dict) -> None:
    methodology = story["methodology"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "BLIND, TIME-DISTRIBUTED, REAL", "Same hidden incidents. Three memory policies.")
    values = (
        (str(methodology["sealed_batches"]), "SEALED\nBATCHES"),
        (str(methodology["chains"]), "MEMORY\nCHAINS"),
        (str(methodology["arm_observations"]), "EXTERNAL\nOBSERVATIONS"),
        ("2", "REAL\nADAPTERS"),
    )
    for index, (value, label) in enumerate(values):
        x = 57 + index * 292
        draw.rounded_rectangle((x, 222, x + 260, 455), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 18, 259), value, fill="#078454", font=font("georgia.ttf", 51))
        draw.multiline_text((x + 18, 357), label, fill=INK, font=font("arialbd.ttf", 17), spacing=6)
    draw.rectangle((57, 501, 1219, 584), fill=INK)
    draw.text((82, 526), "BEDROCK-GENERATED HOLDOUT  ·  GITHUB + S3 RECEIPTS  ·  LABELS SEALED", fill=MINT, font=font("arialbd.ttf", 20))
    _finish(path, image, _caption(story, 1))


def paired_result_slide(path: Path, story: dict) -> None:
    scores = story["metrics"]["target_successes"]
    total = scores["episodes_per_arm"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "FUTURE ACTION, MEASURED", f"{total} target episodes per arm. Receipts decide success.")
    items = (
        ("STATELESS", scores["stateless"], "#5f6863"),
        ("RAW RAG", scores["raw_rag"], RED),
        ("CONTINUUM", scores["continuum"], "#078454"),
    )
    for index, (label, value, color) in enumerate(items):
        y = 218 + index * 105
        draw.text((60, y + 12), label, fill=INK, font=font("arialbd.ttf", 20))
        draw.rounded_rectangle((252, y, 1104, y + 60), radius=7, fill="#e7e3dc")
        width = int(852 * value / total)
        draw.rounded_rectangle((252, y, 252 + width, y + 60), radius=7, fill=color)
        draw.text((1126, y + 10), f"{value}/{total}", fill=color, font=font("arialbd.ttf", 22))
    comparison = story["statistics"]["continuum_vs_raw_rag"]
    interval = comparison["hierarchical_cluster_bootstrap_95_percentage_points"]
    draw.rounded_rectangle((60, 548, 1220, 603), radius=7, fill=INK)
    draw.text((82, 565), f"RAW-RAG LIFT  +{comparison['continuum_lift_percentage_points']:.2f} pp  ·  paired 95% CI [{interval['lower']:.2f}, {interval['upper']:.2f}]", fill=MINT, font=font("arialbd.ttf", 20))
    _finish(path, image, _caption(story, 2))


def compounding_slide(path: Path, story: dict) -> None:
    raw = story["metrics"]["raw_rag"]
    continuum = story["metrics"]["continuum"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "THE COMPOUNDING FAILURE", "A wrong outcome becomes a retrieved instruction.", dark=True)
    rows = (
        ("FALSE CANONICAL PROMOTIONS", raw["false_canonical_promotions"], continuum["false_canonical_promotions"]),
        ("UNSAFE MEMORY EXPOSURES", raw["unsafe_memory_exposures"], continuum["unsafe_memory_exposures"]),
        ("UNSAFE CITATION ADOPTIONS", raw["unsafe_memory_citation_adoptions"], 0),
    )
    draw.text((735, 190), "RAW RAG", fill=SOFT_RED, font=font("arialbd.ttf", 16))
    draw.text((1010, 190), "CONTINUUM", fill=MINT, font=font("arialbd.ttf", 16))
    for index, (label, raw_value, continuum_value) in enumerate(rows):
        y = 242 + index * 112
        draw.text((64, y + 25), label, fill="white", font=font("arialbd.ttf", 21))
        draw.text((753, y), str(raw_value), fill=SOFT_RED, font=font("georgia.ttf", 54))
        draw.text((1062, y), str(continuum_value), fill=MINT, font=font("georgia.ttf", 54))
        draw.line((64, y + 92, 1216, y + 92), fill="#53615a", width=1)
    _finish(path, image, _caption(story, 3))


def outcome_gate_slide(path: Path, story: dict) -> None:
    continuum = story["metrics"]["continuum"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "THE MODEL MAY BE WRONG", "Wrong proposals do not become memory.")
    values = (
        (str(continuum["unsafe_proposals"]), "UNSAFE PROPOSALS", RED),
        (str(continuum["false_canonical_promotions"]), "FALSE PROMOTIONS", "#078454"),
        ("100%", "PROMOTION PRECISION", "#078454"),
        (str(continuum["verified_memory_assisted_successes"]), "MEMORY-ASSISTED WINS", "#078454"),
    )
    for index, (value, label, color) in enumerate(values):
        x = 57 + index * 292
        draw.rounded_rectangle((x, 225, x + 260, 462), radius=11, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 18, 278), value, fill=color, font=font("georgia.ttf", 50))
        draw.multiline_text((x + 18, 374), label.replace(" ", "\n", 1), fill=INK, font=font("arialbd.ttf", 15), spacing=6)
    draw.text((57, 518), "proposal confidence  ≠  provider outcome  ≠  memory authority", fill=INK, font=font("consola.ttf", 22))
    _finish(path, image, _caption(story, 4))


def reconciliation_slide(path: Path, story: dict) -> None:
    replay = story["source_artifacts"]["evaluation_replay"]
    transaction = story["release_transaction"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "EVALUATOR CRASH, EVIDENCE PRESERVED", "Recovery reuses the exact candidate artifact.", dark=True)
    steps = (
        ("01", "CANDIDATE", str(replay["candidate_workflow"]["run_id"])),
        ("02", "RUNNER CRASH", "before scoring"),
        ("03", "RECONCILE", "same artifact"),
        ("04", "PUBLIC PASS", str(transaction["pages_workflow_run_id"])),
    )
    for index, (number, label, value) in enumerate(steps):
        x = 51 + index * 306
        draw.rounded_rectangle((x, 234, x + 276, 456), radius=11, fill="#18221e", outline="#53615a", width=2)
        draw.text((x + 20, 260), number, fill=MINT, font=font("arialbd.ttf", 17))
        draw.text((x + 20, 320), label, fill="white", font=font("arialbd.ttf", 19))
        draw.text((x + 20, 384), value, fill="#aeb8b3", font=font("consola.ttf", 16))
        if index < 3:
            draw.text((x + 282, 327), "→", fill=MINT, font=font("arialbd.ttf", 25))
    draw.text((51, 515), "candidate reruns  0   ·   provider re-effects  0   ·   author re-signatures  0", fill="white", font=font("arialbd.ttf", 21))
    _finish(path, image, _caption(story, 5))


def architecture_slide(path: Path, story: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "ONE CAUSAL EPISODE CONTRACT", "Proposal, effect, outcome, and memory remain joined.")
    boxes = (
        ("AWS BEDROCK", "bounded action\nproposal"),
        ("PROVIDER", "GitHub + S3\neffect receipt"),
        ("COCKROACHDB", "RLS + vector\noutcome memory"),
    )
    for index, (label, detail) in enumerate(boxes):
        x = 58 + index * 398
        draw.rounded_rectangle((x, 226, x + 337, 465), radius=12, fill="white", outline="#8d948e", width=2)
        draw.text((x + 22, 276), label, fill="#078454", font=font("arialbd.ttf", 22))
        draw.multiline_text((x + 22, 345), detail, fill=INK, font=font("arial.ttf", 23), spacing=8)
        if index < 2:
            draw.text((x + 349, 325), "→", fill="#078454", font=font("arialbd.ttf", 30))
    draw.rounded_rectangle((58, 510, 1191, 582), radius=7, fill=INK)
    draw.text((82, 533), "verified caller  →  server scope  →  SQL identity  →  same-scope RLS", fill=MINT, font=font("consola.ttf", 20))
    _finish(path, image, _caption(story, 6))


def proof_slide(path: Path, story: dict) -> None:
    source = story["source_release"]
    transaction = story["release_transaction"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "ONE-CLICK, READ-ONLY PROOF", "The story is a receipt projection, not a hand-written claim.", dark=True)
    rows = (
        ("SOURCE RELEASE", source["tag"].upper()),
        ("RELEASE ENVELOPE", source["envelope_sha256"][:24] + "…"),
        ("STORY RECEIPT", story["receipt_sha256"][:24] + "…"),
        ("COORDINATOR RUN", str(transaction["coordinator_workflow_run_id"])),
    )
    for index, (label, value) in enumerate(rows):
        y = 192 + index * 88
        draw.text((67, y + 8), label, fill="#aeb8b3", font=font("arialbd.ttf", 15))
        draw.rounded_rectangle((337, y - 11, 1212, y + 55), radius=7, fill="#18221e", outline="#53615a", width=2)
        draw.text((360, y + 6), value, fill=MINT, font=font("consola.ttf", 21))
    draw.rounded_rectangle((67, 552, 1212, 610), radius=8, fill=MINT)
    _center(draw, "PUBLIC GATE  ·  PASS", 566, face="arialbd.ttf", size=23, fill=INK)
    _finish(path, image, _caption(story, 7))


def end_slide(path: Path, story: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((60, 80), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 19))
    draw.text((60, 184), "Similarity retrieves.", fill="white", font=font("georgia.ttf", 58))
    draw.text((60, 267), "Outcomes earn trust.", fill=MINT, font=font("georgiai.ttf", 54))
    draw.text((60, 410), "BLIND EVALUATION  ·  REAL PROVIDER RECEIPTS  ·  OUTCOME-GATED MEMORY", fill="#aeb8b3", font=font("arialbd.ttf", 18))
    draw.text((60, 500), "ONE-CLICK PUBLIC VERIFIER", fill="white", font=font("arialbd.ttf", 17))
    draw.text((60, 544), "yonghwan2161.github.io/continuum-memory-firewall/verify.html", fill="white", font=font("consola.ttf", 20))
    _finish(path, image, _caption(story, 8))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--narration-text", type=Path, required=True)
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = (args.story, args.narration_text)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))

    story = json.loads(args.story.read_text(encoding="utf-8"))
    if story.get("gate", {}).get("status") != "PASS" or not verify_evidence_story_receipt(story):
        raise SystemExit("evidence story receipt is not a valid PASS")
    if len(story.get("story", {}).get("scenes", [])) != 9:
        raise SystemExit("exactly nine story scenes are required")

    narration_files = [args.narration_dir / f"segment-{index:02d}.wav" for index in range(1, 10)]
    missing_audio = [str(path) for path in narration_files if not path.is_file()]
    if missing_audio:
        raise SystemExit("missing narration segment: " + ", ".join(missing_audio))
    durations = [wav_duration(path) for path in narration_files]
    total_duration = sum(durations)
    contract = story["story"]["required_duration_seconds"]
    if not contract["minimum"] <= total_duration <= contract["maximum"]:
        raise SystemExit(f"narration must be 90-120 seconds, got {total_duration:.3f}")
    paragraphs = _narration_paragraphs(args.narration_text)
    write_srt(args.subtitles, paragraphs, durations)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v7-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(9)]
        title_slide(slides[0], story)
        sealed_run_slide(slides[1], story)
        paired_result_slide(slides[2], story)
        compounding_slide(slides[3], story)
        outcome_gate_slide(slides[4], story)
        reconciliation_slide(slides[5], story)
        architecture_slide(slides[6], story)
        proof_slide(slides[7], story)
        end_slide(slides[8], story)

        video_manifest = temp / "slides.txt"
        lines: list[str] = []
        for slide, duration in zip(slides, durations, strict=True):
            lines.extend((f"file '{slide.as_posix()}'", f"duration {duration:.3f}"))
        lines.append(f"file '{slides[-1].as_posix()}'")
        video_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        audio_manifest = temp / "audio.txt"
        audio_manifest.write_text(
            "\n".join(f"file '{path.resolve().as_posix()}'" for path in narration_files) + "\n",
            encoding="utf-8",
        )
        silent = temp / "silent.mp4"
        narration = temp / "narration.wav"
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(video_manifest), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(silent)])
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(audio_manifest), "-c:a", "pcm_s16le", str(narration)])
        run([ffmpeg, "-y", "-i", str(silent), "-i", str(narration), "-map", "0:v:0", "-map", "1:a:0", "-t", f"{total_duration:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(args.output)])

    print(f"demo_video_seconds={total_duration:.3f}")
    print(f"demo_video_sha256={hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(f"demo_subtitles_sha256={hashlib.sha256(args.subtitles.read_bytes()).hexdigest()}")
    print(f"story_receipt_sha256={story['receipt_sha256']}")
    print(f"demo_video_path={args.output}")


if __name__ == "__main__":
    main()

"""Build the crash-reconciliation, judge-first 90-120 second competition video."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
import imageio_ffmpeg

from build_demo_video_v2 import HEIGHT, INK, MINT, MUTED, PAPER, WIDTH, font, grid, heading, run, wav_duration
from build_demo_video_v4 import _finish, _narration_paragraphs, screenshot_crop_slide, write_srt


CAPTIONS = (
    "A release crashed after signing. The safe retry is reconciliation, not another signature.",
    "Every send, upload, acknowledgement, and publish boundary is a named crash point.",
    "The immutable release keeps the same target, assets, and author provenance.",
    "Retry adopts the provider receipt. Author re-sign count stays at zero.",
    "The coordinator resumes a hash-chained state machine and fails ambiguity closed.",
    "The public receipt binds the successful workflow run and exact artifact digest.",
    "The same envelope carries agent outcomes, CockroachDB isolation, and real-scale ANN evidence.",
    "One read-only click verifies the coordinator, artifact, release, and public materialization.",
    "Similarity finds memory. Outcomes earn trust. Reconciliation preserves proof.",
)


def _center(draw: ImageDraw.ImageDraw, text: str, y: int, *, face: str, size: int, fill: str) -> None:
    chosen = font(face, size)
    box = draw.textbbox((0, 0), text, font=chosen)
    draw.text(((WIDTH - (box[2] - box[0])) // 2, y), text, fill=fill, font=chosen)


def title_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((56, 54), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 19))
    draw.text((56, 160), "The release crashed", fill="white", font=font("georgia.ttf", 57))
    draw.text((56, 232), "after signing.", fill="#ff958f", font=font("georgiai.ttf", 62))
    draw.rounded_rectangle((56, 366, 1224, 568), radius=12, fill="#18221e", outline="#53615a", width=2)
    draw.text((86, 402), "Do not rebuild.  Do not re-sign.", fill="white", font=font("arialbd.ttf", 29))
    draw.text((86, 464), "Reconcile the immutable provider receipt.", fill=MINT, font=font("arialbd.ttf", 28))
    _finish(path, image, CAPTIONS[0])


def crash_matrix_slide(path: Path, fault: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "DISPOSABLE GITHUB PROVIDER", "We crash every external boundary on purpose.")
    labels = [
        "DRAFT\nBEFORE ACK",
        "ASSET\nBEFORE ACK",
        "DUPLICATE\nUPLOAD",
        "RECEIPT\nBEFORE ACK",
        "DELETE\nBEFORE ACK",
    ]
    for index, label in enumerate(labels):
        x = 56 + index * 237
        draw.rounded_rectangle((x, 232, x + 205, 438), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.multiline_text((x + 19, 271), label, fill=INK, font=font("arialbd.ttf", 18), spacing=8)
        draw.text((x + 19, 384), "RECOVERED", fill="#078454", font=font("arialbd.ttf", 15))
    draw.rectangle((56, 492, 1224, 584), fill=INK)
    draw.text((82, 521), f"{len(fault['scenarios'])} / {len(fault['scenarios'])} CRASH POINTS  ·  0 PUBLISHED  ·  0 SIGNATURES", fill=MINT, font=font("arialbd.ttf", 24))
    _finish(path, image, CAPTIONS[1])


def immutable_slide(path: Path, judge: dict, receipt: dict) -> None:
    immutable = next(event["evidence"] for event in receipt["events"] if event["state"] == "IMMUTABLE")
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "PROVIDER TRUTH SURVIVES", "The immutable release is the recovery anchor.", dark=True)
    facts = (
        (judge["release_envelope"]["tag"].upper(), "RELEASE TAG"),
        ("IMMUTABLE", "PROVIDER STATE"),
        (immutable["release_target"][:8], "TARGET SHA"),
        (str(immutable["total_attestation_count"]), "VISIBLE ATTESTATIONS"),
    )
    for index, (value, label) in enumerate(facts):
        x = 56 + index * 292
        draw.rounded_rectangle((x, 226, x + 260, 430), radius=10, fill="#18221e", outline="#53615a", width=2)
        draw.text((x + 18, 264), label, fill="#aeb8b3", font=font("arialbd.ttf", 14))
        draw.text((x + 18, 332), value, fill=MINT, font=font("georgia.ttf", 34))
    draw.text((56, 506), "A retry may observe this state. It may not rewrite its history.", fill="white", font=font("arial.ttf", 24))
    _finish(path, image, CAPTIONS[2])


def resign_slide(path: Path, receipt: dict) -> None:
    author = next(event["evidence"] for event in receipt["events"] if event["state"] == "AUTHOR_ATTESTED")
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "SIGN ONCE, RECONCILE MANY", "Retry does not manufacture new provenance.")
    _center(draw, str(author["author_attestation_count"]), 204, face="georgia.ttf", size=118, fill="#078454")
    _center(draw, "NETWORK-VISIBLE AUTHOR SIGNATURE", 350, face="arialbd.ttf", size=22, fill=INK)
    draw.rounded_rectangle((324, 424, 956, 560), radius=12, fill=INK)
    _center(draw, "+0 signatures on recovery", 456, face="arialbd.ttf", size=28, fill=MINT)
    _center(draw, "existing subject + digest adopted", 508, face="arial.ttf", size=20, fill="white")
    _finish(path, image, CAPTIONS[3])


def reconciliation_slide(path: Path, receipt: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "RELEASE TRANSACTION COORDINATOR", "A monotonic receipt resumes from provider truth.", dark=True)
    states = [event["state"] for event in receipt["events"]]
    for index, state in enumerate(states):
        x = 42 + index * 247
        draw.rounded_rectangle((x, 250, x + 210, 426), radius=10, fill="#18221e", outline="#53615a", width=2)
        draw.text((x + 17, 278), f"0{index + 1}", fill=MINT, font=font("arialbd.ttf", 16))
        draw.text((x + 17, 347), state.replace("_", "\n"), fill="white", font=font("arialbd.ttf", 16), spacing=5)
        if index < len(states) - 1:
            draw.text((x + 218, 326), "→", fill=MINT, font=font("arialbd.ttf", 25))
    draw.text((56, 500), "identity mismatch, digest drift, or unknown effect  →  AMBIGUOUS / HOLD", fill="#ff958f", font=font("arialbd.ttf", 22))
    _finish(path, image, CAPTIONS[4])


def coordinator_slide(path: Path, receipt: dict) -> None:
    terminal = receipt["events"][-1]["evidence"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "PUBLIC TERMINAL RECEIPT", "The coordinator run and artifact are first-class evidence.")
    items = (
        ("WORKFLOW RUN", str(terminal["coordinator_workflow_run_id"])),
        ("ARTIFACT ID", str(terminal["coordinator_artifact_id"])),
        ("ARTIFACT DIGEST", terminal["coordinator_artifact_digest"].split(":", 1)[1][:20] + "…"),
        ("RECEIPT DIGEST", terminal["coordinator_receipt_sha256"][:20] + "…"),
    )
    for index, (label, value) in enumerate(items):
        y = 208 + index * 88
        draw.text((72, y), label, fill=MUTED, font=font("arialbd.ttf", 16))
        draw.rounded_rectangle((330, y - 15, 1208, y + 50), radius=7, fill="white", outline="#b8b2a6", width=2)
        draw.text((354, y + 1), value, fill=INK, font=font("consola.ttf", 22))
    _finish(path, image, CAPTIONS[5])


def product_slide(path: Path, judge: dict, ablation: dict) -> None:
    continuum = ablation["arms"]["continuum"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "WHAT THE ENVELOPE PROTECTS", "Outcome-gated agent memory at real scale.", dark=True)
    facts = (
        ("540", "PAIRED EPISODE OBSERVATIONS"),
        ("0%", "UNSAFE CONTINUUM PROPOSALS"),
        ("50K", "COCKROACHDB VECTORS"),
        ("0", "CROSS-SCOPE LEAKED ROWS"),
    )
    for index, (value, label) in enumerate(facts):
        x = 56 + index * 292
        draw.rounded_rectangle((x, 230, x + 260, 438), radius=10, fill="#18221e", outline="#53615a", width=2)
        draw.text((x + 18, 275), value, fill=MINT, font=font("georgia.ttf", 48))
        draw.multiline_text((x + 18, 352), label.replace(" ", "\n", 1), fill="white", font=font("arialbd.ttf", 15), spacing=5)
    assert continuum["unsafe_proposal_rate_under_memory_pressure"] == 0
    assert judge["evaluation"]["cross_scope_leaked_documents"] == 0
    draw.text((56, 506), "Bedrock proposals  ·  provider receipts  ·  CockroachDB RLS + ANN", fill="white", font=font("arial.ttf", 23))
    _finish(path, image, CAPTIONS[6])


def end_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((60, 82), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 18))
    draw.text((60, 188), "Crash safely.", fill="white", font=font("georgia.ttf", 59))
    draw.text((60, 264), "Reconcile automatically.", fill=MINT, font=font("georgiai.ttf", 53))
    draw.text((60, 338), "Prove it publicly.", fill="white", font=font("georgia.ttf", 54))
    draw.text((60, 478), "ONE-CLICK READ-ONLY PROOF", fill="#aeb8b3", font=font("arialbd.ttf", 17))
    draw.text((60, 518), "yonghwan2161.github.io/continuum-memory-firewall/verify.html", fill="white", font=font("consola.ttf", 20))
    _finish(path, image, CAPTIONS[8])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--transaction-evidence", type=Path, required=True)
    parser.add_argument("--fault-matrix-evidence", type=Path, required=True)
    parser.add_argument("--ablation-evidence", type=Path, required=True)
    parser.add_argument("--verifier-screenshot", type=Path, required=True)
    parser.add_argument("--narration-text", type=Path, required=True)
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = [args.judge_evidence, args.transaction_evidence, args.fault_matrix_evidence, args.ablation_evidence, args.verifier_screenshot, args.narration_text]
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))

    judge = json.loads(args.judge_evidence.read_text(encoding="utf-8"))
    receipt = json.loads(args.transaction_evidence.read_text(encoding="utf-8"))
    fault = json.loads(args.fault_matrix_evidence.read_text(encoding="utf-8"))
    ablation = json.loads(args.ablation_evidence.read_text(encoding="utf-8"))
    if int(judge.get("schema_version", 0)) < 7:
        raise SystemExit("judge evidence is older than schema v7")
    if receipt.get("state") != "PAGES_MATERIALIZED" or len(receipt.get("events", [])) != 5:
        raise SystemExit("release transaction is not terminal")
    terminal = receipt["events"][-1].get("evidence", {})
    if not terminal.get("coordinator_workflow_run_id") or not terminal.get("coordinator_artifact_digest", "").startswith("sha256:"):
        raise SystemExit("terminal receipt lacks coordinator run/artifact binding")
    if fault.get("gate", {}).get("status") != "PASS" or fault.get("author_attestation_count") != 0 or fault.get("published_release_count") != 0:
        raise SystemExit("disposable fault matrix is not non-signing PASS")
    if ablation.get("methodology", {}).get("case_count_per_arm") != 180:
        raise SystemExit("ablation evidence is not the 180-case-per-arm report")

    narration_files = [args.narration_dir / f"segment-{index:02d}.wav" for index in range(1, 10)]
    missing_audio = [str(item) for item in narration_files if not item.is_file()]
    if missing_audio:
        raise SystemExit("missing narration segment: " + ", ".join(missing_audio))
    durations = [wav_duration(path) for path in narration_files]
    total_duration = sum(durations)
    if not 90 <= total_duration <= 120:
        raise SystemExit(f"narration must be 90-120 seconds, got {total_duration:.3f}")
    paragraphs = _narration_paragraphs(args.narration_text)
    write_srt(args.subtitles, paragraphs, durations)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v5-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(9)]
        title_slide(slides[0])
        crash_matrix_slide(slides[1], fault)
        immutable_slide(slides[2], judge, receipt)
        resign_slide(slides[3], receipt)
        reconciliation_slide(slides[4], receipt)
        coordinator_slide(slides[5], receipt)
        product_slide(slides[6], judge, ablation)
        screenshot_crop_slide(slides[7], args.verifier_screenshot, crop_y=(0, 1050), eyebrow="ONE-CLICK JUDGE PROOF", title="The coordinator verifies itself.", caption=CAPTIONS[7])
        end_slide(slides[8])

        video_manifest = temp / "slides.txt"
        lines: list[str] = []
        for slide, duration in zip(slides, durations, strict=True):
            lines.extend([f"file '{slide.as_posix()}'", f"duration {duration:.3f}"])
        lines.append(f"file '{slides[-1].as_posix()}'")
        video_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
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

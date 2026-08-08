"""Build the real-provider, outcome-gated 90-120 second competition video."""

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
    "A failed action must never become the next agent's trusted memory.",
    "The same 36 incidents execute real GitHub Releases draft effects.",
    "Bedrock proposes. GitHub proves. CockroachDB promotes only verified outcomes.",
    "Continuum: 36/36. Raw RAG: 31/36. Unsafe Continuum proposals: zero.",
    "Raw RAG exposed unsafe memory 23 times and adopted it in five actions.",
    "A stale provider list failed closed; the server-issued release ID fixed the identity join.",
    "Release v11 binds source, workflow, artifact, database policy, and public attestations.",
    "One read-only judge flow verifies the real-provider claim and terminal receipt.",
    "Similarity retrieves. Verified outcomes earn trust.",
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
    draw.text((56, 157), "A failed action", fill="white", font=font("georgia.ttf", 61))
    draw.text((56, 235), "must not become memory.", fill="#ff958f", font=font("georgiai.ttf", 54))
    draw.rounded_rectangle((56, 374, 1224, 566), radius=12, fill="#18221e", outline="#53615a", width=2)
    draw.text((86, 411), "MODEL CONFIDENCE  ≠  PROVIDER OUTCOME", fill="white", font=font("arialbd.ttf", 27))
    draw.text((86, 477), "Only a verified receipt crosses the memory gate.", fill=MINT, font=font("arialbd.ttf", 25))
    _finish(path, image, CAPTIONS[0])


def paired_provider_slide(path: Path, guardian: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "REAL EXTERNAL EFFECTS", "Same incident. Same provider state. Different memory policy.")
    values = (
        (str(guardian["methodology"]["paired_cases"]), "PAIRED INCIDENTS"),
        (str(guardian["methodology"]["arm_observations"]), "ARM OBSERVATIONS"),
        (str(guardian["methodology"]["provider_state_families"]), "PROVIDER FAMILIES"),
        ("DRAFT", "PUBLISH STATE"),
    )
    for index, (value, label) in enumerate(values):
        x = 56 + index * 292
        draw.rounded_rectangle((x, 226, x + 260, 438), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 18, 268), value, fill="#078454", font=font("georgia.ttf", 49))
        draw.multiline_text((x + 18, 353), label.replace(" ", "\n", 1), fill=INK, font=font("arialbd.ttf", 15), spacing=5)
    draw.rectangle((56, 493, 1224, 580), fill=INK)
    draw.text((82, 519), "GITHUB RELEASES SANDBOX  ·  CREATE / UPDATE / INSPECT / CLEANUP", fill=MINT, font=font("arialbd.ttf", 21))
    _finish(path, image, CAPTIONS[1])


def architecture_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "OUTCOME-GATED EPISODE CONTRACT", "Identity, effect, and memory share one causal chain.", dark=True)
    boxes = (
        ("01", "BEDROCK", "bounded\naction proposal"),
        ("02", "GITHUB", "server-issued\neffect receipt"),
        ("03", "COCKROACHDB", "verified outcome\n+ RLS promotion"),
    )
    for index, (number, label, detail) in enumerate(boxes):
        x = 58 + index * 398
        draw.rounded_rectangle((x, 229, x + 337, 454), radius=12, fill="#18221e", outline="#53615a", width=2)
        draw.text((x + 22, 254), number, fill=MINT, font=font("arialbd.ttf", 17))
        draw.text((x + 22, 306), label, fill="white", font=font("arialbd.ttf", 23))
        draw.multiline_text((x + 22, 360), detail, fill="#aeb8b3", font=font("arial.ttf", 20), spacing=7)
        if index < 2:
            draw.text((x + 352, 322), "→", fill=MINT, font=font("arialbd.ttf", 30))
    draw.text((56, 510), "caller identity  →  server scope  →  SQL identity  →  same-scope RLS", fill="white", font=font("consola.ttf", 21))
    _finish(path, image, CAPTIONS[2])


def score_slide(path: Path, guardian: dict) -> None:
    continuum = guardian["arms"]["continuum"]
    raw = guardian["arms"]["raw_rag"]
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "SAME 36 INCIDENTS", "Provider success and unsafe proposal outcomes.")
    panels = (
        (66, "RAW RAG", f"{raw['provider_successes']} / {raw['cases']}", f"{raw['unsafe_proposals']} unsafe proposals", "#b23a34"),
        (658, "CONTINUUM", f"{continuum['provider_successes']} / {continuum['cases']}", f"{continuum['unsafe_proposals']} unsafe proposals", "#078454"),
    )
    for x, label, score, unsafe, color in panels:
        draw.rounded_rectangle((x, 215, x + 556, 491), radius=12, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 25, 247), label, fill=MUTED, font=font("arialbd.ttf", 18))
        draw.text((x + 25, 316), score, fill=color, font=font("georgia.ttf", 58))
        draw.text((x + 25, 417), unsafe, fill=INK, font=font("arialbd.ttf", 23))
    comparison = guardian["paired_comparison"]
    draw.text((66, 534), f"PAIRED LIFT  +{comparison['continuum_lift_percentage_points']:.4f} pp  ·  5 wins  ·  0 losses", fill=INK, font=font("arialbd.ttf", 22))
    _finish(path, image, CAPTIONS[3])


def unsafe_memory_slide(path: Path, guardian: dict) -> None:
    continuum = guardian["arms"]["continuum"]
    raw = guardian["arms"]["raw_rag"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "THE MEMORY FAILURE, MEASURED", "Exposure is not the same as adoption; we record both.", dark=True)
    rows = (
        ("UNSAFE MEMORY EXPOSURES", raw["unsafe_memory_exposures"], continuum["unsafe_memory_exposures"]),
        ("UNSAFE CITATION ADOPTIONS", raw["unsafe_memory_citation_adoptions"], continuum["unsafe_memory_citation_adoptions"]),
        ("FALSE CANONICAL PROMOTIONS", raw["false_canonical_promotions"], continuum["false_canonical_promotions"]),
    )
    draw.text((715, 190), "RAW", fill="#ff958f", font=font("arialbd.ttf", 16))
    draw.text((1000, 190), "CONTINUUM", fill=MINT, font=font("arialbd.ttf", 16))
    for index, (label, raw_value, continuum_value) in enumerate(rows):
        y = 245 + index * 112
        draw.text((67, y + 23), label, fill="white", font=font("arialbd.ttf", 21))
        draw.text((735, y), str(raw_value), fill="#ff958f", font=font("georgia.ttf", 53))
        draw.text((1055, y), str(continuum_value), fill=MINT, font=font("georgia.ttf", 53))
        draw.line((65, y + 91, 1215, y + 91), fill="#53615a", width=1)
    _finish(path, image, CAPTIONS[4])


def failed_first_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "FAILED FIRST, THEN FIXED", "The provider exposed the identity bug before the demo did.")
    steps = (
        ("LIST LOOKUP", "briefly stale", "HOLD"),
        ("EXACT RESIDUAL", "draft deleted", "CLEAN"),
        ("SERVER ID", "effect primary key", "PASS"),
    )
    for index, (label, detail, status) in enumerate(steps):
        x = 58 + index * 398
        draw.rounded_rectangle((x, 230, x + 337, 468), radius=12, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 22, 268), label, fill=MUTED, font=font("arialbd.ttf", 17))
        draw.text((x + 22, 333), detail, fill=INK, font=font("arialbd.ttf", 24))
        color = "#b23a34" if status == "HOLD" else "#078454"
        draw.text((x + 22, 405), status, fill=color, font=font("georgia.ttf", 31))
        if index < 2:
            draw.text((x + 352, 329), "→", fill="#078454", font=font("arialbd.ttf", 30))
    draw.text((58, 520), "provider-issued effect identity  >  query-derived identity", fill=INK, font=font("consola.ttf", 22))
    _finish(path, image, CAPTIONS[5])


def envelope_slide(path: Path, judge: dict, receipt: dict) -> None:
    terminal = receipt["events"][-1]["evidence"]
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "IMMUTABLE RELEASE ENVELOPE V11", "One proof unit; no split-brain deployment claims.", dark=True)
    items = (
        ("RELEASE", judge["release_envelope"]["tag"].upper()),
        ("COORDINATOR RUN", str(terminal["coordinator_workflow_run_id"])),
        ("ARTIFACT DIGEST", terminal["coordinator_artifact_digest"].split(":", 1)[1][:18] + "…"),
        ("AUTHOR SIGNATURES", "1  (+0 ON RETRY)"),
    )
    for index, (label, value) in enumerate(items):
        y = 197 + index * 91
        draw.text((67, y + 8), label, fill="#aeb8b3", font=font("arialbd.ttf", 15))
        draw.rounded_rectangle((330, y - 12, 1210, y + 55), radius=7, fill="#18221e", outline="#53615a", width=2)
        draw.text((354, y + 5), value, fill=MINT, font=font("consola.ttf", 22))
    _finish(path, image, CAPTIONS[6])


def end_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((60, 82), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 18))
    draw.text((60, 180), "Similarity retrieves.", fill="white", font=font("georgia.ttf", 57))
    draw.text((60, 259), "Verified outcomes earn trust.", fill=MINT, font=font("georgiai.ttf", 49))
    draw.text((60, 395), "REAL PROVIDER  ·  OUTCOME GATE  ·  PUBLIC PROOF", fill="#aeb8b3", font=font("arialbd.ttf", 18))
    draw.text((60, 488), "ONE-CLICK READ-ONLY VERIFICATION", fill="white", font=font("arialbd.ttf", 17))
    draw.text((60, 529), "yonghwan2161.github.io/continuum-memory-firewall/verify.html", fill="white", font=font("consola.ttf", 20))
    _finish(path, image, CAPTIONS[8])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--guardian-evidence", type=Path, required=True)
    parser.add_argument("--transaction-evidence", type=Path, required=True)
    parser.add_argument("--verifier-screenshot", type=Path, required=True)
    parser.add_argument("--narration-text", type=Path, required=True)
    parser.add_argument("--narration-dir", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = [args.judge_evidence, args.guardian_evidence, args.transaction_evidence, args.verifier_screenshot, args.narration_text]
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))

    judge = json.loads(args.judge_evidence.read_text(encoding="utf-8"))
    guardian = json.loads(args.guardian_evidence.read_text(encoding="utf-8"))
    receipt = json.loads(args.transaction_evidence.read_text(encoding="utf-8"))
    if int(judge.get("schema_version", 0)) < 8:
        raise SystemExit("judge evidence is older than schema v8")
    if guardian.get("gate", {}).get("status") != "PASS" or not guardian.get("real_external_provider"):
        raise SystemExit("real-provider guardian evidence is not PASS")
    if guardian.get("methodology", {}).get("paired_cases") != 36 or guardian.get("methodology", {}).get("arm_observations") != 72:
        raise SystemExit("guardian evidence is not the 36-pair report")
    if receipt.get("state") != "PAGES_MATERIALIZED" or len(receipt.get("events", [])) != 5:
        raise SystemExit("release transaction is not terminal")
    terminal = receipt["events"][-1].get("evidence", {})
    if not terminal.get("coordinator_workflow_run_id") or not terminal.get("coordinator_artifact_digest", "").startswith("sha256:"):
        raise SystemExit("terminal receipt lacks coordinator run/artifact binding")

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
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v6-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(9)]
        title_slide(slides[0])
        paired_provider_slide(slides[1], guardian)
        architecture_slide(slides[2])
        score_slide(slides[3], guardian)
        unsafe_memory_slide(slides[4], guardian)
        failed_first_slide(slides[5])
        envelope_slide(slides[6], judge, receipt)
        screenshot_crop_slide(slides[7], args.verifier_screenshot, crop_y=(0, 1050), eyebrow="ONE-CLICK JUDGE PROOF", title="Thirty-four checks. One public PASS.", caption=CAPTIONS[7])
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

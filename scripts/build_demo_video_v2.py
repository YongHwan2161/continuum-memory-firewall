"""Build the 90–120 second, secret-free competition video from live evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import wave

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg


WIDTH, HEIGHT = 1280, 720
PAPER, INK, GREEN, MINT, MUTED = "#f4f1e8", "#111714", "#078454", "#baf2d7", "#66706b"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(str(path if path.exists() else "arial.ttf"), size)


def grid(draw: ImageDraw.ImageDraw, *, dark: bool = False) -> None:
    color = "#28342f" if dark else "#e5dfd1"
    for x in range(0, WIDTH, 36):
        draw.line((x, 0, x, HEIGHT), fill=color)
    for y in range(0, HEIGHT, 36):
        draw.line((0, y, WIDTH, y), fill=color)


def heading(draw: ImageDraw.ImageDraw, eyebrow: str, title: str, *, dark: bool = False) -> None:
    draw.text((56, 42), eyebrow, fill=MINT if dark else GREEN, font=font("arialbd.ttf", 17))
    draw.text((56, 86), title, fill="white" if dark else INK, font=font("georgia.ttf", 44))


def title_slide(path: Path, judge: dict, scale: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    draw.rectangle((56, 42, 100, 86), fill=INK)
    draw.text((70, 47), "C", fill=PAPER, font=font("georgia.ttf", 25))
    draw.text((120, 44), "CONTINUUM MEMORY FIREWALL", fill=INK, font=font("arialbd.ttf", 21))
    draw.text((56, 178), "Similarity finds memory.", fill=INK, font=font("georgia.ttf", 57))
    draw.text((56, 248), "The database decides authority.", fill=GREEN, font=font("georgiai.ttf", 54))
    draw.text((56, 348), "Identity-bound agentic memory on CockroachDB + AWS", fill=MUTED, font=font("arial.ttf", 24))
    draw.rounded_rectangle((56, 458, 1224, 610), radius=10, fill=INK)
    recall = judge["evaluation"]["recall"]["3"] * 100
    rows = scale["scales"][-1]["row_count"]
    draw.text((86, 492), f"LIVE 60-QUERY RECALL@3  {recall:.1f}%", fill=MINT, font=font("arialbd.ttf", 24))
    draw.text((86, 540), f"NATURAL ANN  {rows:,} VECTORS  ·  CROSS-SCOPE LEAKAGE  0", fill="white", font=font("arial.ttf", 22))
    image.save(path)


def screenshot_slide(path: Path, source: Path, eyebrow: str, title: str) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, eyebrow, title)
    with Image.open(source) as opened:
        shot = opened.convert("RGB")
        shot.thumbnail((1160, 510), Image.Resampling.LANCZOS)
        x = (WIDTH - shot.width) // 2
        y = 176 + (490 - shot.height) // 2
        image.paste(shot, (x, y))
        draw.rectangle((x - 2, y - 2, x + shot.width + 2, y + shot.height + 2), outline=INK, width=2)
    image.save(path)


def architecture_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "SERVER-OWNED AUTHORIZATION", "One caller. One scope. Enforced twice.")
    cards = [
        ("01", "VERIFIED CALLER", "Cognito RS256\n300-second token"),
        ("02", "AUDITED BINDING", "Versioned bind\nrebind · disable"),
        ("03", "SQL IDENTITY", "Deterministic role\nNOBYPASSRLS"),
        ("04", "DATABASE RLS", "Tenant + incident\nforced at row"),
    ]
    for index, (number, label, detail) in enumerate(cards):
        x = 56 + index * 302
        draw.rounded_rectangle((x, 224, x + 252, 506), radius=10, fill="white", outline="#b8b2a6", width=2)
        draw.text((x + 22, 246), number, fill=GREEN, font=font("arialbd.ttf", 17))
        draw.text((x + 22, 346), label, fill=INK, font=font("arialbd.ttf", 18))
        draw.multiline_text((x + 22, 394), detail, fill=MUTED, font=font("arial.ttf", 18), spacing=8)
        if index < 3:
            draw.text((x + 266, 346), "→", fill=GREEN, font=font("arialbd.ttf", 26))
    draw.rectangle((56, 552, 1224, 628), fill="#dff3e8")
    draw.text((82, 575), "Caller input cannot widen scope. The server and database independently agree.", fill=INK, font=font("arialbd.ttf", 21))
    image.save(path)


def metrics_slide(path: Path, judge: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    heading(draw, "LIVE TITAN V2 EVALUATION", "Sixty adversarial queries. Zero foreign rows.", dark=True)
    recalls = judge["evaluation"]["recall"]
    values = [("RECALL@1", recalls["1"]), ("RECALL@3", recalls["3"]), ("RECALL@5", recalls["5"])]
    for index, (label, value) in enumerate(values):
        x = 56 + index * 302
        draw.text((x, 244), label, fill="#9ba7a1", font=font("arialbd.ttf", 15))
        draw.text((x, 288), f"{value * 100:.1f}%", fill=MINT, font=font("georgia.ttf", 54))
    draw.text((974, 244), "P95", fill="#9ba7a1", font=font("arialbd.ttf", 15))
    draw.text((974, 288), f"{judge['evaluation']['latency_ms']['p95']:.1f}", fill="white", font=font("georgia.ttf", 54))
    draw.text((974, 352), "milliseconds", fill="#9ba7a1", font=font("arial.ttf", 16))
    variants = "PARAPHRASE  ·  TERSE  ·  TYPO  ·  NEGATION  ·  MISLEADING SCOPE  ·  MULTI-INTENT"
    draw.rounded_rectangle((56, 456, 1224, 548), radius=8, outline="#53615a", width=2)
    draw.text((80, 489), variants, fill="white", font=font("arialbd.ttf", 16))
    draw.text((56, 610), "cross_scope_leaked_documents = 0", fill=MINT, font=font("arialbd.ttf", 22))
    image.save(path)


def denial_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    heading(draw, "CROSS-SCOPE ATTACK", "A perfect semantic match still returns nothing.", dark=True)
    draw.rounded_rectangle((84, 205, 1196, 602), radius=10, fill="#090d0b", outline="#425048", width=2)
    lines = [
        ("$ fetch(forbidden_memory_id)", "white"),
        ("caller_scope = tenant-a / incident-7", "#7d8a84"),
        ("row_scope    = tenant-b / incident-2", "#7d8a84"),
        ("DENIED  ·  foreign memory invisible", "#ff958f"),
        ("PASS    ·  caller binding + SQL identity + RLS", MINT),
    ]
    for index, (line, color) in enumerate(lines):
        draw.text((120, 254 + index * 62), line, fill=color, font=font("consola.ttf", 22))
    image.save(path)


def scale_slide(path: Path, scale: dict) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "REPRESENTATIVE-SCALE VECTOR PROOF", "Exact ground truth versus natural CockroachDB ANN.")
    report = scale["scales"][-1]
    best = report["beams"][-1]
    draw.text((56, 204), f"{report['row_count']:,}", fill=GREEN, font=font("georgia.ttf", 78))
    draw.text((56, 294), "synthetic 512-dimensional vectors", fill=MUTED, font=font("arial.ttf", 20))
    cards = [
        ("BEAM", str(best["beam_size"])),
        ("RECALL@10", f"{best['recall_by_k']['10'] * 100:.1f}%"),
        ("FIRST P95", f"{best['fresh_connection_first_pass_ms']['p95']:.1f} ms"),
        ("WARM P95", f"{best['same_connection_immediate_repeat_ms']['p95']:.1f} ms"),
    ]
    for index, (label, value) in enumerate(cards):
        x = 56 + index * 292
        draw.rectangle((x, 384, x + 262, 530), fill="white", outline="#bbb5a9", width=2)
        draw.text((x + 18, 406), label, fill=MUTED, font=font("arialbd.ttf", 14))
        draw.text((x + 18, 452), value, fill=INK, font=font("georgia.ttf", 32))
    draw.rectangle((56, 572, 1224, 638), fill=INK)
    draw.text((82, 592), "VECTOR SEARCH OPERATOR  ·  NO FULL SCAN  ·  FOREIGN ROWS 0  ·  GATE PASS", fill=MINT, font=font("arialbd.ttf", 19))
    image.save(path)


def rotation_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    grid(draw)
    heading(draw, "FAIL-CLOSED KEY ROTATION", "Replace. Outwait. Prove. Retire.")
    steps = [("1", "STAGE"), ("2", "REPLACE"), ("3", "WAIT 310s"), ("4", "READ PROOF"), ("5", "RETIRE")]
    for index, (number, label) in enumerate(steps):
        x = 56 + index * 236
        draw.ellipse((x, 266, x + 68, 334), fill=GREEN)
        draw.text((x + 25, 283), number, fill="white", font=font("arialbd.ttf", 20))
        draw.text((x, 370), label, fill=INK, font=font("arialbd.ttf", 18))
        if index < 4:
            draw.line((x + 82, 300, x + 218, 300), fill=GREEN, width=3)
            draw.polygon(((x + 218, 300), (x + 204, 292), (x + 204, 308)), fill=GREEN)
    draw.rounded_rectangle((56, 486, 1224, 598), radius=8, fill=INK)
    draw.text((82, 518), "list_databases ✓   list_tables ✓   insert_rows DENIED ✓", fill=MINT, font=font("consola.ttf", 22))
    draw.text((82, 558), "prior AWS value retained for automatic rollback", fill="white", font=font("arial.ttf", 18))
    image.save(path)


def end_slide(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    grid(draw, dark=True)
    draw.text((60, 96), "CONTINUUM MEMORY FIREWALL", fill=MINT, font=font("arialbd.ttf", 18))
    draw.text((60, 208), "Long-running agents need memory.", fill="white", font=font("georgia.ttf", 54))
    draw.text((60, 278), "Production agents need a firewall.", fill=MINT, font=font("georgiai.ttf", 51))
    draw.text((60, 410), "One-click read-only proof", fill="#aeb8b3", font=font("arial.ttf", 21))
    draw.text((60, 452), "yonghwan2161.github.io/continuum-memory-firewall/verify.html", fill="white", font=font("consola.ttf", 20))
    draw.text((60, 596), "Similarity is not authority. Database presence is not provenance.", fill="#aeb8b3", font=font("arial.ttf", 19))
    image.save(path)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        return stream.getnframes() / stream.getframerate()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--scale-evidence", type=Path, required=True)
    parser.add_argument("--demo-screenshot", type=Path, required=True)
    parser.add_argument("--verifier-screenshot", type=Path, required=True)
    parser.add_argument("--narration-wav", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    required = [args.judge_evidence, args.scale_evidence, args.demo_screenshot, args.verifier_screenshot, args.narration_wav]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing demo input: " + ", ".join(missing))
    judge = json.loads(args.judge_evidence.read_text(encoding="utf-8"))
    scale = json.loads(args.scale_evidence.read_text(encoding="utf-8"))
    if scale.get("gate", {}).get("status") != "PASS":
        raise SystemExit("vector scale evidence is not PASS")
    duration = wav_duration(args.narration_wav)
    if not 90 <= duration <= 120:
        raise SystemExit(f"narration must be 90-120 seconds, got {duration:.3f}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="continuum-demo-v2-") as directory:
        temp = Path(directory)
        slides = [temp / f"slide-{index}.png" for index in range(8)]
        title_slide(slides[0], judge, scale)
        screenshot_slide(slides[1], args.verifier_screenshot, "ONE-CLICK JUDGE PROOF", "Ten public, read-only gates. One button.")
        architecture_slide(slides[2])
        metrics_slide(slides[3], judge)
        denial_slide(slides[4])
        scale_slide(slides[5], scale)
        rotation_slide(slides[6])
        end_slide(slides[7])
        weights = [0.10, 0.11, 0.14, 0.12, 0.12, 0.16, 0.13, 0.12]
        durations = [duration * weight for weight in weights]
        manifest = temp / "slides.txt"
        lines: list[str] = []
        for slide, seconds in zip(slides, durations, strict=True):
            lines.extend([f"file '{slide.as_posix()}'", f"duration {seconds:.3f}"])
        lines.append(f"file '{slides[-1].as_posix()}'")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        silent = temp / "silent.mp4"
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(silent)])
        run([ffmpeg, "-y", "-i", str(silent), "-i", str(args.narration_wav), "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(args.output)])
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f"demo_video_seconds={duration:.3f}")
    print(f"demo_video_sha256={digest}")
    print(f"demo_video_path={args.output}")


if __name__ == "__main__":
    main()

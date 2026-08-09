"""Compile an immutable v14 evaluation into narration and a signed-input receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuum.blind_holdout import write_canonical_json
from continuum.evidence_story import build_evidence_story, render_narration_markdown


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--sequential", type=Path, required=True)
    parser.add_argument("--release-receipt", type=Path, required=True)
    parser.add_argument("--source-release-tag", required=True)
    parser.add_argument("--source-release-target", required=True)
    parser.add_argument("--source-release-envelope-sha256", required=True)
    parser.add_argument("--source-release-sequential-sha256", required=True)
    parser.add_argument("--compiled-at")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--narration-output", type=Path, required=True)
    args = parser.parse_args()

    sequential_bytes = args.sequential.read_bytes()
    story = build_evidence_story(
        json.loads(args.judge.read_text(encoding="utf-8")),
        json.loads(sequential_bytes.decode("utf-8")),
        json.loads(args.release_receipt.read_text(encoding="utf-8")),
        sequential_bytes=sequential_bytes,
        source_release_tag=args.source_release_tag,
        source_release_target=args.source_release_target,
        source_release_envelope_sha256=args.source_release_envelope_sha256,
        source_release_sequential_sha256=args.source_release_sequential_sha256,
        compiled_at=args.compiled_at,
    )
    write_canonical_json(args.output, story)
    args.narration_output.parent.mkdir(parents=True, exist_ok=True)
    args.narration_output.write_text(render_narration_markdown(story), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "status": story["gate"]["status"],
                "story_receipt_sha256": story["receipt_sha256"],
                "output": str(args.output),
                "narration_output": str(args.narration_output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

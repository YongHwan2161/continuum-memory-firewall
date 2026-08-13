"""Compile immutable v27 provider-origin receipts into the video story contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuum.blind_holdout import write_canonical_json
from continuum.provider_origin_story import (
    build_provider_origin_story,
    render_narration_markdown,
)


def _load(path: Path) -> tuple[bytes, dict]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload, value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--transaction", type=Path, required=True)
    parser.add_argument("--network-bundle", type=Path, required=True)
    parser.add_argument("--compiled-at")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--narration-output", type=Path, required=True)
    args = parser.parse_args()

    outcome_bytes, outcome = _load(args.outcome)
    envelope_bytes, envelope = _load(args.envelope)
    capsule_bytes, capsule = _load(args.capsule)
    transaction_bytes, transaction = _load(args.transaction)
    network_bundle_bytes = args.network_bundle.read_bytes()
    story = build_provider_origin_story(
        outcome,
        envelope,
        capsule,
        transaction,
        outcome_bytes=outcome_bytes,
        envelope_bytes=envelope_bytes,
        capsule_bytes=capsule_bytes,
        transaction_bytes=transaction_bytes,
        network_bundle_bytes=network_bundle_bytes,
        compiled_at=args.compiled_at,
    )
    write_canonical_json(args.output, story)
    args.narration_output.parent.mkdir(parents=True, exist_ok=True)
    args.narration_output.write_text(
        render_narration_markdown(story),
        encoding="utf-8",
        newline="\n",
    )
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

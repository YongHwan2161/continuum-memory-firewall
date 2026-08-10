"""Generate the deterministic ambiguity-first challenge and sealed labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuum.adaptive_diagnosis import generate_adaptive_diagnosis_inputs
from continuum.blind_holdout import write_canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--generation-nonce", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    challenge, labels, commitment = generate_adaptive_diagnosis_inputs(
        source_head=args.source_head,
        generation_nonce=args.generation_nonce,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, value in (
        ("adaptive-diagnosis-challenge-v1.json", challenge),
        ("adaptive-diagnosis-labels-v1.json", labels),
        ("adaptive-diagnosis-commitment-v1.json", commitment),
    ):
        write_canonical_json(args.output_dir / filename, value)
    print(
        json.dumps(
            {
                "case_count": challenge["case_count"],
                "challenge_sha256": commitment["challenge_sha256"],
                "labels_sha256": commitment["labels_sha256"],
                "commitment_sha256": commitment["commitment_sha256"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

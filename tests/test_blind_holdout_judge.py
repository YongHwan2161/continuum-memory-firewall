import hashlib
import json
from copy import deepcopy
from pathlib import Path

from scripts.judge_readonly_verify import verify_blind_holdout


ROOT = Path(__file__).parents[1]
PUBLIC_PATH = ROOT / "public-demo" / "evidence" / "blind-holdout-v1.json"
SOURCE = "00a385d1646fa0fd0fd8b9cf067ef635384a002d"
RUN_ID = 31300283080
ARTIFACT_ID = 9034434648
ARTIFACT_NAME = f"continuum-blind-holdout-{SOURCE}"
ARCHIVE_SHA = "bcfa3c3c38b07ee8316ff8cb83684844317132dd81824811d80687c0018bc01f"


def _evidence(public_bytes: bytes) -> dict:
    report = json.loads(public_bytes)
    return {
        "blind_holdout": {
            "head_sha": SOURCE,
            "workflow_run_id": RUN_ID,
            "workflow_attempt": 1,
            "workflow_api_url": "https://api.example.test/runs/31300283080",
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_archive_sha256": ARCHIVE_SHA,
            "artifact_api_url": "https://api.example.test/artifacts/9034434648",
            "public_url": "https://demo.example.test/blind-holdout-v1.json",
            "public_sha256": hashlib.sha256(public_bytes).hexdigest(),
            "challenge_sha256": report["commitment"]["challenge_sha256"],
            "commitment_sha256": report["commitment"]["commitment_sha256"],
            "seal_receipt_sha256": report["seal_receipt"]["receipt_sha256"],
            "sealed_at": report["seal_receipt"]["sealed_at"],
            "generator_model": report["generator_model"],
            "agent_model": report["agent_model"],
            "evaluator_version": report["evaluator"]["version"],
        }
    }


def _fetch(url: str) -> dict:
    if "/runs/" in url:
        return {
            "id": RUN_ID,
            "run_attempt": 1,
            "conclusion": "success",
            "head_sha": SOURCE,
        }
    if "/artifacts/" in url:
        return {
            "id": ARTIFACT_ID,
            "name": ARTIFACT_NAME,
            "digest": "sha256:" + ARCHIVE_SHA,
            "expired": False,
            "workflow_run": {"id": RUN_ID},
        }
    raise AssertionError(url)


def test_live_public_blind_holdout_is_fully_bound() -> None:
    public_bytes = PUBLIC_PATH.read_bytes()
    assert verify_blind_holdout(
        _evidence(public_bytes),
        fetch_json=_fetch,
        fetch_bytes=lambda _url: public_bytes,
    )


def test_blind_holdout_fails_closed_on_candidate_label_access() -> None:
    public = json.loads(PUBLIC_PATH.read_bytes())
    public["methodology"]["candidate_process_opened_labels"] = True
    tampered = (json.dumps(public, sort_keys=True) + "\n").encode()
    assert not verify_blind_holdout(
        _evidence(tampered),
        fetch_json=_fetch,
        fetch_bytes=lambda _url: tampered,
    )


def test_blind_holdout_fails_closed_on_artifact_digest_drift() -> None:
    public_bytes = PUBLIC_PATH.read_bytes()
    evidence = deepcopy(_evidence(public_bytes))

    def drifted(url: str) -> dict:
        result = _fetch(url)
        if "/artifacts/" in url:
            result["digest"] = "sha256:" + "0" * 64
        return result

    assert not verify_blind_holdout(
        evidence,
        fetch_json=drifted,
        fetch_bytes=lambda _url: public_bytes,
    )

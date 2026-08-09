from copy import deepcopy
from datetime import timedelta
import hashlib
import json

from continuum.blind_holdout import canonical_json_bytes, sha256_bytes
from continuum.sequential_blind import (
    aggregate_sequential_blind_campaign,
    build_campaign_manifest,
    build_public_sequential_blind,
)
from scripts.judge_readonly_verify import verify_sequential_blind_campaign
from tests.test_sequential_blind import CAMPAIGN_ID, NOW, SOURCE_HEAD, SequentialBlindTests


RUN_ID = 31320000000
ARTIFACT_ID = 9040000000
ARTIFACT_NAME = f"continuum-sequential-blind-{SOURCE_HEAD}-{RUN_ID}-1"
ARCHIVE_SHA = "c" * 64


def _public() -> dict:
    helper = SequentialBlindTests(
        methodName="test_campaign_preregisters_three_fresh_batches_and_aggregates"
    )
    reports = [helper.report(index) for index in (1, 2, 3)]
    commitments = [report["commitment"] for report in reports]
    manifest = build_campaign_manifest(
        commitments=commitments,
        source_head=SOURCE_HEAD,
        campaign_id=CAMPAIGN_ID,
        created_at=NOW.isoformat(),
    )
    receipts = []
    for report in reports:
        receipts.append(
            {
                "batch_index": report["batch_index"],
                "commitment_sha256": report["commitment"]["commitment_sha256"],
                "report_sha256": sha256_bytes(canonical_json_bytes(report)),
                "receipt_sha256": hashlib.sha256(
                    f"receipt:{report['batch_index']}".encode()
                ).hexdigest(),
            }
        )
    aggregate = aggregate_sequential_blind_campaign(
        reports=reports,
        receipts=receipts,
        manifest=manifest,
        generated_at=(NOW + timedelta(hours=1)).isoformat(),
        aggregation_workflow_run_id=RUN_ID,
        aggregation_workflow_run_attempt=1,
    )
    campaign_seal = {
        "campaign_manifest_sha256": manifest["campaign_manifest_sha256"],
        "receipt_sha256": "d" * 64,
    }
    aggregate["campaign_seal_receipt"] = campaign_seal
    return build_public_sequential_blind(aggregate)


def _evidence(public_bytes: bytes) -> dict:
    report = json.loads(public_bytes)
    return {
        "sequential_blind_campaign": {
            "head_sha": SOURCE_HEAD,
            "workflow_run_id": RUN_ID,
            "workflow_attempt": 1,
            "workflow_api_url": "https://api.example.test/runs/sequential",
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_archive_sha256": ARCHIVE_SHA,
            "artifact_api_url": "https://api.example.test/artifacts/sequential",
            "public_url": "https://demo.example.test/sequential.json",
            "public_sha256": hashlib.sha256(public_bytes).hexdigest(),
            "campaign_id": report["campaign_id"],
            "campaign_manifest_sha256": report["campaign_manifest"][
                "campaign_manifest_sha256"
            ],
            "campaign_seal_receipt_sha256": report["campaign_seal_receipt"][
                "receipt_sha256"
            ],
        }
    }


def _fetch(url: str) -> dict:
    if "/runs/" in url:
        return {
            "id": RUN_ID,
            "run_attempt": 1,
            "conclusion": "success",
            "head_sha": SOURCE_HEAD,
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


def test_sequential_campaign_is_fully_bound() -> None:
    public_bytes = canonical_json_bytes(_public())
    assert verify_sequential_blind_campaign(
        _evidence(public_bytes),
        fetch_json=_fetch,
        fetch_bytes=lambda _url: public_bytes,
    )


def test_sequential_campaign_fails_closed_on_spacing_or_artifact_drift() -> None:
    public = _public()
    public["methodology"]["observed_start_separations_seconds"][0] = 299
    tampered = canonical_json_bytes(public)
    assert not verify_sequential_blind_campaign(
        _evidence(tampered),
        fetch_json=_fetch,
        fetch_bytes=lambda _url: tampered,
    )
    clean = canonical_json_bytes(_public())
    evidence = deepcopy(_evidence(clean))

    def drifted(url: str) -> dict:
        result = _fetch(url)
        if "/artifacts/" in url:
            result["digest"] = "sha256:" + "0" * 64
        return result

    assert not verify_sequential_blind_campaign(
        evidence,
        fetch_json=drifted,
        fetch_bytes=lambda _url: clean,
    )

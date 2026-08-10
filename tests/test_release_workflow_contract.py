from pathlib import Path


WORKFLOW = (
    Path(__file__).parents[1] / ".github" / "workflows" / "release-envelope.yml"
)


def test_upload_artifact_digest_is_normalized_before_pages_dispatch() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'if [[ "$coordinator_artifact_digest" =~ ^[0-9a-f]{64}$ ]]' in workflow
    assert 'coordinator_artifact_digest="sha256:$coordinator_artifact_digest"' in workflow
    assert '[[ "$coordinator_artifact_digest" =~ ^sha256:[0-9a-f]{64}$ ]]' in workflow
    assert '-f coordinator_artifact_digest="$coordinator_artifact_digest"' in workflow
    assert '-f coordinator_artifact_digest="$COORDINATOR_ARTIFACT_DIGEST"' not in workflow


def test_v19_downloads_and_reprojects_exact_adaptive_artifact() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "default: hackathon-v19" in workflow
    assert "for plane in source vector_scale" in workflow
    assert "sequential_blind_campaign ci_recovery adaptive_diagnosis" in workflow
    assert "build/evidence/ci-recovery/ci-recovery-private.json" in workflow
    assert "build_public_ci_recovery(ci_raw)" in workflow
    assert "--ci-recovery-public public-demo/evidence/ci-recovery-v1.json" in workflow
    assert workflow.count('"ci-recovery-v1.json",') == 2
    assert workflow.count('"ci-recovery-v1.json.sha256",') == 2
    assert "build/evidence/adaptive-diagnosis/adaptive-diagnosis-private.json" in workflow
    assert "build_public_adaptive_diagnosis(adaptive_raw)" in workflow
    assert (
        "--adaptive-diagnosis-public "
        "public-demo/evidence/adaptive-diagnosis-v1.json"
    ) in workflow
    assert workflow.count('"adaptive-diagnosis-v1.json",') == 2
    assert workflow.count('"adaptive-diagnosis-v1.json.sha256",') == 2

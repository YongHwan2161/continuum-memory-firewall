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

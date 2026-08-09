"""Promote a receipt-bound story and public video into judge schema v10."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from continuum.evidence_story import verify_evidence_story_receipt


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STORY_ASSET = "evidence-story-v1.json"


def promote_evidence_story(
    judge: Mapping[str, Any],
    story: Mapping[str, Any],
    *,
    story_bytes: bytes,
    repository: str,
    release_tag: str,
    video_url: str,
    video_duration_seconds: float,
    video_sha256: str,
    subtitles_sha256: str,
    project_version: int,
    project_updated_at: str,
) -> dict[str, Any]:
    if int(judge.get("schema_version", 0)) not in {9, 10}:
        raise RuntimeError("judge schema 9 or 10 is required")
    if not verify_evidence_story_receipt(story):
        raise RuntimeError("story receipt self-check failed")
    if story.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("story gate is not PASS")
    if not repository or "/" not in repository:
        raise RuntimeError("repository must be owner/name")
    if not release_tag or any(character.isspace() for character in release_tag):
        raise RuntimeError("invalid release tag")
    if not video_url.startswith("https://youtu.be/"):
        raise RuntimeError("video URL must be a YouTube short URL")
    if not 90 <= float(video_duration_seconds) <= 120:
        raise RuntimeError("video duration must be 90-120 seconds")
    if SHA256_PATTERN.fullmatch(video_sha256) is None:
        raise RuntimeError("invalid video SHA-256")
    if SHA256_PATTERN.fullmatch(subtitles_sha256) is None:
        raise RuntimeError("invalid subtitles SHA-256")
    if project_version < 1 or not project_updated_at:
        raise RuntimeError("invalid Devpost receipt")

    sequential_reference = judge["sequential_blind_campaign"]
    source_release = story["source_release"]
    if source_release["sequential_asset_sha256"] != sequential_reference["public_sha256"]:
        raise RuntimeError("story does not bind the current sequential receipt")
    if story["source_artifacts"]["candidate_workflow_run_id"] != sequential_reference["candidate_workflow_run_id"]:
        raise RuntimeError("story candidate workflow is stale")
    if story["source_artifacts"]["evaluator_workflow_run_id"] != sequential_reference["workflow_run_id"]:
        raise RuntimeError("story evaluator workflow is stale")

    promoted = deepcopy(dict(judge))
    promoted["schema_version"] = 10
    submission = promoted["submission"]
    submission.update(
        {
            "project_updated_at": project_updated_at,
            "project_version": project_version,
            "video_duration_seconds": round(float(video_duration_seconds), 3),
            "video_sha256": video_sha256,
            "video_subtitles_sha256": subtitles_sha256,
            "video_url": video_url,
        }
    )

    story_sha256 = hashlib.sha256(story_bytes.replace(b"\r\n", b"\n")).hexdigest()
    public_base = promoted["public_demo"]["url"].rstrip("/")
    release_download = f"https://github.com/{repository}/releases/download/{release_tag}"
    promoted["evidence_story"] = {
        "schema_version": 1,
        "compiler_path": "scripts/compile_evidence_story_v7.py",
        "video_builder_path": "scripts/build_demo_video_v7.py",
        "source_release_tag": source_release["tag"],
        "source_release_target": source_release["target"],
        "source_release_envelope_sha256": source_release["envelope_sha256"],
        "source_sequential_sha256": source_release["sequential_asset_sha256"],
        "story_receipt_sha256": story["receipt_sha256"],
        "public_sha256": story_sha256,
        "public_url": f"{public_base}/evidence/{STORY_ASSET}",
        "page_url": f"{public_base}/evidence-story.html",
        "video_url": video_url,
        "video_duration_seconds": round(float(video_duration_seconds), 3),
        "video_sha256": video_sha256,
        "subtitles_sha256": subtitles_sha256,
        "immutable_release_asset_url": f"{release_download}/{STORY_ASSET}",
        "claim_boundary": deepcopy(story["claim_boundary"]),
        "gate": deepcopy(story["gate"]),
    }

    release = promoted["release_envelope"]
    for key, value in list(release.items()):
        if key.endswith("_asset_url") and isinstance(value, str):
            asset_name_key = key.removesuffix("_url") + "_name"
            asset_name = release.get(asset_name_key)
            if asset_name:
                release[key] = f"{release_download}/{asset_name}"
    release.update(
        {
            "tag": release_tag,
            "release_url": f"https://github.com/{repository}/releases/tag/{release_tag}",
            "release_api_url": f"https://api.github.com/repos/{repository}/releases/tags/{release_tag}",
            "asset_url": f"{release_download}/{release['asset_name']}",
            "evidence_story_asset_name": STORY_ASSET,
            "evidence_story_asset_url": f"{release_download}/{STORY_ASSET}",
        }
    )
    return promoted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", default="hackathon-v17")
    parser.add_argument("--video-url", required=True)
    parser.add_argument("--video-duration-seconds", type=float, required=True)
    parser.add_argument("--video-sha256", required=True)
    parser.add_argument("--subtitles-sha256", required=True)
    parser.add_argument("--project-version", type=int, required=True)
    parser.add_argument("--project-updated-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    story_bytes = args.story.read_bytes()
    promoted = promote_evidence_story(
        json.loads(args.judge.read_text(encoding="utf-8")),
        json.loads(story_bytes),
        story_bytes=story_bytes,
        repository=args.repository,
        release_tag=args.release_tag,
        video_url=args.video_url,
        video_duration_seconds=args.video_duration_seconds,
        video_sha256=args.video_sha256,
        subtitles_sha256=args.subtitles_sha256,
        project_version=args.project_version,
        project_updated_at=args.project_updated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(promoted, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "status": promoted["evidence_story"]["gate"]["status"],
                "schema_version": promoted["schema_version"],
                "release_tag": promoted["release_envelope"]["tag"],
                "video_url": promoted["submission"]["video_url"],
                "project_version": promoted["submission"]["project_version"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

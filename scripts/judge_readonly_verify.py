"""Verify the public judge path using bounded HTTP GET requests only."""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_EVIDENCE_URL = (
    "https://yonghwan2161.github.io/continuum-memory-firewall/"
    "evidence/judge-verification.json"
)
MAX_RESPONSE_BYTES = 1_000_000


def _require_https(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username:
        raise RuntimeError("judge verification permits absolute HTTPS URLs only")


def _get_bytes(url: str, *, timeout: float = 10.0) -> bytes:
    _require_https(url)
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
            "User-Agent": "continuum-memory-firewall-judge-verifier/1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("judge verification response exceeded the size limit")
    return body


def get_json(url: str) -> dict[str, Any]:
    payload = json.loads(_get_bytes(url).decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("expected a JSON object")
    return payload


def get_text(url: str) -> str:
    return _get_bytes(url).decode("utf-8", errors="strict")


def verify_evidence(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]] = get_json,
    fetch_text: Callable[[str], str] = get_text,
) -> dict[str, Any]:
    source = evidence["source"]
    evaluation = evidence["evaluation"]
    runtime = evidence["runtime"]
    submission = evidence["submission"]
    public_demo = evidence["public_demo"]
    workflow = fetch_json(source["workflow_api_url"])
    health = fetch_json(runtime["health_url"])
    demo_html = fetch_text(public_demo["url"])

    checks = {
        "submission_recorded": submission["status"] == "Submitted",
        "competition_query_count": int(evaluation["query_count"]) >= 50,
        "recall_at_3_gate": float(evaluation["recall"]["3"]) >= 0.75,
        "zero_cross_scope_leakage": (
            int(evaluation["cross_scope_leaked_documents"]) == 0
        ),
        "workflow_succeeded": workflow.get("conclusion") == "success",
        "workflow_head_matches": (
            workflow.get("head_sha") == source["deployment_head_sha"]
        ),
        "mcp_health_ok": health.get("ok") is True,
        "mcp_service_matches": (
            health.get("service") == "continuum-memory-firewall"
        ),
        "public_demo_marker_present": public_demo["marker"] in demo_html,
        "cross_scope_fetch_denied": runtime["cross_scope_fetch_denied"] is True,
        "migration_capability_absent": (
            runtime["temporary_migration_capability_absent"] is True
        ),
    }
    return {
        "ok": all(checks.values()),
        "mode": "read-only-http-get",
        "workflow_run_id": source["workflow_run_id"],
        "deployment_head_sha": source["deployment_head_sha"],
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-url", default=DEFAULT_EVIDENCE_URL)
    args = parser.parse_args()
    evidence = get_json(args.evidence_url)
    report = verify_evidence(evidence)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

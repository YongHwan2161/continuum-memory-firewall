"""Transform a legacy fixed-bearer secret into the OIDC caller registry shape.

Secret JSON is read from stdin and written to stdout so the deployment script
can keep it inside one pipe.  No secret field is logged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--required-scope", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise RuntimeError("runtime secret must be an object")

    caller_scopes = payload.get("caller_scopes")
    if isinstance(caller_scopes, dict) and caller_scopes:
        prior_scope = next(iter(caller_scopes.values()))
    else:
        prior_scope = {
            "tenant_id": payload.pop("tenant_id"),
            "incident_id": payload.pop("incident_id"),
        }
    payload["caller_scopes"] = {args.client_id: prior_scope}
    payload["oidc_issuer"] = args.issuer
    payload["oidc_required_scope"] = args.required_scope
    payload["bedrock_region"] = args.region
    replacement_database_url = os.environ.get("CONTINUUM_NEW_DATABASE_URL")
    if replacement_database_url:
        payload["database_url"] = replacement_database_url
    payload.pop("bearer_token", None)
    json.dump(payload, sys.stdout, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    main()

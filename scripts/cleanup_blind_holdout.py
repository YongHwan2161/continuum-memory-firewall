"""Delete and prove absence under one bounded blind-holdout S3 prefix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any


def cleanup(*, client: Any, bucket: str, prefix: str) -> dict[str, Any]:
    if re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket) is None:
        raise ValueError("bucket is invalid")
    if re.fullmatch(r"blind-holdout-sandbox/blind-[0-9]+-[0-9]+", prefix) is None:
        raise ValueError("cleanup prefix is outside the blind holdout sandbox")
    prefix_with_slash = prefix + "/"
    deleted_count = 0
    continuation_token = None
    while True:
        request = {"Bucket": bucket, "Prefix": prefix_with_slash}
        if continuation_token is not None:
            request["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**request)
        objects = [
            {"Key": item["Key"]}
            for item in response.get("Contents", [])
            if isinstance(item, dict) and isinstance(item.get("Key"), str)
        ]
        if objects:
            client.delete_objects(
                Bucket=bucket, Delete={"Objects": objects, "Quiet": True}
            )
            deleted_count += len(objects)
        if response.get("IsTruncated") is not True:
            break
        continuation_token = response.get("NextContinuationToken")
        if not isinstance(continuation_token, str) or not continuation_token:
            raise RuntimeError("S3 cleanup pagination token is missing")
    residual = client.list_objects_v2(
        Bucket=bucket, Prefix=prefix_with_slash, MaxKeys=1
    )
    residual_count = int(residual.get("KeyCount", 0))
    if residual_count != 0 or residual.get("Contents"):
        raise RuntimeError("blind holdout sandbox cleanup left a residual object")
    return {
        "deleted_count": deleted_count,
        "prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "residual_count": 0,
    }


def main() -> None:
    import boto3

    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    receipt = cleanup(
        client=boto3.client("s3", region_name=args.region),
        bucket=args.bucket,
        prefix=args.prefix,
    )
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()

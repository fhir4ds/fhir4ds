#!/usr/bin/env python3
"""AMUX-39: push the converted chunk corpus to an S3-compatible endpoint.

  python3 benchmarks/scaling/s3_push.py s3://bucket/prefix \
      [--endpoint-url http://localhost:7070] [--workers 8]

Auth: standard boto3 chain (env AWS_*, or --access-key/--secret-key for
local endpoints like `rclone serve s3` / MinIO). Pushes chunk_*.parquet +
terminology.parquet + chunks.json. Idempotent: skips objects that already
exist with the same size.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from omop_common import CONVERTED


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", help="s3://bucket/prefix")
    ap.add_argument("--endpoint-url", default=None)
    ap.add_argument("--access-key", default=None)
    ap.add_argument("--secret-key", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--source", default=str(CONVERTED))
    args = ap.parse_args()

    import boto3
    from botocore.client import Config as BotoConfig

    if not args.dest.startswith("s3://"):
        raise SystemExit("dest must be s3://bucket/prefix")
    _, _, bucket, prefix = args.dest.split("/", 3)

    kwargs = {"service_name": "s3",
              "config": BotoConfig(signature_version="s3v4",
                                   s3={"addressing_style": "path"})}
    if args.endpoint_url:
        kwargs["endpoint_url"] = args.endpoint_url
    if args.access_key:
        kwargs["aws_access_key_id"] = args.access_key
        kwargs["aws_secret_access_key"] = args.secret_key
    s3 = boto3.client(**kwargs)

    files = sorted(Path(args.source).glob("*.parquet")) + \
        [Path(args.source) / "chunks.json"]
    existing = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            existing[obj["Key"]] = obj["Size"]

    jobs = []
    for f in files:
        key = f"{prefix}/{f.name}".lstrip("/")
        if existing.get(key) == f.stat().st_size:
            continue
        jobs.append((f, key))
    total = sum(f.stat().st_size for f, _ in jobs)
    print(f"{len(files)} files, {len(jobs)} to upload "
          f"({total / 2**20:,.1f} MB) -> {args.dest}")

    def push(job):
        f, key = job
        s3.upload_file(str(f), bucket, key)
        return key

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key in pool.map(push, jobs):
            done += 1
            print(f"  [{done}/{len(jobs)}] {key}", flush=True)
    print("push complete")


if __name__ == "__main__":
    main()

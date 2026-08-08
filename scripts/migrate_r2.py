#!/usr/bin/env python3
"""
Migrate tất cả objects từ R2 cũ sang R2 mới bằng boto3 streaming.
Chạy: python3 migrate_r2.py
"""
import os
import sys
import boto3
from botocore.client import Config

SRC_ENDPOINT = os.environ["SRC_R2_ENDPOINT"]
SRC_KEY      = os.environ["SRC_R2_ACCESS_KEY"]
SRC_SECRET   = os.environ["SRC_R2_SECRET_KEY"]

DST_ENDPOINT = os.environ["DST_R2_ENDPOINT"]
DST_KEY      = os.environ["DST_R2_ACCESS_KEY"]
DST_SECRET   = os.environ["DST_R2_SECRET_KEY"]

BUCKETS = [b.strip() for b in os.environ.get("BUCKETS", "atl-media,atl-output").split(",") if b.strip()]


def make_client(endpoint, key, secret):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket(client, bucket):
    # Bucket phải được tạo trước trên Cloudflare Dashboard
    # Script chỉ kiểm tra có truy cập được không
    try:
        client.head_bucket(Bucket=bucket)
        print(f"  [ok] {bucket}")
    except Exception as e:
        print(f"  [WARN] {bucket}: {e} — tạo bucket trên Cloudflare Dashboard trước!", file=sys.stderr)


def migrate_bucket(src, dst, bucket):
    print(f"\n=== Migrating bucket: {bucket} ===")
    ensure_bucket(dst, bucket)

    paginator = src.get_paginator("list_objects_v2")
    total = copied = skipped = errors = 0

    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            total += 1
            try:
                # Kiểm tra object đã tồn tại ở đích chưa (skip nếu size bằng nhau)
                try:
                    dst_head = dst.head_object(Bucket=bucket, Key=key)
                    if dst_head["ContentLength"] == obj["Size"]:
                        skipped += 1
                        continue
                except dst.exceptions.ClientError:
                    pass

                # Stream copy: không load hết vào RAM
                src_obj = src.get_object(Bucket=bucket, Key=key)
                body = src_obj["Body"]
                content_type = src_obj.get("ContentType", "application/octet-stream")

                dst.upload_fileobj(
                    body,
                    bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
                copied += 1
                if copied % 50 == 0:
                    print(f"  copied {copied} / skipped {skipped} / errors {errors} (total scanned {total})")
            except Exception as e:
                errors += 1
                print(f"  [ERROR] {key}: {e}", file=sys.stderr)

    print(f"  DONE: copied={copied}  skipped={skipped}  errors={errors}  total={total}")
    return errors


def main():
    src = make_client(SRC_ENDPOINT, SRC_KEY, SRC_SECRET)
    dst = make_client(DST_ENDPOINT, DST_KEY, DST_SECRET)

    total_errors = 0
    for bucket in BUCKETS:
        total_errors += migrate_bucket(src, dst, bucket)

    if total_errors:
        print(f"\n⚠  Xong nhưng có {total_errors} lỗi — kiểm tra stderr.")
        sys.exit(1)
    else:
        print("\n✓ Migration hoàn tất, không có lỗi.")


if __name__ == "__main__":
    main()

"""
Thin wrapper around boto3's S3 client, pointed at MinIO locally and at real
AWS S3 in production via S3_ENDPOINT_URL. Raw uploaded documents (PDF, DOCX,
CSV, TXT) are stored here — never inlined into PostgreSQL rows.
"""
import uuid

import boto3
from botocore.client import Config as BotoConfig

from app.config import get_settings

settings = get_settings()

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY_ID,
    aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
    region_name=settings.S3_REGION,
    config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path" if settings.S3_USE_PATH_STYLE else "auto"}),
)


def ensure_bucket_exists() -> None:
    existing = [b["Name"] for b in _s3.list_buckets().get("Buckets", [])]
    if settings.S3_BUCKET not in existing:
        _s3.create_bucket(Bucket=settings.S3_BUCKET)


def build_object_key(workspace_id: uuid.UUID, bot_id: uuid.UUID, filename: str) -> str:
    safe_name = filename.replace("/", "_")
    return f"workspaces/{workspace_id}/bots/{bot_id}/documents/{uuid.uuid4()}_{safe_name}"


def upload_bytes(object_key: str, data: bytes, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    _s3.put_object(Bucket=settings.S3_BUCKET, Key=object_key, Body=data, **extra)


def download_bytes(object_key: str) -> bytes:
    obj = _s3.get_object(Bucket=settings.S3_BUCKET, Key=object_key)
    return obj["Body"].read()


def delete_object(object_key: str) -> None:
    _s3.delete_object(Bucket=settings.S3_BUCKET, Key=object_key)


def presigned_get_url(object_key: str, expires_seconds: int = 600) -> str:
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": object_key},
        ExpiresIn=expires_seconds,
    )

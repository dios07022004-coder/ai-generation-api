"""S3-совместимое хранилище: AWS S3, Cloudflare R2, MinIO.

Различие между ними — только endpoint_url и публичный URL, поэтому один класс.
  AWS S3 : S3_ENDPOINT_URL пустой, регион реальный
  R2     : S3_ENDPOINT_URL=https://<acc>.r2.cloudflarestorage.com, регион auto
  MinIO  : S3_ENDPOINT_URL=http://minio:9000
"""
import boto3
from botocore.client import Config

from app.core.config import settings

from .base import StorageProvider


class S3Storage(StorageProvider):
    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
        )

    def save(self, key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        if settings.S3_PUBLIC_URL:
            return f"{settings.S3_PUBLIC_URL.rstrip('/')}/{key}"
        # presigned URL как fallback, если нет публичного домена
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=86400
        )

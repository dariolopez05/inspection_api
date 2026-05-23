import logging
import time

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import get_settings

logger = logging.getLogger("uvicorn.error")

EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket(client: BaseClient, bucket: str, retries: int = 10) -> None:
    for attempt in range(1, retries + 1):
        try:
            buckets = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
            if bucket not in buckets:
                client.create_bucket(Bucket=bucket)
                logger.info("Bucket S3 creado: %s", bucket)
            return
        except Exception as exc:
            if attempt == retries:
                raise
            logger.warning("S3 no disponible (%s/%s): %s", attempt, retries, exc)
            time.sleep(2)


def object_key(plate_number: str, inspection_id: int, content_type: str) -> str:
    ext = EXT_BY_CONTENT_TYPE.get(content_type, ".bin")
    return f"{plate_number}/{inspection_id}{ext}"


def upload_image(
    client: BaseClient, bucket: str, key: str, data: bytes, content_type: str
) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

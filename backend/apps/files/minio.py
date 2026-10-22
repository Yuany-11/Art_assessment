"""MinIO（S3 兼容）对象存储访问。"""
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings


@lru_cache(maxsize=1)
def get_client():
    endpoint = f"{'https' if settings.MINIO_USE_SSL else 'http'}://{settings.MINIO_ENDPOINT}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    client = get_client()
    try:
        client.head_bucket(Bucket=settings.MINIO_BUCKET)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchBucket", "NotFound"}:
            client.create_bucket(Bucket=settings.MINIO_BUCKET)
        else:
            raise


def upload_object(uploaded, object_key: str, mime_type: str) -> None:
    ensure_bucket()
    uploaded.seek(0)
    get_client().put_object(
        Bucket=settings.MINIO_BUCKET,
        Key=object_key,
        Body=uploaded,
        ContentType=mime_type,
    )


def delete_object(object_key: str) -> None:
    get_client().delete_object(Bucket=settings.MINIO_BUCKET, Key=object_key)


def presigned_url(object_key: str, expires: int | None = None) -> str:
    return get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.MINIO_BUCKET, "Key": object_key},
        ExpiresIn=expires or settings.MINIO_PRESIGN_EXPIRES,
    )

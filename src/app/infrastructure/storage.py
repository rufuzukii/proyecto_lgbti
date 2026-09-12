from __future__ import annotations

import os
from functools import lru_cache
from typing import Any
from urllib.parse import quote, urlsplit

from app.core.config import get_app_config

DEFAULT_SUPABASE_STORAGE_BUCKET = "felgtbi-reports"
DEFAULT_DIDACTIC_SLIDES_BUCKET = "slideshow-didactics"


def supabase_public_object_url(storage_path: object, *, bucket: str | None = None) -> str:
    """Construye una URL pública de Supabase Storage sin persistir ese valor derivado."""
    clean_path = _clean_storage_path(storage_path)
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    clean_bucket = (
        str(bucket or os.getenv("SUPABASE_STORAGE_BUCKET", DEFAULT_SUPABASE_STORAGE_BUCKET))
        .strip()
        .strip("/")
    )
    if not clean_path or not supabase_url or not clean_bucket:
        return ""
    parsed_url = urlsplit(supabase_url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
        or (not get_app_config().local_mode and parsed_url.scheme != "https")
    ):
        return ""
    return (
        f"{supabase_url}/storage/v1/object/public/"
        f"{quote(clean_bucket, safe='')}/{quote(clean_path, safe='/')}"
    )


def supabase_public_image_url(storage_path: object, *, bucket: str | None = None) -> str:
    """Mantiene el alias de compatibilidad para los consumidores de imágenes públicas."""
    return supabase_public_object_url(storage_path, bucket=bucket)


@lru_cache(maxsize=2)
def supabase_s3_client(
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str,
) -> Any:
    """Devuelve el cliente S3 de Supabase compartido, con tiempos de espera acotados."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            connect_timeout=max(1, int(os.getenv("SUPABASE_CONNECT_TIMEOUT_SECONDS", "3"))),
            read_timeout=max(1, int(os.getenv("SUPABASE_READ_TIMEOUT_SECONDS", "10"))),
            retries={"mode": "standard", "total_max_attempts": 2},
            max_pool_connections=4,
            s3={"addressing_style": "path"},
        ),
    )


def supabase_s3_config(*, bucket: str) -> dict[str, str] | None:
    """Lee la configuración S3 de Supabase sin exponer credenciales."""
    endpoint = os.getenv("SUPABASE_S3_ENDPOINT", "").strip()
    access_key = os.getenv("SUPABASE_S3_ACCESS_KEY", "").strip()
    secret_key = os.getenv("SUPABASE_S3_SECRET_KEY", "").strip()
    clean_bucket = str(bucket or "").strip().strip("/")
    if not endpoint or not access_key or not secret_key or not clean_bucket:
        return None
    parsed_endpoint = urlsplit(endpoint)
    if parsed_endpoint.scheme not in {"http", "https"} or not parsed_endpoint.hostname:
        return None
    if not get_app_config().local_mode and parsed_endpoint.scheme != "https":
        return None
    return {
        "bucket": clean_bucket,
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "region": os.getenv("SUPABASE_S3_REGION", "us-east-1").strip() or "us-east-1",
    }


def _clean_storage_path(value: object) -> str:
    path = str(value or "").strip().replace("\\", "/").lstrip("/")
    if (
        not path
        or "://" in path
        or path.lower().startswith("assets/")
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        return ""
    return path

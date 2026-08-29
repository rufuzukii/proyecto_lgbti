from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.infrastructure.storage import (
    DEFAULT_SUPABASE_STORAGE_BUCKET,
    supabase_s3_client,
    supabase_s3_config,
)

FIGURE_IMAGE_EXTENSION = "webp"
_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def upload_figure_to_supabase(
    *,
    image_bytes: bytes,
    storage_path: str,
    mime_type: str,
    checksum: str,
) -> dict[str, Any]:
    config = supabase_storage_config()
    if not config:
        return {
            "status": "failed",
            "error": "supabase_storage_not_configured",
            "bucket": supabase_storage_bucket(),
            "storage_path": storage_path,
        }
    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return {
            "status": "failed",
            "error": "boto3_not_installed",
            "bucket": config["bucket"],
            "storage_path": storage_path,
        }

    client = supabase_s3_client(
        config["endpoint"], config["access_key"], config["secret_key"], config["region"]
    )
    should_upload = True
    try:
        existing = client.head_object(Bucket=config["bucket"], Key=storage_path)
        metadata = existing.get("Metadata") or {}
        if metadata.get("checksum") == checksum:
            should_upload = False
    except ClientError as exc:
        response = exc.response if isinstance(exc.response, dict) else {}
        error_value = response.get("Error")
        error: dict[str, Any] = error_value if isinstance(error_value, dict) else {}
        status_code = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
        error_code = str(error.get("Code") or status_code or exc.__class__.__name__)
        if status_code != 404 and error_code not in {"404", "NoSuchKey", "NotFound"}:
            return _storage_failure(config["bucket"], storage_path, f"head_object:{error_code}")
    except (BotoCoreError, OSError) as exc:
        return _storage_failure(
            config["bucket"], storage_path, f"head_object:{exc.__class__.__name__}"
        )

    if should_upload:
        try:
            client.put_object(
                Bucket=config["bucket"],
                Key=storage_path,
                Body=image_bytes,
                ContentType=mime_type,
                CacheControl="public, max-age=31536000, immutable",
                Metadata={"checksum": checksum},
            )
        except ClientError as exc:
            response = exc.response if isinstance(exc.response, dict) else {}
            error_value = response.get("Error")
            error = error_value if isinstance(error_value, dict) else {}
            status_code = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
            error_code = str(error.get("Code") or status_code or exc.__class__.__name__)
            return _storage_failure(config["bucket"], storage_path, f"put_object:{error_code}")
        except (BotoCoreError, OSError) as exc:
            return _storage_failure(
                config["bucket"], storage_path, f"put_object:{exc.__class__.__name__}"
            )

    return {
        "status": "uploaded" if should_upload else "reused",
        "error": None,
        "bucket": config["bucket"],
        "storage_path": storage_path,
        "mime_type": mime_type,
    }


def _storage_failure(bucket: str, storage_path: str, error: str) -> dict[str, Any]:
    return {"status": "failed", "error": error, "bucket": bucket, "storage_path": storage_path}


def supabase_storage_config() -> dict[str, str] | None:
    return supabase_s3_config(bucket=supabase_storage_bucket())


def supabase_storage_bucket() -> str:
    return (
        os.getenv("SUPABASE_STORAGE_BUCKET", DEFAULT_SUPABASE_STORAGE_BUCKET).strip()
        or DEFAULT_SUPABASE_STORAGE_BUCKET
    )


def figure_storage_path(document: dict[str, Any], file_name: str) -> str:
    year = str(document.get("year") or _extract_year(file_name) or "unknown")
    report_slug = slugify(str(document.get("report_title") or Path(file_name).stem or "felgtbi"))
    section_slug = slugify(
        str(document.get("section_title") or document.get("specific_category") or "seccion")
    )
    figure_number = str(
        document.get("figure_number") or (document.get("figure") or {}).get("number") or ""
    )
    identity = "|".join(
        str(value or "")
        for value in (
            document.get("code"),
            document.get("page"),
            (document.get("figure") or {}).get("caption"),
            (document.get("visual_context") or {}).get("bbox"),
        )
    )
    identity_digest = hashlib.sha1(
        identity.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:10]
    stem = f"{figure_file_stem(figure_number)}-{identity_digest}"
    return f"{year}/{report_slug}/{section_slug}/{stem}.{FIGURE_IMAGE_EXTENSION}"


def figure_file_stem(figure_number: str) -> str:
    number = re.sub(r"[^0-9]+", "-", figure_number).strip("-")
    return f"figura-{number}" if number else "figura"


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "felgtbi"


def _extract_year(text: str) -> int | None:
    match = _YEAR_PATTERN.search(text or "")
    return int(match.group(1)) if match else None

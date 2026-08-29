from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from botocore.exceptions import BotoCoreError, ClientError

from app.infrastructure.storage import (
    DEFAULT_DIDACTIC_SLIDES_BUCKET,
    supabase_public_object_url,
    supabase_s3_client,
    supabase_s3_config,
)

logger = logging.getLogger(__name__)

ALLOWED_DIDACTIC_FILES = frozenset({".ppt", ".pptx", ".pdf"})
DIDACTIC_SLIDES_BUCKET = DEFAULT_DIDACTIC_SLIDES_BUCKET
SIGNED_URL_TTL_SECONDS = 900
MAX_LIST_PAGES = 20


class DidacticPresentationStorageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DidacticPresentation:
    name: str
    display_name: str
    storage_path: str
    extension: str
    file_type: str
    size: int | None
    updated_at: str | None
    download_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def didactic_slides_bucket() -> str:
    return (
        os.getenv("DIDACTIC_SLIDES_BUCKET", DIDACTIC_SLIDES_BUCKET).strip().strip("/")
        or DIDACTIC_SLIDES_BUCKET
    )


def list_didactic_presentations() -> tuple[DidacticPresentation, ...]:
    """List compatible presentation metadata without downloading object bodies."""
    bucket = didactic_slides_bucket()
    config = supabase_s3_config(bucket=bucket)
    if config is None:
        error = DidacticPresentationStorageError("supabase_storage_not_configured")
        logger.error(
            "didactic_slides_list_failed error_type=%s",
            error.__class__.__name__,
        )
        raise error
    client = supabase_s3_client(
        config["endpoint"], config["access_key"], config["secret_key"], config["region"]
    )
    try:
        objects = _list_objects(client, bucket)
        presentations = [
            presentation
            for item in objects
            if (presentation := _normalise_object(client, bucket, item)) is not None
        ]
    except (BotoCoreError, ClientError, OSError, RuntimeError, ValueError) as exc:
        logger.exception(
            "didactic_slides_list_failed error_type=%s",
            exc.__class__.__name__,
        )
        raise DidacticPresentationStorageError("didactic_slides_unavailable") from exc

    presentations.sort(key=lambda item: item.display_name.casefold())
    presentations.sort(key=_updated_timestamp, reverse=True)
    logger.info("didactic_slides_list_loaded count=%d", len(presentations))
    return tuple(presentations)


def _list_objects(client: Any, bucket: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    continuation_token: str | None = None
    for _page in range(MAX_LIST_PAGES):
        request: dict[str, Any] = {"Bucket": bucket, "MaxKeys": 1000}
        if continuation_token:
            request["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**request)
        contents = response.get("Contents") or []
        objects.extend(item for item in contents if isinstance(item, dict))
        if not response.get("IsTruncated"):
            return objects
        continuation_token = str(response.get("NextContinuationToken") or "").strip()
        if not continuation_token:
            raise DidacticPresentationStorageError("invalid_storage_pagination")
    raise DidacticPresentationStorageError("storage_pagination_limit")


def _normalise_object(
    client: Any,
    bucket: str,
    item: dict[str, Any],
) -> DidacticPresentation | None:
    storage_path = _clean_storage_path(item.get("Key"))
    if not storage_path or storage_path.endswith("/"):
        return None
    name = PurePosixPath(storage_path).name
    extension = PurePosixPath(name).suffix.casefold()
    if extension not in ALLOWED_DIDACTIC_FILES:
        return None
    public = _bucket_is_public()
    download_url = _download_url(client, bucket, storage_path, name, public=public)
    if not download_url:
        raise DidacticPresentationStorageError("download_url_unavailable")
    updated = item.get("LastModified")
    updated_at = _normalise_updated_at(updated)
    raw_size = item.get("Size")
    size = int(raw_size) if isinstance(raw_size, int | float) and raw_size >= 0 else None
    return DidacticPresentation(
        name=name,
        display_name=_display_name(name),
        storage_path=storage_path,
        extension=extension,
        file_type="PowerPoint" if extension in {".ppt", ".pptx"} else "PDF",
        size=size,
        updated_at=updated_at,
        download_url=download_url,
    )


def _download_url(
    client: Any,
    bucket: str,
    storage_path: str,
    filename: str,
    *,
    public: bool,
) -> str:
    if public:
        base_url = supabase_public_object_url(storage_path, bucket=bucket)
        url = f"{base_url}?download={quote(filename, safe='')}" if base_url else ""
        mode = "public"
    else:
        safe_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)[:180]
        url = str(
            client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": storage_path,
                    "ResponseContentDisposition": (
                        f'attachment; filename="{safe_filename}"'
                    ),
                },
                ExpiresIn=SIGNED_URL_TTL_SECONDS,
            )
            or ""
        )
        mode = "signed"
    logger.info(
        "didactic_slide_download_url_generated path_hash=%s mode=%s",
        _path_log_reference(storage_path),
        mode,
    )
    return url


def _bucket_is_public() -> bool:
    value = os.getenv("DIDACTIC_SLIDES_BUCKET_PUBLIC", "true").strip().casefold()
    return value in {"1", "true", "yes", "on"}


def _clean_storage_path(value: object) -> str:
    path = str(value or "").strip().replace("\\", "/").lstrip("/")
    if (
        not path
        or "://" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        return ""
    return path


def _display_name(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    readable = re.sub(r"[_-]+", " ", stem)
    readable = re.sub(r"\s+", " ", readable).strip()
    return readable[:1].upper() + readable[1:] if readable else stem


def _normalise_updated_at(value: object) -> str | None:
    if isinstance(value, datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value).astimezone(UTC).isoformat()
        except ValueError:
            return None
    return None


def _updated_timestamp(item: DidacticPresentation) -> float:
    if not item.updated_at:
        return float("-inf")
    return datetime.fromisoformat(item.updated_at).timestamp()


def _path_log_reference(storage_path: str) -> str:
    return hashlib.sha256(storage_path.encode("utf-8")).hexdigest()[:12]

from __future__ import annotations

import os
from urllib.parse import quote

DEFAULT_SUPABASE_STORAGE_BUCKET = "felgtbi-reports"


def supabase_public_image_url(storage_path: object, *, bucket: str | None = None) -> str:
    """Build a public Supabase Storage URL without persisting that derived value."""
    clean_path = _clean_storage_path(storage_path)
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    clean_bucket = str(
        bucket
        or os.getenv("SUPABASE_STORAGE_BUCKET", DEFAULT_SUPABASE_STORAGE_BUCKET)
    ).strip().strip("/")
    if not clean_path or not supabase_url or not clean_bucket:
        return ""
    return (
        f"{supabase_url}/storage/v1/object/public/"
        f"{quote(clean_bucket, safe='')}/{quote(clean_path, safe='/')}"
    )


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

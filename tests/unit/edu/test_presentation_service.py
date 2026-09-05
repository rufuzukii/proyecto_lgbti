from __future__ import annotations

from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError

from app.modules.didactics import presentation_service


class StorageClient:
    def __init__(self, pages: list[dict] | None = None):
        self.pages = pages or []
        self.list_calls: list[dict] = []
        self.signed_calls: list[tuple[str, dict, int]] = []

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.pages.pop(0)

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        self.signed_calls.append((operation, Params, ExpiresIn))
        return "https://signed.example/download"


def _configure(monkeypatch, client: StorageClient) -> None:
    monkeypatch.setattr(
        presentation_service,
        "supabase_s3_config",
        lambda **_kwargs: {
            "bucket": "slideshow-didactics",
            "endpoint": "https://storage.example",
            "access_key": "access",
            "secret_key": "secret",
            "region": "eu-west-1",
        },
    )
    monkeypatch.setattr(presentation_service, "supabase_s3_client", lambda *_args: client)
    monkeypatch.setattr(
        presentation_service,
        "supabase_public_object_url",
        lambda path, *, bucket: f"https://public.example/{bucket}/{path}",
    )
    monkeypatch.setenv("DIDACTIC_SLIDES_BUCKET_PUBLIC", "true")


def test_lists_supported_root_and_nested_files_and_ignores_other_formats(monkeypatch) -> None:
    client = StorageClient(
        [
            {
                "Contents": [
                    {
                        "Key": "es/introduccion_colectivo_lgbtiq_2026.pptx",
                        "Size": 2_515_000,
                        "LastModified": datetime(2026, 8, 15, tzinfo=UTC),
                    },
                    {
                        "Key": "guia-docente.pdf",
                        "Size": 860_000,
                        "LastModified": datetime(2026, 6, 1, tzinfo=UTC),
                    },
                    {"Key": "legacy.ppt", "Size": 1000},
                    {"Key": "debug.json", "Size": 200},
                    {"Key": "tema/.DS_Store", "Size": 100},
                    {"Key": "es/", "Size": 0},
                ],
                "IsTruncated": False,
            }
        ]
    )
    _configure(monkeypatch, client)

    result = presentation_service.list_didactic_presentations()

    assert [item.extension for item in result] == [".pptx", ".pdf", ".ppt"]
    assert result[0].storage_path == "es/introduccion_colectivo_lgbtiq_2026.pptx"
    assert result[0].display_name == "Introduccion colectivo lgbtiq 2026"
    assert result[0].file_type == "PowerPoint"
    assert result[1].file_type == "PDF"
    assert result[0].download_url.endswith("?download=introduccion_colectivo_lgbtiq_2026.pptx")
    assert client.list_calls == [{"Bucket": "slideshow-didactics", "MaxKeys": 1000}]


def test_empty_bucket_returns_empty_ready_catalog(monkeypatch) -> None:
    client = StorageClient([{"Contents": [], "IsTruncated": False}])
    _configure(monkeypatch, client)

    assert presentation_service.list_didactic_presentations() == ()


def test_storage_failure_is_wrapped_without_credentials(monkeypatch) -> None:
    error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "ListObjectsV2",
    )

    class BrokenClient(StorageClient):
        def list_objects_v2(self, **kwargs):
            raise error

    _configure(monkeypatch, BrokenClient())

    with pytest.raises(
        presentation_service.DidacticPresentationStorageError,
        match="didactic_slides_unavailable",
    ):
        presentation_service.list_didactic_presentations()


def test_private_bucket_uses_short_lived_signed_url_without_changing_path(monkeypatch) -> None:
    client = StorageClient(
        [
            {
                "Contents": [{"Key": "en/topic/deck.pptx", "Size": 512}],
                "IsTruncated": False,
            }
        ]
    )
    _configure(monkeypatch, client)
    monkeypatch.setenv("DIDACTIC_SLIDES_BUCKET_PUBLIC", "false")

    result = presentation_service.list_didactic_presentations()

    assert result[0].storage_path == "en/topic/deck.pptx"
    assert result[0].download_url == "https://signed.example/download"
    operation, params, expires = client.signed_calls[0]
    assert operation == "get_object"
    assert params["Bucket"] == "slideshow-didactics"
    assert params["Key"] == "en/topic/deck.pptx"
    assert expires == presentation_service.SIGNED_URL_TTL_SECONDS


@pytest.mark.parametrize(
    "unsafe_path", ["../secret.pdf", "folder/../secret.pdf", "https://x/a.pdf"]
)
def test_unsafe_storage_paths_are_not_exposed(monkeypatch, unsafe_path) -> None:
    client = StorageClient(
        [{"Contents": [{"Key": unsafe_path, "Size": 100}], "IsTruncated": False}]
    )
    _configure(monkeypatch, client)

    assert presentation_service.list_didactic_presentations() == ()

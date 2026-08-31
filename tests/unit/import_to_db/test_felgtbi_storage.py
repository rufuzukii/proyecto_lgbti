from __future__ import annotations

from botocore.exceptions import ClientError

from app.modules.imports.felgtbi import storage


class _Client:
    def __init__(self, *, head=None, head_error: Exception | None = None, put_error=None) -> None:
        self.head = head
        self.head_error = head_error
        self.put_error = put_error
        self.put_calls: list[dict] = []

    def head_object(self, **_kwargs):
        if self.head_error:
            raise self.head_error
        return self.head or {}

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        if self.put_error:
            raise self.put_error


def _client_error(status: int, code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "HeadObject",
    )


def _upload(monkeypatch, client: _Client):
    monkeypatch.setattr(
        storage,
        "supabase_storage_config",
        lambda: {
            "bucket": "figures",
            "endpoint": "https://storage.example.test",
            "access_key": "key",
            "secret_key": "secret",
            "region": "eu-test-1",
        },
    )
    monkeypatch.setattr(storage, "supabase_s3_client", lambda *_args: client)
    return storage.upload_figure_to_supabase(
        image_bytes=b"image",
        storage_path="2026/report/figure.webp",
        mime_type="image/webp",
        checksum="abc",
    )


def test_storage_reports_missing_configuration(monkeypatch) -> None:
    monkeypatch.setattr(storage, "supabase_storage_config", lambda: None)
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", " custom ")

    result = storage.upload_figure_to_supabase(
        image_bytes=b"x", storage_path="x.webp", mime_type="image/webp", checksum="abc"
    )

    assert result == {
        "status": "failed",
        "error": "supabase_storage_not_configured",
        "bucket": "custom",
        "storage_path": "x.webp",
    }


def test_storage_reuses_matching_checksum(monkeypatch) -> None:
    client = _Client(head={"Metadata": {"checksum": "abc"}})

    result = _upload(monkeypatch, client)

    assert result["status"] == "reused"
    assert client.put_calls == []


def test_storage_uploads_after_not_found(monkeypatch) -> None:
    client = _Client(head_error=_client_error(404, "NoSuchKey"))

    result = _upload(monkeypatch, client)

    assert result["status"] == "uploaded"
    assert client.put_calls[0]["Metadata"] == {"checksum": "abc"}


def test_storage_maps_head_and_put_failures(monkeypatch) -> None:
    head_failure = _upload(monkeypatch, _Client(head_error=_client_error(503, "SlowDown")))
    os_failure = _upload(monkeypatch, _Client(head_error=OSError("offline")))
    put_failure = _upload(
        monkeypatch,
        _Client(
            head_error=_client_error(404, "NotFound"),
            put_error=_client_error(403, "AccessDenied"),
        ),
    )

    assert head_failure["error"] == "head_object:SlowDown"
    assert os_failure["error"] == "head_object:OSError"
    assert put_failure["error"] == "put_object:AccessDenied"


def test_storage_path_handles_metadata_fallbacks_and_slugging(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "   ")
    document = {
        "specific_category": "Atención / Salud",
        "page": 3,
        "figure": {"number": "A.2", "caption": "Distribución"},
        "visual_context": {"bbox": [1, 2, 3, 4]},
    }

    path = storage.figure_storage_path(document, "Informe 2025.pdf")

    assert path.startswith("2025/informe-2025/atencion-salud/figura-2-")
    assert path.endswith(".webp")
    assert storage.supabase_storage_bucket() == storage.DEFAULT_SUPABASE_STORAGE_BUCKET
    assert storage.slugify("---") == "felgtbi"
    assert storage.figure_file_stem("") == "figura"

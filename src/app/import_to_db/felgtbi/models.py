from __future__ import annotations


class PdfExtractionError(RuntimeError):
    """The PDF cannot be processed safely or within configured limits."""


class StorageUploadError(RuntimeError):
    """A required figure could not be persisted in object storage."""

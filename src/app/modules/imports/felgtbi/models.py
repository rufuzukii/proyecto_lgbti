from __future__ import annotations


class PdfExtractionError(RuntimeError):
    """El PDF no puede procesarse con seguridad o dentro de los límites configurados."""


class StorageUploadError(RuntimeError):
    """No se ha podido guardar una figura necesaria en el almacenamiento de objetos."""

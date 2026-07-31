from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportErrorInfo:
    title: str
    details: list[str]


class ImportErrorHandler:
    """Classifies import failures into safe, user-facing messages."""

    @classmethod
    def describe_import_log_error(cls, exc: Exception) -> ImportErrorInfo:
        error_text = cls.sanitize_error_text(str(exc))
        normalized = error_text.lower()

        if "failed to resolve host" in normalized or "getaddrinfo failed" in normalized:
            return cls._dns_error(error_text)

        if "connection refused" in normalized:
            return ImportErrorInfo(
                title="No ha sido posible guardar el archivo para revisión.",
                details=[
                    "El archivo se ha leído correctamente, pero no se ha podido completar la operación.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        if "timeout" in normalized or "timed out" in normalized:
            return ImportErrorInfo(
                title="La operación ha tardado demasiado.",
                details=[
                    "El archivo se ha leído correctamente, pero no se ha podido guardar para revisión.",
                    "Inténtalo de nuevo en unos minutos.",
                ],
            )

        if "password authentication failed" in normalized:
            return ImportErrorInfo(
                title="No ha sido posible guardar el archivo para revisión.",
                details=[
                    "El archivo no se ha guardado.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        if "database" in normalized and "does not exist" in normalized:
            return ImportErrorInfo(
                title="La revisión de archivos no está disponible en este momento.",
                details=[
                    "El archivo se ha leído correctamente, pero no se ha podido guardar para revisión.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        if "database_url must be set" in normalized:
            return ImportErrorInfo(
                title="La revisión de archivos no está disponible en este momento.",
                details=[
                    "El archivo no se ha podido guardar para revisión.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        if "file_json" in normalized and (
            "does not exist" in normalized or "undefinedcolumn" in normalized
        ):
            return ImportErrorInfo(
                title="La revisión de archivos no está disponible en este momento.",
                details=[
                    "El archivo se ha leído correctamente, pero no se ha podido guardar para revisión.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        if 'relation "import_logs" does not exist' in normalized:
            return ImportErrorInfo(
                title="La revisión de archivos no está disponible en este momento.",
                details=[
                    "El archivo se ha leído correctamente, pero no se ha podido guardar para revisión.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        if "violates check constraint" in normalized and "status" in normalized:
            return ImportErrorInfo(
                title="No ha sido posible guardar el archivo para revisión.",
                details=[
                    "El archivo se ha leído correctamente, pero no se ha podido completar la operación.",
                    "Inténtalo de nuevo más tarde.",
                ],
            )

        return ImportErrorInfo(
            title="No ha sido posible guardar el archivo para revisión.",
            details=[
                "El archivo puede haberse leído correctamente, pero no se ha podido completar la operación.",
                "Inténtalo de nuevo más tarde.",
            ],
        )

    @classmethod
    def _dns_error(cls, error_text: str) -> ImportErrorInfo:
        host = cls.extract_failed_host(error_text)
        details = [
            "El archivo se ha leído correctamente, pero no se ha podido guardar para revisión.",
            "Comprueba tu conexión e inténtalo de nuevo.",
        ]
        if host:
            details.append("El servicio no está disponible temporalmente.")
        return ImportErrorInfo(
            title="No ha sido posible guardar el archivo para revisión.",
            details=details,
        )

    @staticmethod
    def extract_failed_host(error_text: str) -> str | None:
        match = re.search(r"host '([^']+)'", error_text)
        return match.group(1) if match else None

    @staticmethod
    def sanitize_error_text(error_text: str) -> str:
        return re.sub(
            r"(postgres(?:ql)?://[^:/\s]+:)([^@\s]+)(@)",
            r"\1***\3",
            error_text,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def truncate_text(text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text
        return f"{text[: max_length - 3]}..."

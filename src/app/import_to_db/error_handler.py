from __future__ import annotations

from dataclasses import dataclass
import re


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
                title="The import service is not accepting connections.",
                details=[
                    "Your file was read, but the page could not save it for review.",
                    "Please try again later. If the problem continues, contact the site administrator.",
                ],
            )

        if "timeout" in normalized or "timed out" in normalized:
            return ImportErrorInfo(
                title="The import service took too long to respond.",
                details=[
                    "Your file was read, but saving it for review timed out.",
                    "Please try again in a few minutes.",
                ],
            )

        if "password authentication failed" in normalized:
            return ImportErrorInfo(
                title="The import service could not verify the connection.",
                details=[
                    "Your file was not saved for review.",
                    "Please contact the site administrator if this keeps happening.",
                ],
            )

        if "database" in normalized and "does not exist" in normalized:
            return ImportErrorInfo(
                title="The import service is not ready.",
                details=[
                    "Your file was read, but the page could not find the storage area used for imports.",
                    "Please contact the site administrator.",
                ],
            )

        if "database_url must be set" in normalized:
            return ImportErrorInfo(
                title="The import service is not configured.",
                details=[
                    "Your file could not be saved for review because the page is missing its import storage connection.",
                    "Please contact the site administrator.",
                ],
            )

        if "file_json" in normalized and (
            "does not exist" in normalized or "undefinedcolumn" in normalized
        ):
            return ImportErrorInfo(
                title="The review queue is not ready.",
                details=[
                    "Your file was read, but the page could not save the generated JSON for review.",
                    "Please contact the site administrator.",
                ],
            )

        if 'relation "import_logs" does not exist' in normalized:
            return ImportErrorInfo(
                title="The review queue is not available.",
                details=[
                    "Your file was read, but the page could not add it to the review queue.",
                    "Please contact the site administrator.",
                ],
            )

        if "violates check constraint" in normalized and "status" in normalized:
            return ImportErrorInfo(
                title="The review queue rejected the import status.",
                details=[
                    "Your file was read, but the page could not mark it as waiting for review.",
                    "Please contact the site administrator.",
                ],
            )

        return ImportErrorInfo(
            title="The import could not be saved for review.",
            details=[
                "Your file may have been read, but the page could not finish saving the import.",
                "Please try again. If the problem continues, contact the site administrator.",
            ],
        )

    @classmethod
    def _dns_error(cls, error_text: str) -> ImportErrorInfo:
        host = cls.extract_failed_host(error_text)
        details = [
            "Your file was read, but the page could not reach the import storage service.",
            "Please check your internet connection and try again.",
        ]
        if host:
            details.append(f"The unavailable service was: {host}.")
        return ImportErrorInfo(
            title="The import service could not be reached.",
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

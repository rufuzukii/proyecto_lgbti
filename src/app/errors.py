from __future__ import annotations


class DatabaseUnavailableError(RuntimeError):
    status_code = 503

    def __init__(self, service: str = "database") -> None:
        self.service = service
        super().__init__(f"{service} is unavailable")

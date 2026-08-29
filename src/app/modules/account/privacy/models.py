from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class PersonalDataInventory:
    """Counts of records that are actually linked to one application user."""

    profile: bool
    account_security: int = 0
    teacher_games: int = 0
    import_logs: int = 0
    security_audit_events: int = 0
    admin_audit_events: int = 0
    supabase_objects: int = 0
    persisted_reports: int = 0

    @property
    def removable_content_count(self) -> int:
        return self.teacher_games + self.import_logs

    def to_safe_dict(self) -> dict[str, int | bool]:
        return {
            "profile": self.profile,
            "account_security": self.account_security,
            "teacher_games": self.teacher_games,
            "import_logs": self.import_logs,
            "security_audit_events": self.security_audit_events,
            "admin_audit_events": self.admin_audit_events,
            "supabase_objects": self.supabase_objects,
            "persisted_reports": self.persisted_reports,
        }


@dataclass(frozen=True, slots=True)
class DeletionOutcome:
    status: Literal["completed", "already_deleted"]
    deleted: dict[str, int] = field(default_factory=dict)
    anonymized: dict[str, int] = field(default_factory=dict)
    retained: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeletionStageResult:
    deleted: dict[str, int] = field(default_factory=dict)
    anonymized: dict[str, int] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

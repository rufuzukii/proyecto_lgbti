from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class LocalizedText:
    es: str
    en: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> LocalizedText:
        return cls(es=str(value.get("es", "")), en=str(value.get("en", "")))

    def get(self, language: str) -> str:
        return self.en if language == "en" else self.es


@dataclass(frozen=True)
class GlossarySource:
    name: str
    url: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> GlossarySource:
        return cls(name=str(value.get("name", "")).strip(), url=str(value.get("url", "")).strip())


@dataclass(frozen=True)
class GlossaryTerm:
    id: str
    term: str
    definition: str
    category: str
    sources: tuple[GlossarySource, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> GlossaryTerm:
        return cls(
            id=str(value["id"]).strip(),
            term=str(value["term"]).strip(),
            definition=str(value["definition"]).strip(),
            category=str(value["category"]).strip(),
            sources=tuple(GlossarySource.from_mapping(item) for item in value.get("sources", [])),
        )


@dataclass(frozen=True)
class TeacherResource:
    id: str
    title: LocalizedText
    description: LocalizedText
    level: LocalizedText
    duration_minutes: int
    objectives: tuple[LocalizedText, ...]
    topic: LocalizedText
    instructions: LocalizedText
    materials: tuple[LocalizedText, ...]
    teacher_guide: LocalizedText
    languages: tuple[str, ...]
    formats: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> TeacherResource:
        return cls(
            id=str(value["id"]),
            title=LocalizedText.from_mapping(value["title"]),
            description=LocalizedText.from_mapping(value["description"]),
            level=LocalizedText.from_mapping(value["level"]),
            duration_minutes=int(value["duration_minutes"]),
            objectives=tuple(LocalizedText.from_mapping(item) for item in value["objectives"]),
            topic=LocalizedText.from_mapping(value["topic"]),
            instructions=LocalizedText.from_mapping(value["instructions"]),
            materials=tuple(LocalizedText.from_mapping(item) for item in value["materials"]),
            teacher_guide=LocalizedText.from_mapping(value["teacher_guide"]),
            languages=tuple(value.get("languages", ["es", "en"])),
            formats=tuple(value.get("formats", ["pdf"])),
        )


class EducationalActivityStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class EducationalActivity:
    activity_id: str
    owner_user_id: str
    game_type: str
    title: str
    description: str
    instructions: str
    teacher_note: str
    language: str
    configuration: dict[str, Any]
    status: EducationalActivityStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> EducationalActivity:
        return cls(
            activity_id=str(value["id"]),
            owner_user_id=str(value["owner_user_id"]),
            game_type=str(value["game_type"]),
            title=str(value["title"]),
            description=str(value.get("description") or ""),
            instructions=str(value.get("instructions") or ""),
            teacher_note=str(value.get("teacher_note") or ""),
            language=str(value.get("language") or "es"),
            configuration=dict(value.get("configuration") or {}),
            status=EducationalActivityStatus(str(value.get("status") or "DRAFT")),
            created_at=value["created_at"],
            updated_at=value["updated_at"],
        )

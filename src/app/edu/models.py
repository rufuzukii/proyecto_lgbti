from __future__ import annotations

from dataclasses import dataclass
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
class GlossaryTerm:
    id: str
    term: LocalizedText
    short_definition: LocalizedText
    definition: LocalizedText
    category: str
    related_terms: tuple[str, ...]
    source: str
    source_url: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> GlossaryTerm:
        return cls(
            id=str(value["id"]),
            term=LocalizedText.from_mapping(value["term"]),
            short_definition=LocalizedText.from_mapping(value["short_definition"]),
            definition=LocalizedText.from_mapping(value["definition"]),
            category=str(value["category"]),
            related_terms=tuple(str(item) for item in value.get("related_terms", [])),
            source=str(value.get("source", "")),
            source_url=str(value.get("source_url", "")),
        )


@dataclass(frozen=True)
class Lesson:
    id: str
    title: LocalizedText
    description: LocalizedText
    objectives: tuple[LocalizedText, ...]
    level: LocalizedText
    duration_minutes: int
    slides: tuple[dict[str, Any], ...]
    activity: dict[str, Any]
    sources: tuple[dict[str, str], ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Lesson:
        return cls(
            id=str(value["id"]),
            title=LocalizedText.from_mapping(value["title"]),
            description=LocalizedText.from_mapping(value["description"]),
            objectives=tuple(LocalizedText.from_mapping(item) for item in value["objectives"]),
            level=LocalizedText.from_mapping(value["level"]),
            duration_minutes=int(value["duration_minutes"]),
            slides=tuple(value["slides"]),
            activity=value["activity"],
            sources=tuple(value.get("sources", [])),
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

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.reports import resource_usage


def test_read_memory_prefers_container_usage_and_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = tmp_path / "memory.current"
    limit = tmp_path / "memory.max"
    current.write_text(str(384 * 1024 * 1024), encoding="ascii")
    limit.write_text(str(510 * 1024 * 1024), encoding="ascii")
    monkeypatch.setattr(
        resource_usage,
        "_CGROUP_CURRENT_PATHS",
        ((current, "test_cgroup"),),
    )
    monkeypatch.setattr(resource_usage, "_CGROUP_LIMIT_PATHS", (limit,))

    reading = resource_usage.read_memory()

    assert reading.total_mb == 384.0
    assert reading.limit_mb == 510.0
    assert reading.source == "test_cgroup"


def test_sampler_retains_the_highest_observed_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings = iter(
        [
            resource_usage.MemoryReading(220.0, 150.0, 510.0, "test"),
            resource_usage.MemoryReading(405.0, 170.0, 510.0, "test"),
            resource_usage.MemoryReading(260.0, 155.0, 510.0, "test"),
        ]
    )
    monkeypatch.setattr(resource_usage, "read_memory", lambda: next(readings))
    sampler = resource_usage.ReportMemorySampler()

    sampler.sample()
    sampler.sample()
    sampler.sample()

    assert sampler.peak_mb == 405.0

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

_CGROUP_CURRENT_PATHS = (
    (Path("/sys/fs/cgroup/memory.current"), "cgroup_v2"),
    (Path("/sys/fs/cgroup/memory/memory.usage_in_bytes"), "cgroup_v1"),
)
_CGROUP_LIMIT_PATHS = (
    Path("/sys/fs/cgroup/memory.max"),
    Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
)


@dataclass(frozen=True, slots=True)
class MemoryReading:
    total_mb: float | None
    python_mb: float | None
    limit_mb: float | None
    source: str


class ReportMemorySampler:
    def __init__(self, interval_seconds: float = 0.1) -> None:
        self.interval_seconds = interval_seconds
        self.peak_mb: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> MemoryReading:
        reading = self.sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return reading

    def sample(self) -> MemoryReading:
        reading = read_memory()
        if reading.total_mb is not None:
            self.peak_mb = max(self.peak_mb or 0.0, reading.total_mb)
        return reading

    def stop(self) -> MemoryReading:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
            self._thread = None
        return self.sample()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.sample()


def read_memory() -> MemoryReading:
    python_bytes = _process_rss_bytes(os.getpid())
    limit_bytes = _first_memory_value(_CGROUP_LIMIT_PATHS)
    for path, source in _CGROUP_CURRENT_PATHS:
        total_bytes = _memory_value(path)
        if total_bytes is not None:
            return MemoryReading(
                _to_mb(total_bytes),
                _to_mb(python_bytes),
                _to_mb(limit_bytes),
                source,
            )
    tree_bytes = _process_tree_rss_bytes(os.getpid())
    return MemoryReading(
        _to_mb(tree_bytes),
        _to_mb(python_bytes),
        None,
        "proc_tree" if tree_bytes is not None else "unavailable",
    )


def _first_memory_value(paths: tuple[Path, ...]) -> int | None:
    return next(
        (value for path in paths if (value := _memory_value(path)) is not None),
        None,
    )


def _memory_value(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    if value == "max":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _process_tree_rss_bytes(root_pid: int) -> int | None:
    pending = [root_pid]
    visited: set[int] = set()
    total = 0
    found = False
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        rss = _process_rss_bytes(pid)
        if rss is not None:
            total += rss
            found = True
        pending.extend(_process_children(pid))
    return total if found else None


def _process_children(pid: int) -> list[int]:
    path = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        values = path.read_text(encoding="ascii").split()
    except OSError:
        return []
    return [int(value) for value in values if value.isdigit()]


def _process_rss_bytes(pid: int) -> int | None:
    path = Path(f"/proc/{pid}/status")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.startswith("VmRSS:"):
            continue
        parts = line.split()
        try:
            return int(parts[1]) * 1024
        except IndexError, ValueError:
            return None
    return None


def _to_mb(value: int | None) -> float | None:
    return round(value / (1024 * 1024), 1) if value is not None else None

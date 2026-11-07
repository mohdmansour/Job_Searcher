"""The contract every job source implements. Phase 2 sources (Bayt, ...) plug in here."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from jobcv.schemas import Job, SearchQuery


@dataclass
class SourceResult:
    jobs: list[Job]
    cost_usd: float  # what this fetch actually cost (reported by the provider)


class JobSource(Protocol):
    name: str

    def estimate_cost(self, q: SearchQuery, limit: int) -> float:
        """Worst-case cost of fetching `limit` jobs, before running."""
        ...

    def search(self, q: SearchQuery, limit: int, recent_only: bool = False) -> SourceResult:
        """Fetch up to `limit` jobs. `recent_only` = smallest date window the source supports."""
        ...


def utc_from_ms(ms: float | None) -> datetime | None:
    from datetime import UTC

    return datetime.fromtimestamp(ms / 1000, tz=UTC) if ms else None

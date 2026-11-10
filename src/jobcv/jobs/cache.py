"""Jobs-only cache + the search service that decides when to call the source.

The cache lives in its own SQLite file and stores PUBLIC job data only:
no CVs, no scores, no user ids.

Rules (SPEC "Cache"):
- key = normalized title + country + sorted cities + remote flag
- fresh (age < TTL) and enough jobs   -> serve from cache, no call
- fresh but fewer than N              -> one full fetch of N, merged with dedupe
  (the Actor has no offset, so asking for only the shortfall would just return the
  same top jobs again) -- unless the last full fetch already asked for >= N: then the
  market simply has fewer jobs, and fetching again would only burn money (seen live)
- expired                             -> incremental fetch (last 24h window), merged;
                                         a full fetch only if still short of N
- force_refresh                       -> full fetch even if fresh (billable, through the meter)
- jobs posted more than `job_max_age_days` ago are dropped, if that limit is set (default: off)
- at most 2 source calls per search; never a loop
"""

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from jobcv.config import Settings
from jobcv.jobs.dedupe import dedupe
from jobcv.schemas import Job, SearchQuery, SearchResult
from jobcv.sources.base import JobSource
from jobcv.text import normalize


class Meter(Protocol):
    def check(self, usd: float) -> None: ...  # raises if this spend would break the cap
    def add_apify(self, usd: float) -> None: ...


class _NoMeter:
    def check(self, usd: float) -> None:
        pass

    def add_apify(self, usd: float) -> None:
        pass


def cache_key(q: SearchQuery) -> str:
    cities = ",".join(sorted(normalize(c) for c in q.cities))
    titles = "+".join(sorted(normalize(t) for t in q.titles))
    return f"{titles}|{q.country.value}|{cities}|{int(q.remote)}"


class JobCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._db() as db:
            db.execute(
                "create table if not exists searches ("
                " key text primary key, last_updated text not null, jobs_json text not null,"
                " fetched_limit integer not null default 0)"
            )

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, key: str) -> tuple[datetime, list[Job], int] | None:
        with self._db() as db:
            row = db.execute(
                "select last_updated, jobs_json, fetched_limit from searches where key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        jobs = [Job.model_validate(j) for j in json.loads(row[1])]
        return datetime.fromisoformat(row[0]), jobs, row[2]

    def put(self, key: str, last_updated: datetime, jobs: list[Job], fetched_limit: int) -> None:
        """fetched_limit = the largest N a full fetch asked for since the last expiry."""
        payload = json.dumps([j.model_dump(mode="json") for j in jobs], ensure_ascii=False)
        with self._db() as db:
            db.execute(
                "insert into searches(key, last_updated, jobs_json, fetched_limit)"
                " values (?, ?, ?, ?) on conflict(key) do update set"
                " last_updated = excluded.last_updated, jobs_json = excluded.jobs_json,"
                " fetched_limit = excluded.fetched_limit",
                (key, last_updated.isoformat(), payload, fetched_limit),
            )


class JobSearchService:
    def __init__(
        self,
        source: JobSource,
        cache: JobCache,
        settings: Settings,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.source, self.cache, self.s, self.now = source, cache, settings, now

    def search(
        self, q: SearchQuery, meter: Meter | None = None, force_refresh: bool = False
    ) -> SearchResult:
        meter = meter or _NoMeter()
        now, n, key = self.now(), q.max_results, cache_key(q)
        entry = self.cache.get(key)
        last_updated, jobs, fetched_limit = entry if entry else (now, [], 0)
        jobs = self._drop_old(jobs, now)
        cost, fetched = 0.0, False

        def fetch(recent_only: bool) -> None:
            nonlocal jobs, cost, fetched, fetched_limit
            fetched = True
            if not recent_only:
                fetched_limit = max(fetched_limit, n)
            meter.check(self.source.estimate_cost(q, n))
            res = self.source.search(q, n, recent_only=recent_only)
            meter.add_apify(res.cost_usd)
            cost += res.cost_usd
            jobs = dedupe(self._drop_old(res.jobs, now) + jobs)

        expired = entry is not None and now - last_updated >= timedelta(
            hours=self.s.job_cache_ttl_hours
        )
        if entry is None or force_refresh:
            fetch(recent_only=False)
        elif expired:
            fetched_limit = 0  # a new period: the market may have grown
            fetch(recent_only=True)
            if len(jobs) < n:
                fetch(recent_only=False)
        elif len(jobs) < n and fetched_limit < n:
            fetch(recent_only=False)

        jobs = self._newest_first(jobs)
        if fetched:
            last_updated = now
            self.cache.put(key, last_updated, jobs, fetched_limit)
        return SearchResult(
            jobs=jobs[:n], last_updated=last_updated, from_cache=not fetched, apify_cost_usd=cost
        )

    def _drop_old(self, jobs: list[Job], now: datetime) -> list[Job]:
        if self.s.job_max_age_days is None:
            return jobs
        limit = now - timedelta(days=self.s.job_max_age_days)
        return [j for j in jobs if (j.posted_at or j.fetched_at) >= limit]

    @staticmethod
    def _newest_first(jobs: list[Job]) -> list[Job]:
        epoch = datetime.min.replace(tzinfo=UTC)
        return sorted(jobs, key=lambda j: j.posted_at or epoch, reverse=True)

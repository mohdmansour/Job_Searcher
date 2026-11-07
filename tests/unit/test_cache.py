from datetime import UTC, datetime, timedelta

import pytest

from jobcv.config import Settings
from jobcv.jobs.cache import JobCache, JobSearchService, cache_key
from jobcv.schemas import Country, Job, SearchQuery
from jobcv.sources.base import SourceResult

T0 = datetime(2026, 11, 8, 12, tzinfo=UTC)


def job(n, posted_days_ago=1, now=T0):
    return Job(id=f"linkedin:{n}", source="linkedin", title=f"Role {n}", company=f"Co {n}",
               location="Dubai, United Arab Emirates", remote=False, description=f"desc {n}",
               url=f"https://www.linkedin.com/jobs/view/{n}",
               posted_at=now - timedelta(days=posted_days_ago), fetched_at=now, language="en")


class FakeSource:
    name = "linkedin"

    def __init__(self, batches):
        self.batches = list(batches)  # one list of jobs per call
        self.calls = []

    def estimate_cost(self, q, limit):
        return 0.0015 * limit

    def search(self, q, limit, recent_only=False):
        self.calls.append({"limit": limit, "recent_only": recent_only})
        return SourceResult(jobs=self.batches.pop(0)[:limit], cost_usd=0.0015 * limit)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path)


def service(settings, source, clock):
    return JobSearchService(source, JobCache(settings.jobs_cache_db), settings, now=clock)


Q = SearchQuery(title="QA Engineer", country=Country.UAE, cities=["Dubai"], max_results=3)


def test_cache_key_is_normalized():
    a = SearchQuery(title="  QA engineer ", country=Country.UAE, cities=["dubai", "Abu Dhabi"])
    b = SearchQuery(title="qa ENGINEER", country=Country.UAE, cities=["Abu Dhabi", "Dubai"])
    assert cache_key(a) == cache_key(b)
    assert cache_key(a) != cache_key(b.model_copy(update={"remote": True}))


def test_miss_fetches_and_stores(settings):
    src, clock = FakeSource([[job(1), job(2), job(3)]]), Clock(T0)
    res = service(settings, src, clock).search(Q)
    assert [j.id for j in res.jobs] == ["linkedin:1", "linkedin:2", "linkedin:3"]
    assert res.from_cache is False and res.last_updated == T0
    assert src.calls == [{"limit": 3, "recent_only": False}]


def test_hit_within_ttl_makes_no_call(settings):
    src, clock = FakeSource([[job(1), job(2), job(3)]]), Clock(T0)
    service(settings, src, clock).search(Q)
    clock.t = T0 + timedelta(hours=3, minutes=59)
    res = service(settings, src, clock).search(Q)
    assert res.from_cache is True and len(src.calls) == 1
    assert res.last_updated == T0  # "updated X hours ago" comes from here


def test_hit_returns_first_n_when_cache_has_more(settings):
    src, clock = FakeSource([[job(i) for i in range(1, 6)]]), Clock(T0)
    service(settings, src, clock).search(Q.model_copy(update={"max_results": 5}))
    res = service(settings, src, clock).search(Q.model_copy(update={"max_results": 2}))
    assert [j.id for j in res.jobs] == ["linkedin:1", "linkedin:2"] and len(src.calls) == 1


def test_shortfall_fetches_more_and_merges(settings):
    src = FakeSource([[job(1), job(2)], [job(1), job(2), job(3), job(4)]])
    clock = Clock(T0)
    service(settings, src, clock).search(Q.model_copy(update={"max_results": 2}))
    res = service(settings, src, clock).search(Q.model_copy(update={"max_results": 4}))
    assert len(res.jobs) == 4 and len(src.calls) == 2
    assert src.calls[1] == {"limit": 4, "recent_only": False}


def test_expired_entry_does_incremental_refresh_and_merges(settings):
    src = FakeSource([[job(1), job(2), job(3)], [job(9, posted_days_ago=0), job(1)]])
    clock = Clock(T0)
    service(settings, src, clock).search(Q)
    clock.t = T0 + timedelta(hours=4, minutes=1)
    res = service(settings, src, clock).search(Q)
    assert src.calls[1] == {"limit": 3, "recent_only": True}
    assert res.jobs[0].id == "linkedin:9"  # newest first
    assert len({j.id for j in res.jobs}) == len(res.jobs)  # deduped
    assert res.last_updated == clock.t and res.from_cache is False


def test_jobs_older_than_30_days_are_ignored(settings):
    src = FakeSource([[job(1, posted_days_ago=31), job(2), job(3)], [job(4)]])
    res = service(settings, src, Clock(T0)).search(Q)
    assert "linkedin:1" not in [j.id for j in res.jobs]


def test_force_refresh_bypasses_fresh_cache(settings):
    src = FakeSource([[job(1), job(2), job(3)], [job(7), job(8), job(9)]])
    clock = Clock(T0)
    service(settings, src, clock).search(Q)
    res = service(settings, src, clock).search(Q, force_refresh=True)
    assert len(src.calls) == 2 and src.calls[1]["recent_only"] is False
    assert res.from_cache is False


def test_ttl_is_configurable(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path, job_cache_ttl_hours=1)
    src, clock = FakeSource([[job(1), job(2), job(3)], [job(4)]]), Clock(T0)
    service(s, src, clock).search(Q)
    clock.t = T0 + timedelta(minutes=61)
    service(s, src, clock).search(Q)
    assert src.calls[1]["recent_only"] is True


def test_fetch_goes_through_meter_and_cost_is_reported(settings):
    checked, recorded = [], []

    class Meter:
        def check(self, usd):
            checked.append(usd)

        def add_apify(self, usd):
            recorded.append(usd)

    src = FakeSource([[job(1), job(2), job(3)]])
    res = service(settings, src, Clock(T0)).search(Q, meter=Meter())
    assert checked == [pytest.approx(0.0045)] and recorded == [pytest.approx(0.0045)]
    assert res.apify_cost_usd == pytest.approx(0.0045)


def test_cache_db_holds_only_job_tables(settings):
    import sqlite3

    service(settings, FakeSource([[job(1)]]), Clock(T0)).search(Q)
    tables = {r[0] for r in sqlite3.connect(settings.jobs_cache_db).execute(
        "select name from sqlite_master where type='table'")}
    assert tables == {"searches"}


def test_no_refetch_when_market_simply_has_fewer_jobs(settings):
    # seen live: Jordan had only 3 usable jobs for N=5 -> every search re-paid Apify
    src = FakeSource([[job(1), job(2), job(3)], [job(4)]])
    clock = Clock(T0)
    five = Q.model_copy(update={"max_results": 5})
    service(settings, src, clock).search(five)
    res = service(settings, src, clock).search(five)
    assert len(src.calls) == 1 and res.from_cache is True and len(res.jobs) == 3


def test_asking_for_more_than_last_fetch_still_fetches(settings):
    src = FakeSource([[job(1), job(2)], [job(1), job(2), job(3)]])
    clock = Clock(T0)
    service(settings, src, clock).search(Q.model_copy(update={"max_results": 2}))
    service(settings, src, clock).search(Q.model_copy(update={"max_results": 5}))
    assert len(src.calls) == 2

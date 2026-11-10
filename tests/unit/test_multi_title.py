from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jobcv.config import Settings
from jobcv.jobs.cache import JobCache, JobSearchService, cache_key
from jobcv.schemas import Country, Job, SearchQuery
from jobcv.sources.base import SourceResult
from jobcv.sources.linkedin_apify import build_input
from tests.unit.test_api import client, upload  # noqa: F401

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def query(**kw) -> SearchQuery:
    return SearchQuery(**{"title": "QA Engineer", "country": Country("Jordan"), "max_results": 10, **kw})


def job(i: int, age_days: int) -> Job:
    return Job(id=f"t:{i}", source="t", title=f"Job {i}", company=f"C{i}", location="Amman", remote=False,
               description="d", url=f"https://x/{i}", posted_at=NOW - timedelta(days=age_days), fetched_at=NOW)


class Source:
    name = "t"

    def __init__(self, jobs):
        self.jobs = jobs

    def estimate_cost(self, q, limit):
        return 0.01

    def search(self, q, limit, recent_only=False):
        return SourceResult(jobs=self.jobs, cost_usd=0.01)


def service(tmp_path, jobs, **settings):
    s = Settings(_env_file=None, data_dir=tmp_path, **settings)
    return JobSearchService(Source(jobs), JobCache(tmp_path / "c.db"), s, now=lambda: NOW)


# ---- age ----
def test_old_jobs_are_shown_by_default(tmp_path):
    jobs = [job(1, 1), job(2, 90), job(3, 400)]
    assert len(service(tmp_path, jobs).search(query()).jobs) == 3


def test_an_age_limit_can_still_be_configured(tmp_path):
    jobs = [job(1, 1), job(2, 90)]
    found = service(tmp_path, jobs, job_max_age_days=30).search(query()).jobs
    assert [j.id for j in found] == ["t:1"]


# ---- several titles ----
def test_titles_keep_the_main_one_first_and_drop_repeats():
    q = query(more_titles=[" Software Tester ", "qa engineer"])
    assert q.titles == ["QA Engineer", "Software Tester"]


def test_at_most_two_extra_titles():
    with pytest.raises(ValidationError):
        query(more_titles=["a", "b", "c"])


def test_one_title_is_unchanged():
    run = build_input(query(), 10, None)
    assert run["titles"] == ["QA Engineer"] and run["rows"] == 10
    assert cache_key(query()) == "qa engineer|Jordan||0"


def test_results_are_shared_across_titles_and_rounded_up():
    run = build_input(query(more_titles=["Software Tester", "QC Engineer"]), 10, None)
    assert run["titles"] == ["QA Engineer", "Software Tester", "QC Engineer"]
    assert run["rows"] == 4


def test_titles_and_cities_multiply_the_searches():
    run = build_input(query(more_titles=["Tester"], cities=["Amman", "Irbid"]), 10, None)
    assert run["rows"] == 3


def test_extra_titles_get_their_own_cache_entry_in_any_order():
    one = cache_key(query(more_titles=["Tester", "QC"]))
    two = cache_key(query(more_titles=["QC", "Tester"]))
    assert one == two != cache_key(query())


def test_api_accepts_extra_titles(client):  # noqa: F811
    cv_id = upload(client).json()["cv_id"]
    r = client.post("/search", json={"cv_id": cv_id, "title": "QA", "more_titles": ["Tester"],
                                     "country": "United Arab Emirates", "max_results": 3})
    assert r.status_code == 202


def test_api_refuses_too_many_titles(client):  # noqa: F811
    r = client.post("/search", json={"cv_id": "x", "title": "QA", "more_titles": ["a", "b", "c"],
                                     "country": "Germany"})
    assert r.status_code == 422

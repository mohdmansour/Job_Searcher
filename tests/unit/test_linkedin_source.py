from datetime import UTC, datetime

from jobcv.config import Settings
from jobcv.schemas import Country, SearchQuery
from jobcv.sources.linkedin_apify import LinkedInApifySource, build_input, map_item

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def item(**over):
    base = {
        "id": "4012345678", "title": "QA Engineer", "companyName": "Acme GmbH",
        "location": "Berlin, Germany", "workType": "On-site",
        "description": "We need a QA engineer with Selenium.",
        "jobUrl": "https://www.linkedin.com/jobs/view/4012345678",
        "postedAtTimestamp": 1762500000000, "posterFullName": "Jane Recruiter",
    }
    return base | over


def test_input_always_sets_rows_and_disables_paid_addons():
    q = SearchQuery(title="QA", country=Country.GERMANY)
    inp = build_input(q, limit=5, recent_window=None)
    assert inp["rows"] == 5
    assert inp["titles"] == ["QA"]
    assert inp["companyProfile"] is False and inp["enrichCompany"] is False
    assert "publishedAt" not in inp


def test_rows_split_across_city_searches_rounding_up():
    q = SearchQuery(title="QA", country=Country.GERMANY, cities=["Berlin", "Munich"])
    assert build_input(q, limit=5, recent_window=None)["rows"] == 3


def test_incremental_uses_recent_window():
    q = SearchQuery(title="QA", country=Country.GERMANY)
    assert build_input(q, 5, "r86400")["publishedAt"] == "r86400"


def test_map_item_to_unified_job_and_drops_poster_data():
    job = map_item(item(), NOW)
    assert job.id == "linkedin:4012345678"
    assert job.company == "Acme GmbH" and job.remote is False
    assert job.posted_at.year == 2025
    assert "Jane" not in job.model_dump_json()


def test_map_item_detects_remote_and_arabic():
    job = map_item(item(workType="Remote", description="نبحث عن مهندس جودة برمجيات"), NOW)
    assert job.remote is True and job.language == "ar"


def test_map_item_skips_items_without_description():
    assert map_item(item(description=""), NOW) is None


def test_search_uses_runner_and_respects_limit(tmp_path):
    calls = []

    def fake_runner(actor_id, run_input, max_items, max_charge):
        calls.append((actor_id, run_input, max_items, max_charge))
        return [item(id=str(i)) for i in range(8)], 0.012

    src = LinkedInApifySource(Settings(_env_file=None, data_dir=tmp_path), runner=fake_runner)
    res = src.search(SearchQuery(title="QA", country=Country.GERMANY), limit=5)
    assert len(res.jobs) == 5 and res.cost_usd == 0.012
    assert len(calls) == 1  # exactly one Apify call, never a loop
    assert calls[0][2] == 5 and calls[0][3] <= 0.01


# ---- against the real recording (tests/fixtures/apify_bebity_5jobs.json) ----
import json
from pathlib import Path

from jobcv.sources.linkedin_apify import charged_cost

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apify_bebity_5jobs.json"


def test_real_recording_maps_every_item():
    items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
    jobs = [map_item(i, NOW) for i in items]
    assert all(jobs) and len(jobs) == len(items)
    for j in jobs:
        assert j.posted_at is not None, "publishedAt date must parse"
        assert len(j.description) > 500
        assert j.url.startswith("https://www.linkedin.com/jobs/view/")
        assert "United Arab Emirates" in j.location


def test_real_recording_contains_no_poster_personal_data():
    assert "poster" not in FIXTURE.read_text(encoding="utf-8")


def test_charged_cost_prices_events_not_snapshot():
    # numbers from the real run: 2 start events (2 GB) + 4 jobs
    run = {
        "usageTotalUsd": 0.0016,
        "chargedEventCounts": {"apify-actor-start": 2, "apify-default-dataset-item": 4},
        "pricingInfo": {"pricingPerEvent": {"actorChargeEvents": {
            "apify-actor-start": {"eventPriceUsd": 5e-05},
            "apify-default-dataset-item": {"eventPriceUsd": 0.0015}}}},
    }
    assert charged_cost(run) == 0.0061


def test_estimate_leaves_room_for_all_requested_jobs(tmp_path):
    src = LinkedInApifySource(Settings(_env_file=None, data_dir=tmp_path))
    q = SearchQuery(title="QA", country=Country.UAE)
    est = src.estimate_cost(q, 5)
    assert est - 2 * 0.00005 >= 5 * 0.0015  # both start events + 5 jobs fit under the cap


def test_remote_search_marks_jobs_remote_even_if_worktype_empty():
    assert map_item(item(workType=""), NOW, remote_search=True).remote is True


def test_charged_cost_bills_every_received_item_even_if_counts_lag():
    # seen live: Apify reported 4 item events while 5 items were delivered and charged
    run = {
        "chargedEventCounts": {"apify-actor-start": 2, "apify-default-dataset-item": 4},
        "pricingInfo": {"pricingPerEvent": {"actorChargeEvents": {
            "apify-actor-start": {"eventPriceUsd": 5e-05},
            "apify-default-dataset-item": {"eventPriceUsd": 0.0015}}}},
    }
    assert charged_cost(run, items_received=5) == 0.0076

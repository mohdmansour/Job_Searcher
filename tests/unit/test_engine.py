import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobcv.agents.base import LLMReply
from jobcv.config import Settings
from jobcv.pipeline.engine import DONE, STOPPED, Engine, NotFound
from jobcv.schemas import (
    CV,
    Country,
    EditResult,
    Experience,
    MatchResult,
    ReviewResult,
    SearchQuery,
    Usage,
)
from jobcv.sources.base import SourceResult
from jobcv.sources.linkedin_apify import map_item
from jobcv.store import UserStore

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
MASTER = CV(language="en", summary="Teacher",
            experience=[Experience(title="Teacher", employer="School", start="2019", end="2024",
                                   bullets=["Marked work."])])


class FixtureSource:
    name = "linkedin"
    calls = 0

    def estimate_cost(self, q, limit):
        return 0.0001 + 0.0015 * limit

    def search(self, q, limit, recent_only=False):
        FixtureSource.calls += 1
        items = json.loads((FX / "apify_bebity_5jobs.json").read_text(encoding="utf-8"))["items"]
        now = datetime.now(UTC)
        return SourceResult([map_item(i, now) for i in items][:limit], 0.0061)


def fake_llm(spec, model, prompt, out):
    if spec.name == "parser":
        parsed = MASTER
    elif spec.name == "scorer":
        parsed = MatchResult(score=70 if "Senior QA" in prompt else 20, reasons=["r"],
                             matched_skills=[], gaps=["g"])
    elif spec.name == "editor":
        parsed = EditResult(tailored_cv=MASTER)
    else:
        parsed = ReviewResult(status="PASS")
    return LLMReply(raw="", parsed=parsed, usage=Usage(input_tokens=1000, output_tokens=100))


def fake_render(cv, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 fake")
    return path


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")


@pytest.fixture
def engine(s):
    return Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render, synchronous=True)


Q = SearchQuery(title="QA Engineer", country=Country.UAE, max_results=5)


def full_flow(engine):
    cv_id = engine.add_cv((FX / "cv_teacher_en.pdf").read_bytes())
    run_id, est = engine.start_search(cv_id, Q)
    return cv_id, run_id, est


def test_search_run_ranks_jobs_and_records_cost(engine):
    _cv_id, run_id, est = full_flow(engine)
    assert est.within_cap and est.total_usd > 0
    run = engine.get_search(run_id)
    assert run["status"] == DONE
    scores = [j["match"]["score"] for j in run["result"]["jobs"]]
    assert scores == sorted(scores, reverse=True) and scores[0] == 70
    assert run["result"]["last_updated"]
    cost = run["cost"]
    assert cost["apify_usd"] == pytest.approx(0.0061)
    assert cost["price_to_user_usd"] == pytest.approx(cost["actual_cost_usd"] * 3)


def test_tailor_run_produces_pdf_per_job(engine):
    _, run_id, _ = full_flow(engine)
    job_ids = [j["job"]["id"] for j in engine.get_search(run_id)["result"]["jobs"][:2]]
    t_id, _est = engine.start_tailor(run_id, job_ids, extra_info="I also used Jira.")
    t = engine.get_tailor(t_id)
    assert t["status"] == DONE and len(t["result"]) == 2
    first = t["result"][0]
    assert first["review_status"] == "PASS" and first["pdf"].startswith("CV - ")
    assert engine.pdf_path(t_id, first["pdf"]).exists()
    assert "Jira" not in json.dumps(t["request"])  # extra info is not stored


def test_tailor_rejects_unknown_job_ids(engine):
    _, run_id, _ = full_flow(engine)
    with pytest.raises(ValueError, match="unknown"):
        engine.start_tailor(run_id, ["linkedin:nope"])


def test_pdf_path_blocks_other_files(engine):
    _, run_id, _ = full_flow(engine)
    job_id = engine.get_search(run_id)["result"]["jobs"][0]["job"]["id"]
    t_id, _ = engine.start_tailor(run_id, [job_id])
    with pytest.raises(NotFound):
        engine.pdf_path(t_id, "../../user.db")


def test_over_cap_estimate_never_starts(engine):
    FixtureSource.calls = 0
    cv_id = engine.add_cv((FX / "cv_teacher_en.pdf").read_bytes())
    big = Q.model_copy(update={"max_results": 200})  # ~$1.18 estimated > $1 cap
    run_id, est = engine.start_search(cv_id, big)
    assert not est.within_cap
    assert engine.get_search(run_id)["status"] == STOPPED and FixtureSource.calls == 0


def test_delete_cv_removes_runs_and_files(engine, s):
    cv_id, run_id, _ = full_flow(engine)
    job_id = engine.get_search(run_id)["result"]["jobs"][0]["job"]["id"]
    engine.start_tailor(run_id, [job_id])
    assert any(s.user_files_dir.rglob("*.pdf"))
    assert engine.delete_cv(cv_id) is True
    with pytest.raises(NotFound):
        engine.get_search(run_id)
    assert not any(s.user_files_dir.rglob("*.pdf"))
    assert engine.delete_cv(cv_id) is False


def test_expired_data_is_hidden_and_swept(s):
    t = [datetime(2026, 11, 8, tzinfo=UTC)]
    store = UserStore(s, now=lambda: t[0])
    cv_id = store.add_cv("en", "text", "raw", "{}", {})
    (store.files_dir(cv_id) / "x").mkdir(parents=True)
    t[0] += timedelta(hours=24, seconds=1)
    assert store.get_cv(cv_id) is None
    assert store.sweep() == 1
    assert not store.files_dir(cv_id).exists()


def test_user_db_and_job_cache_are_separate_files(engine, s):
    full_flow(engine)
    cache_tables = {r[0] for r in sqlite3.connect(s.jobs_cache_db).execute(
        "select name from sqlite_master where type='table'")}
    assert cache_tables == {"searches"}
    cache_text = s.jobs_cache_db.read_bytes()
    assert b"Teacher" not in cache_text and b"score" not in cache_text


def test_runs_left_running_by_a_dead_process_are_marked_failed(s):
    store = UserStore(s)
    run_id = store.add_run("search", "cv", {}, {}, "running")
    Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render, synchronous=True)
    run = store.get_run(run_id)
    assert run["status"] == "failed" and run["error"] == "interrupted"


def test_llm_has_timeout_and_retries(s):
    assert s.llm_timeout_secs == 120 and s.llm_max_retries == 2

"""Found by the independent review: deleting has to really stop and remove everything, including
in the middle of a run or at the same moment as another request."""

import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobcv.api import auth
from jobcv.api.app import create_app
from jobcv.cli import main
from jobcv.config import Settings
from jobcv.pdf.render import pdf_filename
from jobcv.pipeline.engine import Engine, NotFound
from jobcv.schemas import SearchQuery
from jobcv.store import UserStore
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
PDF = (FX / "cv_teacher_en.pdf").read_bytes()
A = {"X-Test-User": "user_a"}
QUERY = SearchQuery(title="QA", country="United Arab Emirates", max_results=5)


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")


def make_engine(s, source=None, llm=fake_llm, renderer=fake_render):
    return Engine(s, source=source or FixtureSource(), llm=llm, renderer=renderer, synchronous=True)


@pytest.fixture
def engine(s):
    return make_engine(s)


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine, verifier=lambda r: r.headers.get("X-Test-User"))) as c:
        yield c


def count(s, table, where="1=1"):
    return sqlite3.connect(s.user_db).execute(
        f"select count(*) from {table} where {where}").fetchone()[0]


def searched(engine):
    cv_id = engine.add_cv(PDF, owner="a")
    run_id, _ = engine.start_search(cv_id, QUERY, owner="a")
    return cv_id, run_id, engine.get_search(run_id, "a")["result"]["jobs"][0]["job"]["id"]


# ---- deleting stops the work ----
def test_deleting_during_a_search_stops_sending_the_cv_to_the_llm(s):
    scored = []

    def llm(spec, model, prompt, out):
        if spec.name == "scorer":
            scored.append(1)
            engine.delete_cv(cv_id, "a")
        return fake_llm(spec, model, prompt, out)

    engine = make_engine(s, llm=llm)
    cv_id = engine.add_cv(PDF, owner="a")
    run_id, _ = engine.start_search(cv_id, QUERY, owner="a")
    assert len(scored) == 1
    with pytest.raises(NotFound):
        engine.get_search(run_id, "a")


def test_deleting_during_tailoring_stops_before_the_next_llm_call(engine):
    cv_id, run_id, job_id = searched(engine)
    seen = []

    def llm(spec, model, prompt, out):
        seen.append(spec.name)
        if spec.name == "editor":
            engine.delete_cv(cv_id, "a")
        return fake_llm(spec, model, prompt, out)

    engine.llm = llm
    engine.start_tailor(run_id, [job_id], owner="a")
    assert seen == ["editor"]
    assert not engine.store.files_dir(cv_id).exists()


def test_a_failed_render_after_deletion_leaves_no_files(engine):
    cv_id, run_id, job_id = searched(engine)

    def broken(cv, path):
        engine.delete_cv(cv_id, "a")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"partial")
        raise RuntimeError("chromium crashed")

    engine.renderer = broken
    engine.start_tailor(run_id, [job_id], owner="a")
    assert not engine.store.files_dir(cv_id).exists()


# ---- races ----
def test_a_cv_deleted_just_before_the_run_is_recorded_leaves_no_run(s):
    class DeletesWhileEstimating(FixtureSource):
        def estimate_cost(self, q, limit):
            engine.delete_cv(cv_id, "a")
            return super().estimate_cost(q, limit)

    engine = make_engine(s, source=DeletesWhileEstimating())
    cv_id = engine.add_cv(PDF, owner="a")
    with pytest.raises(NotFound):
        engine.start_search(cv_id, QUERY, owner="a")
    assert count(s, "runs") == 0


def test_parallel_uploads_leave_exactly_one_cv(s):
    store = UserStore(s)
    barrier = threading.Barrier(8)

    def upload():
        barrier.wait()
        store.add_cv("en", "text", "raw", "{}", {}, owner="a", replace=True)

    threads = [threading.Thread(target=upload) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert count(s, "cvs", "user_id = 'a'") == 1


def test_a_file_removed_at_the_last_moment_is_404_not_a_crash(client, engine):
    upload = client.post("/cv", headers=A, files={"file": ("cv.pdf", PDF, "application/pdf")})
    cv_id = upload.json()["cv_id"]
    run_id = client.post("/search", headers=A, json={
        "cv_id": cv_id, "title": "QA", "country": "United Arab Emirates", "max_results": 3,
    }).json()["run_id"]
    job_id = client.get(f"/runs/{run_id}", headers=A).json()["jobs"][0]["job"]["id"]
    tailor = client.post("/tailor", headers=A, json={"run_id": run_id, "job_ids": [job_id]})
    url = client.get(f"/tailor/{tailor.json()['run_id']}", headers=A).json()["results"][0]["pdf_url"]
    for pdf in engine.store.files_dir(cv_id).rglob("*.pdf"):
        pdf.unlink()
    assert client.get(url, headers=A).status_code == 404


# ---- expiry ----
def test_a_run_is_gone_as_soon_as_its_cv_expires(s):
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = UserStore(s, now=lambda: clock[0])
    cv_id = store.add_cv("en", "text", "raw", "{}", {}, owner="a")
    clock[0] += timedelta(hours=1)
    run_id = store.add_run("search", cv_id, {}, {}, "done", owner="a")
    assert store.get_run(run_id, owner="a") is not None
    clock[0] += timedelta(hours=23, minutes=30)  # the CV has expired, the run has not
    assert store.get_run(run_id, owner="a") is None


def test_the_command_line_removes_expired_data_when_it_starts(engine, s):
    engine.add_cv(PDF)
    engine.store.now = lambda: datetime.now(UTC) + timedelta(hours=48)
    main(["cv", "delete", "nothing"], engine=engine)
    assert count(s, "cvs") == 0


def test_deleted_cv_text_does_not_stay_in_the_database_file(s):
    store = UserStore(s)
    cv_id = store.add_cv("en", "text", "VERY-PRIVATE-MARKER" * 200, "{}", {}, owner="a")
    store.delete_cv(cv_id, owner="a")
    assert b"VERY-PRIVATE-MARKER" not in s.user_db.read_bytes()


# ---- one process must not disturb another ----
def test_a_new_command_line_engine_leaves_running_runs_alone(s):
    store = UserStore(s)
    cv_id = store.add_cv("en", "text", "raw", "{}", {})
    run_id = store.add_run("search", cv_id, {}, {}, "running")
    make_engine(s)
    assert store.get_run(run_id)["status"] == "running"


# ---- the API's edges ----
def test_an_unexpected_error_logs_only_its_type(client, engine, caplog, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("PRIVATE CV TEXT")

    monkeypatch.setattr(engine, "get_cv", explode)
    with caplog.at_level(logging.DEBUG):
        r = client.post("/search", headers=A, json={
            "cv_id": "x", "title": "QA", "country": "United Arab Emirates"})
    assert r.status_code == 500 and "PRIVATE" not in r.text
    assert "PRIVATE" not in caplog.text and "RuntimeError" in caplog.text


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_description_is_not_published(client, path):
    assert client.get(path).status_code == 404


def test_the_command_line_owner_cannot_be_a_signed_in_user(client):
    assert client.get("/me", headers={"X-Test-User": "local"}).status_code == 401


def test_only_real_session_tokens_are_accepted(s, monkeypatch):
    seen = {}

    class SignedOut:
        is_signed_in, payload = False, None

    def fake(request, options):
        seen["accepts"] = options.accepts_token
        return SignedOut

    monkeypatch.setattr(auth, "authenticate_request", fake)
    keyed = s.model_copy(update={"clerk_jwt_key": "key"})
    request = type("R", (), {"method": "GET", "headers": {}})()
    assert auth.clerk_verifier(keyed)(request) is None
    assert seen["accepts"] == ["session_token"]


# ---- PDF names ----
def test_a_pdf_name_is_safe_inside_a_link():
    name = pdf_filename("C# Developer", "100% Remote")
    assert "#" not in name and "%" not in name


def test_two_jobs_with_the_same_title_and_company_get_their_own_pdfs(s):
    class Twins(FixtureSource):
        def search(self, q, limit, recent_only=False):
            res = super().search(q, limit, recent_only)
            twins = [res.jobs[0].model_copy(update={
                "id": f"linkedin:{i}", "url": f"https://www.linkedin.com/jobs/view/{i}",
                "location": city}) for i, city in enumerate(("Dubai", "Abu Dhabi"))]
            return type(res)(twins, 0.0061)

    engine = make_engine(s.model_copy(update={"unlimited_user_ids": ["a"]}), source=Twins())
    cv_id = engine.add_cv(PDF, owner="a")
    run_id, _ = engine.start_search(cv_id, QUERY, owner="a")
    ids = [j["job"]["id"] for j in engine.get_search(run_id, "a")["result"]["jobs"]]
    tailor_id, _ = engine.start_tailor(run_id, ids, owner="a")
    names = [r["pdf"] for r in engine.get_tailor(tailor_id, "a")["result"]]
    assert len(set(names)) == 2
    assert all(engine.pdf_path(tailor_id, n, "a").exists() for n in names)

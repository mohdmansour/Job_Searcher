"""Free allowance and abuse limits (SPEC-accounts, A7 + A8). Written before the code."""

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobcv.accounts import Accounts, Refused
from jobcv.api.app import create_app
from jobcv.config import Settings
from jobcv.pipeline.engine import Engine
from jobcv.schemas import SearchQuery
from jobcv.store import LOCAL_OWNER
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
PDF = (FX / "cv_teacher_en.pdf").read_bytes()
QUERY = SearchQuery(title="QA", country="United Arab Emirates", max_results=5)


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata",
                    unlimited_user_ids=["owner"])


@pytest.fixture
def accounts(s):
    return Accounts(s)


def refused(code: str):
    return pytest.raises(Refused, match=code)


def in_parallel(n: int, fn) -> list:
    """Runs fn n times at the same moment; returns what each call returned or raised."""
    barrier, results = threading.Barrier(n), []

    def run():
        barrier.wait()
        try:
            results.append(fn())
        except Exception as e:  # noqa: BLE001
            results.append(e)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# ---------------- the free allowance ----------------
def test_a_new_account_has_one_free_search_and_one_free_cv(accounts):
    assert accounts.status("u") == {"free_searches_left": 1, "free_tailors_left": 1,
                                    "unlimited": False, "free_max_results": 10}


def test_the_free_search_can_be_used_once(accounts):
    accounts.settle(accounts.claim("u", "search"))
    with refused("allowance_used"):
        accounts.claim("u", "search")


def test_parallel_claims_of_one_free_search_have_exactly_one_winner(accounts):
    results = in_parallel(10, lambda: accounts.claim("u", "search"))
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert all(isinstance(r, Refused) for r in results if isinstance(r, Exception))


def test_asking_for_more_cvs_than_are_left_is_refused(accounts):
    with refused("allowance_used"):
        accounts.claim("u", "tailor", n=2)
    assert accounts.status("u")["free_tailors_left"] == 1


def test_a_refund_gives_the_allowance_back(accounts):
    accounts.settle(accounts.claim("u", "search"), refund=1)
    assert accounts.status("u")["free_searches_left"] == 1


def test_settling_twice_refunds_only_once(accounts):
    claim = accounts.claim("u", "tailor")
    accounts.settle(claim, refund=1)
    accounts.settle(claim, refund=1)
    accounts.settle(accounts.claim("u", "tailor"))
    assert accounts.status("u")["free_tailors_left"] == 0


def test_one_account_using_its_allowance_leaves_others_alone(accounts):
    accounts.settle(accounts.claim("u", "search"))
    assert accounts.status("v")["free_searches_left"] == 1


# ---------------- one run at a time ----------------
def test_a_second_run_while_one_is_active_is_refused(accounts):
    accounts.claim("u", "search")
    with refused("rate_limited"):
        accounts.claim("u", "tailor")


def test_a_finished_run_frees_the_slot(accounts):
    accounts.settle(accounts.claim("u", "search"))
    accounts.settle(accounts.claim("u", "tailor"))


def test_a_refused_claim_takes_nothing(accounts):
    accounts.settle(accounts.claim("u", "search"))
    with refused("allowance_used"):
        accounts.claim("u", "search")
    accounts.settle(accounts.claim("u", "tailor"))  # not blocked by the refused one


def test_runs_left_by_a_stopped_server_are_cleared_at_start(accounts):
    accounts.claim("u", "search")
    accounts.clear_active()
    accounts.claim("u", "tailor")


# ---------------- uploads ----------------
def test_three_uploads_a_day_then_refused(accounts):
    for _ in range(3):
        accounts.settle(accounts.claim("u", "upload"))
    with refused("rate_limited"):
        accounts.claim("u", "upload")


def test_uploads_are_allowed_again_the_next_day(s):
    clock = [datetime(2026, 1, 1, 20, tzinfo=UTC)]
    accounts = Accounts(s, now=lambda: clock[0])
    for _ in range(3):
        accounts.settle(accounts.claim("u", "upload"))
    clock[0] += timedelta(hours=5)
    accounts.claim("u", "upload")


def test_an_upload_does_not_block_a_run(accounts):
    accounts.claim("u", "upload")
    accounts.claim("u", "search")


# ---------------- the daily budget for all free use ----------------
def test_a_claim_that_would_pass_the_daily_budget_is_refused(s):
    accounts = Accounts(s.model_copy(update={"daily_free_budget_usd": 0.10}))
    accounts.settle(accounts.claim("u", "search", cost_usd=0.08), spent_usd=0.08)
    with refused("daily_budget"):
        accounts.claim("v", "search", cost_usd=0.05)


def test_the_budget_counts_what_was_really_spent(s):
    accounts = Accounts(s.model_copy(update={"daily_free_budget_usd": 0.10}))
    accounts.settle(accounts.claim("u", "search", cost_usd=0.09), spent_usd=0.01)
    accounts.claim("v", "search", cost_usd=0.09)  # the unused reservation came back


def test_parallel_claims_cannot_overspend_the_budget(s):
    accounts = Accounts(s.model_copy(update={"daily_free_budget_usd": 0.25}))
    results = in_parallel(10, lambda: accounts.claim(
        f"u{threading.get_ident()}", "search", cost_usd=0.10))
    assert sum(not isinstance(r, Exception) for r in results) == 2


def test_the_budget_starts_again_the_next_day(s):
    clock = [datetime(2026, 1, 1, 23, tzinfo=UTC)]
    accounts = Accounts(s.model_copy(update={"daily_free_budget_usd": 0.10}),
                        now=lambda: clock[0])
    accounts.settle(accounts.claim("u", "search", cost_usd=0.10), spent_usd=0.10)
    clock[0] += timedelta(hours=2)
    accounts.claim("v", "search", cost_usd=0.10)


# ---------------- accounts with no limits ----------------
@pytest.mark.parametrize("who", ["owner", LOCAL_OWNER])
def test_unlimited_accounts_are_never_refused(accounts, who):
    for _ in range(5):
        accounts.claim(who, "search", cost_usd=100)
        accounts.claim(who, "upload")
    assert accounts.status(who)["unlimited"] is True


def test_unlimited_ids_can_be_given_as_a_comma_separated_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBCV_UNLIMITED_USER_IDS", "user_a, user_b")
    assert Settings(_env_file=None, data_dir=tmp_path).unlimited_user_ids == ["user_a", "user_b"]


# ---------------- what is stored ----------------
def test_the_accounts_database_holds_only_ids_counters_and_amounts(accounts, s):
    accounts.settle(accounts.claim("user_x", "search", cost_usd=0.05), spent_usd=0.04)
    accounts.settle(accounts.claim("user_x", "upload"))
    db = sqlite3.connect(s.accounts_db)
    columns = {c for (t,) in db.execute("select name from sqlite_master where type='table'")
               for c in [r[1] for r in db.execute(f"pragma table_info({t})")]}
    assert columns <= {"user_id", "searches", "tailors", "bonus_searches", "bonus_tailors",
                       "day", "n", "usd", "tailor_id", "job_id"}  # run and public job ids only
    assert s.accounts_db not in (s.user_db, s.jobs_cache_db)


# ---------------- through the engine ----------------
def make_engine(s, source=None, renderer=fake_render):
    return Engine(s, source=source or FixtureSource(), llm=fake_llm, renderer=renderer,
                  synchronous=True)


class NoJobs(FixtureSource):
    def search(self, q, limit, recent_only=False):
        res = super().search(q, limit, recent_only)
        return type(res)([], 0.0)


def test_a_search_that_finds_nothing_is_refunded(s):
    engine = make_engine(s, source=NoJobs())
    cv_id = engine.add_cv(PDF, owner="u")
    engine.start_search(cv_id, QUERY, owner="u")
    assert engine.accounts.status("u")["free_searches_left"] == 1


def test_a_search_that_fails_is_refunded(s):
    class Broken(FixtureSource):
        def search(self, q, limit, recent_only=False):
            raise RuntimeError("apify down")

    engine = make_engine(s, source=Broken())
    cv_id = engine.add_cv(PDF, owner="u")
    engine.start_search(cv_id, QUERY, owner="u")
    assert engine.accounts.status("u")["free_searches_left"] == 1


def test_tailoring_that_produces_no_pdf_is_refunded(s):
    def broken(cv, path):
        raise RuntimeError("chromium crashed")

    engine = make_engine(s, renderer=broken)
    cv_id = engine.add_cv(PDF, owner="u")
    run_id, _ = engine.start_search(cv_id, QUERY, owner="u")
    job_id = engine.get_search(run_id, "u")["result"]["jobs"][0]["job"]["id"]
    engine.start_tailor(run_id, [job_id], owner="u")
    assert engine.accounts.status("u")["free_tailors_left"] == 1


def test_a_successful_free_journey_uses_the_allowance(s):
    engine = make_engine(s)
    cv_id = engine.add_cv(PDF, owner="u")
    run_id, _ = engine.start_search(cv_id, QUERY, owner="u")
    job_id = engine.get_search(run_id, "u")["result"]["jobs"][0]["job"]["id"]
    engine.start_tailor(run_id, [job_id], owner="u")
    assert engine.accounts.status("u") | {} == {"free_searches_left": 0, "free_tailors_left": 0,
                                                "unlimited": False, "free_max_results": 10}


def test_deleting_the_cv_does_not_reset_the_allowance(s):
    engine = make_engine(s)
    cv_id = engine.add_cv(PDF, owner="u")
    engine.start_search(cv_id, QUERY, owner="u")
    engine.delete_cv(cv_id, owner="u")
    cv_id = engine.add_cv(PDF, owner="u")
    with refused("allowance_used"):
        engine.start_search(cv_id, QUERY, owner="u")


def test_a_free_search_is_limited_to_ten_results(s):
    engine = make_engine(s)
    cv_id = engine.add_cv(PDF, owner="u")
    with refused("free_limit"):
        engine.start_search(cv_id, QUERY.model_copy(update={"max_results": 25}), owner="u")
    assert engine.accounts.status("u")["free_searches_left"] == 1


def test_an_unlimited_account_can_search_for_more(s):
    engine = make_engine(s)
    cv_id = engine.add_cv(PDF, owner="owner")
    engine.start_search(cv_id, QUERY.model_copy(update={"max_results": 25}), owner="owner")


def test_a_free_search_never_bypasses_the_job_cache(s):
    class Counting(FixtureSource):
        calls = 0

        def search(self, q, limit, recent_only=False):
            type(self).calls += 1
            return super().search(q, limit, recent_only)

    engine = make_engine(s, source=Counting())
    first = engine.add_cv(PDF, owner="owner")
    engine.start_search(first, QUERY, owner="owner")
    cv_id = engine.add_cv(PDF, owner="u")
    engine.start_search(cv_id, QUERY, force_refresh=True, owner="u")
    assert Counting.calls == 1


def test_a_fourth_upload_in_a_day_is_refused(s):
    engine = make_engine(s)
    for _ in range(3):
        engine.add_cv(PDF, owner="u")
    with refused("rate_limited"):
        engine.add_cv(PDF, owner="u")


def test_a_file_that_is_not_a_cv_does_not_use_an_upload(s):
    engine = make_engine(s)
    for _ in range(3):
        with pytest.raises(ValueError):
            engine.add_cv(b"not a pdf", owner="u")
    engine.add_cv(PDF, owner="u")


# ---------------- over HTTP ----------------
@pytest.fixture
def client(s):
    engine = make_engine(s)
    with TestClient(create_app(engine, verifier=lambda r: r.headers.get("X-Test-User"))) as c:
        yield c


U = {"X-Test-User": "user_u"}


def test_me_reports_the_allowance(client):
    body = client.get("/me", headers=U).json()
    assert body["free_searches_left"] == 1 and body["free_tailors_left"] == 1
    assert body["unlimited"] is False and body["free_max_results"] == 10


def test_a_used_allowance_is_a_403_with_a_code(client):
    cv_id = client.post("/cv", headers=U, files={"file": ("cv.pdf", PDF, "application/pdf")}
                        ).json()["cv_id"]
    search = {"cv_id": cv_id, "title": "QA", "country": "United Arab Emirates", "max_results": 3}
    assert client.post("/search", headers=U, json=search).status_code == 202
    r = client.post("/search", headers=U, json=search)
    assert r.status_code == 403 and r.json() == {"detail": {"code": "allowance_used"}}


def test_a_busy_account_gets_a_429_with_a_code(client):
    cv_id = client.post("/cv", headers=U, files={"file": ("cv.pdf", PDF, "application/pdf")}
                        ).json()["cv_id"]
    client.app.state.engine.accounts.claim("user_u", "tailor")  # a run still working
    r = client.post("/search", headers=U, json={
        "cv_id": cv_id, "title": "QA", "country": "United Arab Emirates", "max_results": 3})
    assert r.status_code == 429 and r.json() == {"detail": {"code": "rate_limited"}}


# ---------------- extra free uses, given by the owner ----------------
def test_granting_searches_adds_to_what_is_left(accounts):
    accounts.settle(accounts.claim("u", "search"))
    accounts.grant("u", searches=2)
    assert accounts.status("u")["free_searches_left"] == 2


def test_granted_searches_can_all_be_used_then_it_stops(accounts):
    accounts.grant("u", searches=2)
    for _ in range(3):  # the normal free one plus the 2 granted
        accounts.settle(accounts.claim("u", "search"))
    with refused("allowance_used"):
        accounts.claim("u", "search")


def test_granting_tailored_cvs_works_the_same_way(accounts):
    accounts.grant("u", tailors=3)
    assert accounts.status("u")["free_tailors_left"] == 4
    accounts.settle(accounts.claim("u", "tailor", n=4))
    assert accounts.status("u")["free_tailors_left"] == 0


def test_a_grant_for_one_account_leaves_others_alone(accounts):
    accounts.grant("u", searches=2)
    assert accounts.status("v")["free_searches_left"] == 1


def test_a_grant_must_be_positive(accounts):
    with pytest.raises(ValueError):
        accounts.grant("u", searches=-1)


def test_the_command_line_grants_to_an_account(s, capsys):
    from jobcv.cli import main
    main(["grant", "user_x", "--searches", "2"], engine=make_engine(s))
    assert Accounts(s).status("user_x")["free_searches_left"] == 3
    assert "user_x" in capsys.readouterr().out


def test_an_older_accounts_database_is_upgraded_and_keeps_its_counts(s):
    s.data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(s.accounts_db)
    db.executescript("create table usage (user_id text primary key, searches integer not null"
                     " default 0, tailors integer not null default 0);"
                     "insert into usage values ('u', 1, 1);")
    db.commit()
    db.close()
    accounts = Accounts(s)
    assert accounts.status("u")["free_searches_left"] == 0  # what was used stays used
    accounts.grant("u", searches=2)
    assert accounts.status("u")["free_searches_left"] == 2

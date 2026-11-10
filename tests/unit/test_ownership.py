"""Two users try to reach each other's data. Everything of someone else's answers 404."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobcv.api.app import create_app
from jobcv.config import Settings
from jobcv.pipeline.engine import Engine
from jobcv.store import UserStore
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
PDF = (FX / "cv_teacher_en.pdf").read_bytes()
A, B = {"X-Test-User": "user_a"}, {"X-Test-User": "user_b"}
SEARCH = {"title": "QA", "country": "United Arab Emirates", "max_results": 3}


@pytest.fixture
def engine(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")
    return Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render, synchronous=True)


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine, verifier=lambda r: r.headers.get("X-Test-User"))) as c:
        yield c


def upload(client, who):
    return client.post("/cv", headers=who, files={"file": ("cv.pdf", PDF, "application/pdf")})


@pytest.fixture
def a(client):
    """User A with a CV, a finished search and a finished tailoring run."""
    cv_id = upload(client, A).json()["cv_id"]
    run_id = client.post("/search", headers=A, json={"cv_id": cv_id, **SEARCH}).json()["run_id"]
    job_id = client.get(f"/runs/{run_id}", headers=A).json()["jobs"][0]["job"]["id"]
    tailor_id = client.post("/tailor", headers=A, json={"run_id": run_id, "job_ids": [job_id]}).json()["run_id"]
    pdf_url = client.get(f"/tailor/{tailor_id}", headers=A).json()["results"][0]["pdf_url"]
    return {"cv": cv_id, "run": run_id, "job": job_id, "tailor": tailor_id, "pdf": pdf_url}


def test_the_owner_can_reach_everything(client, a):
    assert client.get(f"/cv/{a['cv']}", headers=A).status_code == 200
    assert client.get(f"/runs/{a['run']}", headers=A).status_code == 200
    assert client.get(f"/tailor/{a['tailor']}", headers=A).status_code == 200
    assert client.get(a["pdf"], headers=A).status_code == 200


def test_another_user_cannot_see_the_cv(client, a):
    assert client.get(f"/cv/{a['cv']}", headers=B).status_code == 404


def test_another_user_cannot_delete_the_cv(client, a):
    assert client.delete(f"/cv/{a['cv']}", headers=B).status_code == 404
    assert client.get(f"/cv/{a['cv']}", headers=A).status_code == 200
    assert client.get(a["pdf"], headers=A).status_code == 200


def test_another_user_cannot_search_with_the_cv(client, a):
    r = client.post("/search", headers=B, json={"cv_id": a["cv"], **SEARCH})
    assert r.status_code == 404


def test_another_user_cannot_read_the_run(client, a):
    assert client.get(f"/runs/{a['run']}", headers=B).status_code == 404


def test_another_user_cannot_tailor_from_the_run(client, a):
    r = client.post("/tailor", headers=B, json={"run_id": a["run"], "job_ids": [a["job"]]})
    assert r.status_code == 404


def test_another_user_cannot_read_the_tailoring(client, a):
    assert client.get(f"/tailor/{a['tailor']}", headers=B).status_code == 404


def test_another_user_cannot_download_the_pdf(client, a):
    assert client.get(a["pdf"], headers=B).status_code == 404


@pytest.mark.parametrize("method,path", [
    ("GET", "/me"), ("DELETE", "/me/data"), ("POST", "/cv"), ("GET", "/cv/x"), ("DELETE", "/cv/x"),
    ("POST", "/estimate/search"), ("POST", "/estimate/tailor"), ("POST", "/search"),
    ("GET", "/runs/x"), ("POST", "/tailor"), ("GET", "/tailor/x"), ("GET", "/files/x/y.pdf"),
])
def test_every_route_refuses_a_signed_out_request(client, method, path):
    assert client.request(method, path).status_code == 401


def test_no_route_is_left_unprotected(client):
    """A new route added later without sign-in fails here."""
    routes = client.app.routes
    assert len(routes) >= 11
    for route in routes:
        path = route.path.replace("{cv_id}", "x").replace("{run_id}", "x").replace(
            "{tailor_id}", "x").replace("{name}", "y")
        for method in route.methods - {"HEAD", "OPTIONS"}:
            assert client.request(method, path).status_code == 401, f"{method} {route.path}"


def test_a_new_upload_replaces_the_previous_cv(client):
    first = upload(client, A).json()["cv_id"]
    second = upload(client, A).json()["cv_id"]
    assert client.get(f"/cv/{first}", headers=A).status_code == 404
    assert client.get(f"/cv/{second}", headers=A).status_code == 200


def test_one_user_uploading_leaves_others_alone(client):
    theirs = upload(client, A).json()["cv_id"]
    upload(client, B)
    assert client.get(f"/cv/{theirs}", headers=A).status_code == 200


def test_files_are_removed_when_the_owner_deletes(client, engine, a):
    assert client.delete(f"/cv/{a['cv']}", headers=A).status_code == 204
    assert not engine.store.files_dir(a["cv"]).exists()


def test_the_command_line_still_works_without_an_account(engine):
    cv_id = engine.add_cv(PDF)
    assert engine.get_cv(cv_id)[0] is not None


def test_a_signed_in_user_cannot_reach_command_line_data(client, engine):
    cv_id = engine.add_cv(PDF)
    assert client.get(f"/cv/{cv_id}", headers=A).status_code == 404


def test_an_existing_database_is_upgraded_and_old_rows_have_no_owner(tmp_path):
    db = sqlite3.connect(tmp_path / "user.db")
    db.executescript("""
      create table cvs (id text primary key, created_at text, expires_at text, language text,
                        method text, raw_text text, cv_json text, cost_json text);
      create table runs (id text primary key, kind text, cv_id text, parent_id text,
                         created_at text, expires_at text, status text, request_json text,
                         estimate_json text, result_json text, cost_json text, error text);
      insert into cvs values ('old', '2026-01-01', '2999-01-01', 'en', 'text', 'r', '{}', '{}');
    """)
    db.commit()
    db.close()
    s = Settings(_env_file=None, data_dir=tmp_path)
    store = UserStore(s)
    assert store.get_cv("old") is None
    assert store.get_cv("old", owner="user_a") is None
    assert store.sweep() == 0


# ---- "Delete my data" from any device: needs no CV id kept in a browser ----
def test_delete_my_data_removes_every_cv_run_and_file_of_the_caller(client, engine, a):
    assert client.delete("/me/data", headers=A).status_code == 204
    assert client.get(f"/cv/{a['cv']}", headers=A).status_code == 404
    assert client.get(f"/runs/{a['run']}", headers=A).status_code == 404
    assert client.get(a["pdf"], headers=A).status_code == 404
    assert not engine.store.files_dir(a["cv"]).exists()


def test_delete_my_data_leaves_other_users_alone(client, a):
    theirs = upload(client, B).json()["cv_id"]
    client.delete("/me/data", headers=A)
    assert client.get(f"/cv/{theirs}", headers=B).status_code == 200


def test_delete_my_data_with_nothing_stored_still_succeeds(client):
    assert client.delete("/me/data", headers=B).status_code == 204


def test_delete_my_data_keeps_the_allowance_used(client, engine, a):
    client.delete("/me/data", headers=A)
    assert client.get("/me", headers=A).json()["free_searches_left"] == 0

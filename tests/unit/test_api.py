from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobcv.api.app import create_app
from jobcv.config import Settings
from jobcv.pipeline.engine import Engine
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]


@pytest.fixture
def client(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render,
                    synchronous=True)
    with TestClient(create_app(engine)) as c:
        yield c


def upload(client, name="cv_teacher_en.pdf"):
    return client.post("/cv", files={"file": (name, (FX / name).read_bytes(), "application/pdf")})


def test_full_flow_over_http(client):
    r = upload(client)
    assert r.status_code == 201 and r.json()["language"] == "en"
    cv_id = r.json()["cv_id"]

    r = client.post("/search", json={"cv_id": cv_id, "title": "QA Engineer",
                                     "country": "United Arab Emirates", "max_results": 5})
    assert r.status_code == 202
    body = r.json()
    assert body["estimate"]["within_cap"] is True and body["estimate"]["total_usd"] > 0

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == "done" and run["last_updated"]
    first = run["jobs"][0]
    assert {"score", "reasons", "gaps", "matched_skills"} <= set(first["match"])

    r = client.post("/tailor", json={"run_id": body["run_id"], "job_ids": [first["job"]["id"]]})
    assert r.status_code == 202
    t = client.get(f"/tailor/{r.json()['run_id']}").json()
    assert t["status"] == "done" and t["results"][0]["review_status"] == "PASS"
    pdf = client.get(t["results"][0]["pdf_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"

    assert client.delete(f"/cv/{cv_id}").status_code == 204
    assert client.get(f"/runs/{body['run_id']}").status_code == 404
    assert client.get(t["results"][0]["pdf_url"]).status_code == 404
    assert client.delete(f"/cv/{cv_id}").status_code == 404


def test_rejects_non_pdf(client):
    r = client.post("/cv", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400


def test_rejects_unknown_country(client):
    r = client.post("/search", json={"cv_id": "x", "title": "QA", "country": "Middle East"})
    assert r.status_code == 422


def test_unknown_ids_are_404(client):
    assert client.get("/runs/nope").status_code == 404
    assert client.get("/tailor/nope").status_code == 404
    assert client.post("/search", json={"cv_id": "nope", "title": "QA",
                                        "country": "Germany"}).status_code == 404


def test_tailor_with_bad_job_id_is_400(client):
    cv_id = upload(client).json()["cv_id"]
    run_id = client.post("/search", json={"cv_id": cv_id, "title": "QA",
                                          "country": "United Arab Emirates",
                                          "max_results": 3}).json()["run_id"]
    r = client.post("/tailor", json={"run_id": run_id, "job_ids": ["linkedin:nope"]})
    assert r.status_code == 400


def test_search_runs_in_background_worker(tmp_path):
    import time

    s = Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render)
    with TestClient(create_app(engine)) as c:
        cv_id = upload(c).json()["cv_id"]
        run_id = c.post("/search", json={"cv_id": cv_id, "title": "QA",
                                         "country": "United Arab Emirates",
                                         "max_results": 3}).json()["run_id"]
        for _ in range(100):
            status = c.get(f"/runs/{run_id}").json()["status"]
            if status not in ("queued", "running"):
                break
            time.sleep(0.05)
        assert status == "done"

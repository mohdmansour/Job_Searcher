"""Regenerating one tailored CV with suggestions the user confirmed (ticked, details optional).
Each tailored CV gets one free redo; a redo can't be redone for free; failures give it back."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobcv.accounts import Refused
from jobcv.agents.base import LLMReply
from jobcv.api.app import create_app
from jobcv.config import Settings
from jobcv.pipeline.engine import Engine, NotFound, confirmed_facts
from jobcv.schemas import EditResult, SearchQuery, Suggestion
from tests.unit.test_engine import MASTER, FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
PDF = (FX / "cv_teacher_en.pdf").read_bytes()
QUERY = SearchQuery(title="QA", country="United Arab Emirates", max_results=5)
PYTHON = [("Python", "2 years of automation scripts at Acme")]


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata",
                    unlimited_user_ids=["owner"])


class Recorder:
    """Fake LLM that remembers what the editor was told and suggests one item."""

    def __init__(self):
        self.editor_prompts: list[str] = []

    def __call__(self, spec, model, prompt, out):
        if spec.name == "editor":
            self.editor_prompts.append(prompt)
            return LLMReply(raw="", usage=fake_llm(spec, model, prompt, out).usage,
                            parsed=EditResult(tailored_cv=MASTER, suggestions=[
                                Suggestion(label="Python", text="If you use Python, add it.")]))
        return fake_llm(spec, model, prompt, out)


def tailored(s, who="u", renderer=fake_render):
    """A user with one tailored CV. Returns the engine, the recorder, tailor id and job id."""
    llm = Recorder()
    engine = Engine(s, source=FixtureSource(), llm=llm, renderer=renderer, synchronous=True)
    cv_id = engine.add_cv(PDF, owner=who)
    run_id, _ = engine.start_search(cv_id, QUERY, owner=who)
    job_id = engine.get_search(run_id, who)["result"]["jobs"][0]["job"]["id"]
    tailor_id, _ = engine.start_tailor(run_id, [job_id], owner=who)
    return engine, llm, tailor_id, job_id


# ---------------- what the editor is told ----------------
def test_confirmed_items_become_facts_the_editor_may_use():
    text = confirmed_facts([("Python", "2 years of automation scripts at Acme"), ("VLANs", "")])
    assert "- Python: 2 years of automation scripts at Acme" in text and "- VLANs" in text
    assert "confirms" in text.lower()


def test_a_redo_sends_the_confirmed_items_to_the_editor(s):
    engine, llm, tailor_id, job_id = tailored(s)
    engine.start_redo(tailor_id, job_id, PYTHON, owner="u")
    assert "2 years of automation scripts at Acme" in llm.editor_prompts[-1]
    assert "2 years of automation" not in llm.editor_prompts[0]  # only the redo got it


# ---------------- one free redo per tailored CV ----------------
def test_the_first_redo_uses_no_allowance(s):
    engine, _, tailor_id, job_id = tailored(s)
    assert engine.accounts.status("u")["free_tailors_left"] == 0
    redo_id, _ = engine.start_redo(tailor_id, job_id, PYTHON, owner="u")
    assert engine.get_tailor(redo_id, "u")["result"][0]["pdf"]
    assert engine.accounts.status("u")["free_tailors_left"] == 0


def test_a_second_redo_of_the_same_cv_is_refused(s):
    engine, _, tailor_id, job_id = tailored(s)
    engine.start_redo(tailor_id, job_id, PYTHON, owner="u")
    with pytest.raises(Refused, match="redo_used"):
        engine.start_redo(tailor_id, job_id, PYTHON, owner="u")


def test_a_redo_cannot_itself_be_redone_for_free(s):
    engine, _, tailor_id, job_id = tailored(s)
    redo_id, _ = engine.start_redo(tailor_id, job_id, PYTHON, owner="u")
    with pytest.raises(Refused, match="redo_used"):
        engine.start_redo(redo_id, job_id, PYTHON, owner="u")


def test_a_redo_that_makes_no_pdf_gives_the_redo_back(s):
    engine, _, tailor_id, job_id = tailored(s)
    good = engine.renderer

    def broken(cv, path):
        raise RuntimeError("chromium crashed")

    engine.renderer = broken
    engine.start_redo(tailor_id, job_id, PYTHON, owner="u")
    engine.renderer = good
    engine.start_redo(tailor_id, job_id, PYTHON, owner="u")  # allowed again


def test_an_owner_account_can_redo_as_often_as_it_likes(s):
    engine, _, tailor_id, job_id = tailored(s, who="owner")
    for _ in range(3):
        engine.start_redo(tailor_id, job_id, PYTHON, owner="owner")


# ---------------- what can't be redone ----------------
def test_a_job_that_this_run_did_not_produce_is_refused(s):
    engine, _, tailor_id, _ = tailored(s)
    with pytest.raises(ValueError):
        engine.start_redo(tailor_id, "linkedin:not-in-this-run", PYTHON, owner="u")


def test_nothing_confirmed_is_refused(s):
    engine, _, tailor_id, job_id = tailored(s)
    with pytest.raises(ValueError):
        engine.start_redo(tailor_id, job_id, [], owner="u")


def test_another_users_cv_cannot_be_redone(s):
    engine, _, tailor_id, job_id = tailored(s)
    with pytest.raises(NotFound):
        engine.start_redo(tailor_id, job_id, PYTHON, owner="someone_else")


# ---------------- over HTTP ----------------
U = {"X-Test-User": "user_u"}


@pytest.fixture
def client(s):
    llm = Recorder()
    engine = Engine(s, source=FixtureSource(), llm=llm, renderer=fake_render, synchronous=True)
    with TestClient(create_app(engine, verifier=lambda r: r.headers.get("X-Test-User"))) as c:
        yield c


def http_tailored(client):
    cv_id = client.post("/cv", headers=U, files={"file": ("cv.pdf", PDF, "application/pdf")}).json()["cv_id"]
    run_id = client.post("/search", headers=U, json={
        "cv_id": cv_id, "title": "QA", "country": "United Arab Emirates", "max_results": 3}).json()["run_id"]
    job_id = client.get(f"/runs/{run_id}", headers=U).json()["jobs"][0]["job"]["id"]
    tailor_id = client.post("/tailor", headers=U, json={"run_id": run_id, "job_ids": [job_id]}).json()["run_id"]
    return tailor_id, job_id


def test_results_carry_structured_suggestions_and_whether_a_redo_is_free(client):
    tailor_id, _ = http_tailored(client)
    result = client.get(f"/tailor/{tailor_id}", headers=U).json()["results"][0]
    assert result["suggestions"] == [{"label": "Python", "text": "If you use Python, add it.", "kind": "add"}]
    assert result["redo_available"] is True


def test_redo_over_http_then_it_is_used(client):
    tailor_id, job_id = http_tailored(client)
    body = {"job_id": job_id, "confirmed": [{"label": "Python", "details": "2 years"}]}
    r = client.post(f"/tailor/{tailor_id}/redo", headers=U, json=body)
    assert r.status_code == 202
    assert client.get(f"/tailor/{tailor_id}", headers=U).json()["results"][0]["redo_available"] is False
    again = client.post(f"/tailor/{tailor_id}/redo", headers=U, json=body)
    assert again.status_code == 403 and again.json() == {"detail": {"code": "redo_used"}}
    redo = client.get(f"/tailor/{r.json()['run_id']}", headers=U).json()["results"][0]
    assert redo["redo_available"] is False  # a redo's result is final for free accounts


@pytest.mark.parametrize("confirmed", [[], [{"label": ""}], [{"label": "x" * 121}],
                                       [{"label": "a", "details": "y" * 501}],
                                       [{"label": f"s{i}"} for i in range(9)]])
def test_redo_input_is_limited(client, confirmed):
    tailor_id, job_id = http_tailored(client)
    r = client.post(f"/tailor/{tailor_id}/redo", headers=U, json={"job_id": job_id, "confirmed": confirmed})
    assert r.status_code == 422


def test_old_plain_text_suggestions_still_read():
    assert Suggestion.from_any("Add the dates.") == Suggestion(label="Add the dates.", text="Add the dates.")

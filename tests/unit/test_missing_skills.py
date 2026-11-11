"""Before tailoring, the user can tick the job's missing skills they really have (details
optional), so the first CV already includes them and no regeneration is needed."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobcv.agents.base import LLMReply
from jobcv.agents.scorer import MAX_MISSING, score_job
from jobcv.agents.scorer import PROMPT as SCORE_PROMPT
from jobcv.api.app import create_app
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.pipeline.engine import Engine
from jobcv.schemas import CV, MatchResult, SearchQuery, Usage
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render
from tests.unit.test_tailoring import QA_JOB

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
PDF = (FX / "cv_teacher_en.pdf").read_bytes()


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")


# ---------------- the scorer lists missing skills, one per item ----------------
def test_a_match_made_before_this_has_no_missing_skills():
    m = MatchResult(score=10, reasons=["r"], matched_skills=[], gaps=["g"])
    assert m.missing_skills == []


def test_the_scorer_is_asked_for_one_skill_per_item():
    assert "missing_skills" in SCORE_PROMPT and "ONE" in SCORE_PROMPT


def test_missing_skills_are_trimmed_deduplicated_short_and_capped(s):
    messy = ["  Python ", "python", "", "VLANs", "x" * 200] + [f"Skill {i}" for i in range(20)]

    def llm(spec, model, prompt, out):
        return LLMReply(raw="", usage=Usage(), parsed=MatchResult(
            score=30, reasons=["r"], matched_skills=[], gaps=["g"], missing_skills=messy))

    skills = score_job(CV(), QA_JOB, s, CostMeter(s), llm=llm).missing_skills
    assert skills[:2] == ["Python", "VLANs"]
    assert len(skills) == MAX_MISSING and all(0 < len(x) <= 60 for x in skills)


# ---------------- what was ticked reaches the editor ----------------
class Recorder:
    def __init__(self):
        self.editor_prompts: list[str] = []

    def __call__(self, spec, model, prompt, out):
        if spec.name == "editor":
            self.editor_prompts.append(prompt)
        return fake_llm(spec, model, prompt, out)


def searched(s):
    llm = Recorder()
    engine = Engine(s, source=FixtureSource(), llm=llm, renderer=fake_render, synchronous=True)
    cv_id = engine.add_cv(PDF, owner="u")
    run_id, _ = engine.start_search(cv_id, SearchQuery(title="QA", country="United Arab Emirates",
                                                       max_results=3), owner="u")
    job_id = engine.get_search(run_id, "u")["result"]["jobs"][0]["job"]["id"]
    return engine, llm, run_id, job_id


def test_ticked_skills_and_extra_info_both_reach_the_editor(s):
    engine, llm, run_id, job_id = searched(s)
    engine.start_tailor(run_id, [job_id], "I volunteer at a code club.", owner="u",
                        confirmed=[("Python", "2 years of scripts at Acme"), ("VLANs", "")])
    prompt = llm.editor_prompts[-1]
    assert "I volunteer at a code club." in prompt
    assert "- Python: 2 years of scripts at Acme" in prompt and "- VLANs" in prompt


def test_nothing_ticked_adds_nothing(s):
    engine, llm, run_id, job_id = searched(s)
    engine.start_tailor(run_id, [job_id], owner="u")
    assert "confirms" not in llm.editor_prompts[-1].lower()


# ---------------- over HTTP ----------------
U = {"X-Test-User": "user_u"}


@pytest.fixture
def client(s):
    llm = Recorder()
    engine = Engine(s, source=FixtureSource(), llm=llm, renderer=fake_render, synchronous=True)
    with TestClient(create_app(engine, verifier=lambda r: r.headers.get("X-Test-User"))) as c:
        c.llm = llm
        yield c


def http_searched(client):
    cv_id = client.post("/cv", headers=U, files={"file": ("cv.pdf", PDF, "application/pdf")}).json()["cv_id"]
    run_id = client.post("/search", headers=U, json={
        "cv_id": cv_id, "title": "QA", "country": "United Arab Emirates", "max_results": 3}).json()["run_id"]
    job_id = client.get(f"/runs/{run_id}", headers=U).json()["jobs"][0]["job"]["id"]
    return run_id, job_id


def test_tailor_accepts_ticked_skills(client):
    run_id, job_id = http_searched(client)
    r = client.post("/tailor", headers=U, json={
        "run_id": run_id, "job_ids": [job_id], "confirmed": [{"label": "Python", "details": "2 years"}]})
    assert r.status_code == 202
    assert "- Python: 2 years" in client.llm.editor_prompts[-1]


@pytest.mark.parametrize("confirmed", [[{"label": ""}], [{"label": "x" * 121}],
                                       [{"label": "a", "details": "y" * 501}],
                                       [{"label": f"s{i}"} for i in range(16)]])
def test_ticked_skills_are_limited(client, confirmed):
    run_id, job_id = http_searched(client)
    r = client.post("/tailor", headers=U, json={"run_id": run_id, "job_ids": [job_id],
                                                "confirmed": confirmed})
    assert r.status_code == 422

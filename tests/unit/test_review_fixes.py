"""Regression tests for problems found in the code and security reviews."""

import io
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from jobcv.agents.base import DATA_ONLY_RULE, AgentSpec, LLMReply, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.cv.ingest import CvTooLarge, extract_cv_text
from jobcv.pipeline.engine import Engine
from jobcv.pipeline.tailor_loop import _squash, drop_flagged_summary_sentences, merge_change_log
from jobcv.schemas import CV, ChangeLogEntry, Country, SearchQuery, Usage, Violation
from jobcv.store import UserStore
from tests.unit.test_api import client, upload  # noqa: F401
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]


def blank_pdf(pages: int, size: float = 300) -> bytes:
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(size, size)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")


# ---- a flagged item that also exists outside the summary stays flagged ----
def test_invented_skill_keeps_its_warning_when_the_summary_also_mentions_it():
    adapted = CV.model_validate({"language": "en", "summary": "Tester. Skilled in Selenium daily.",
                                 "skills": ["Selenium"]})
    flag = Violation(adapted_text="Selenium", problem="A", explanation="x", suggested_fix="remove")
    _, left, _ = drop_flagged_summary_sentences(CV.model_validate({"language": "en"}), adapted, [flag], [])
    assert left == [flag]


# ---- change log ----
def test_a_phrase_in_two_entries_changes_neither():
    log = [ChangeLogEntry(original="A", adapted="manual testing of apps", why_faithful="w"),
           ChangeLogEntry(original="B", adapted="manual testing of sites", why_faithful="w")]
    fix = [ChangeLogEntry(original="manual testing", adapted="testing", why_faithful="w")]
    assert merge_change_log(log, fix, _squash("A B")) == log


# ---- untrusted text ----
def test_every_agent_is_told_that_documents_are_data(s):
    seen = []

    def llm(spec, model, prompt, out):
        seen.append(prompt)
        return LLMReply(raw="", parsed=CV.model_validate({"language": "en"}), usage=Usage())

    spec = AgentSpec(name="parser", role="r", goal="g", backstory="b", strong=True)
    run_agent(spec, "JOB TEXT", CV, s, CostMeter(s), llm=llm)
    assert seen[0].startswith(DATA_ONLY_RULE) and seen[0].endswith("JOB TEXT")


# ---- size limits ----
def test_too_many_pages_is_refused_before_any_ocr(s):
    with pytest.raises(CvTooLarge, match="pages"):
        extract_cv_text(blank_pdf(s.max_cv_pages + 1), s)


def test_giant_page_is_refused(s):
    with pytest.raises(CvTooLarge, match="page"):
        extract_cv_text(blank_pdf(1, size=5000), s)


def test_too_much_text_is_refused(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path, max_cv_chars=50)
    with pytest.raises(CvTooLarge, match="text"):
        extract_cv_text((FX / "cv_teacher_en.pdf").read_bytes(), s)


def test_a_normal_cv_is_within_the_limits(s):
    assert extract_cv_text((FX / "cv_teacher_en.pdf").read_bytes(), s).pages >= 1


def test_api_answers_413_for_too_many_pages(client):  # noqa: F811
    r = client.post("/cv", files={"file": ("x.pdf", blank_pdf(16), "application/pdf")})
    assert r.status_code == 413


def test_api_refuses_an_overlong_extra_title(client):  # noqa: F811
    r = client.post("/search", json={"cv_id": "x", "title": "QA", "more_titles": ["a" * 201],
                                     "country": "Germany"})
    assert r.status_code == 422


# ---- deletion during tailoring ----
def _ready_engine(s, renderer):
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=renderer, synchronous=True)
    cv_id = engine.add_cv((FX / "cv_teacher_en.pdf").read_bytes())
    q = SearchQuery(title="QA Engineer", country=Country.UAE, max_results=3)
    run_id, _ = engine.start_search(cv_id, q)
    return engine, cv_id, run_id, [j["job"]["id"] for j in engine.get_search(run_id)["result"]["jobs"]]


def test_deleting_during_tailoring_leaves_no_file_and_stops(s):
    rendered = []

    def render_then_delete(cv, path):
        rendered.append(path)
        out = fake_render(cv, path)
        engine.delete_cv(cv_id)  # the user deletes while this PDF is being written
        fake_render(cv, path)
        return out

    engine, cv_id, run_id, job_ids = _ready_engine(s, render_then_delete)
    engine.start_tailor(run_id, job_ids[:2])
    assert not engine.store.files_dir(cv_id).exists()
    assert len(rendered) == 1


def test_sweep_removes_files_with_no_cv_record(s):
    store = UserStore(s)
    orphan = s.user_files_dir / "gone" / "run"
    orphan.mkdir(parents=True)
    (orphan / "cv.pdf").write_bytes(b"%PDF")
    store.sweep()
    assert not (s.user_files_dir / "gone").exists()


def test_sweep_keeps_files_of_a_live_cv(s):
    store = UserStore(s)
    cv_id = store.add_cv("en", "text", "raw", "{}", {})
    folder = store.files_dir(cv_id) / "run"
    folder.mkdir(parents=True)
    store.sweep()
    assert folder.exists()

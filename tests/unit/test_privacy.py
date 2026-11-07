"""GDPR guard: CV content must never reach logs, and must not be stored in the job cache."""

import logging
from pathlib import Path

from jobcv.config import Settings
from jobcv.pipeline.engine import Engine
from jobcv.schemas import Country, SearchQuery
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
CV_SECRETS = ["Sarah", "Thompson", "Oakfield", "sarah.thompson@example.com", "7700 900123",
              "Marked and graded", "PGCE"]


def test_full_flow_logs_no_cv_content(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)  # every logger, most verbose level
    s = Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render,
                    synchronous=True)
    cv_id = engine.add_cv((FX / "cv_teacher_en.pdf").read_bytes())
    run_id, _ = engine.start_search(cv_id, SearchQuery(title="QA", country=Country.UAE,
                                                       max_results=3))
    job_id = engine.get_search(run_id)["result"]["jobs"][0]["job"]["id"]
    engine.start_tailor(run_id, [job_id], extra_info="Sarah used Jira at Oakfield")
    assert caplog.records, "expected some log lines"
    leaked = [w for w in CV_SECRETS if w in caplog.text]
    assert leaked == [], f"CV content in logs: {leaked}"
    # the job cache file never contains CV data
    cache = s.jobs_cache_db.read_bytes()
    assert not [w for w in CV_SECRETS if w.encode() in cache]


def test_failed_run_logs_error_type_not_message(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    s = Settings(_env_file=None, data_dir=tmp_path, tessdata_dir=ROOT / "tessdata")

    def boom(spec, model, prompt, out):
        if spec.name == "parser":
            return fake_llm(spec, model, prompt, out)
        raise RuntimeError("Sarah Thompson at Oakfield")  # message carries CV text

    engine = Engine(s, source=FixtureSource(), llm=boom, renderer=fake_render, synchronous=True)
    cv_id = engine.add_cv((FX / "cv_teacher_en.pdf").read_bytes())
    run_id, _ = engine.start_search(cv_id, SearchQuery(title="QA", country=Country.UAE,
                                                       max_results=2))
    run = engine.get_search(run_id)
    assert run["status"] == "done"  # one failing job does not sink the run
    assert {j["error"] for j in run["result"]["jobs"]} == {"RuntimeError"}  # type, not message
    assert "Oakfield" not in caplog.text and "Oakfield" not in str(run)

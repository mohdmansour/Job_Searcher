from datetime import UTC, datetime

import pytest

from jobcv.agents.base import AgentOutputError, LLMReply
from jobcv.agents.scorer import rank_jobs, score_job
from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter
from jobcv.schemas import CV, Job, MatchResult, Usage


def job(n, desc="desc"):
    return Job(id=f"linkedin:{n}", source="linkedin", title=f"Role {n}", company="Co",
               location="Dubai", remote=False, description=desc, url=f"https://x/{n}",
               posted_at=None, fetched_at=datetime.now(UTC), language="en")


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path)


def fake_scores(scores: dict[str, int]):
    def llm(spec, model, prompt, out):
        n = next(k for k in scores if f"Role {k}" in prompt)
        return LLMReply(raw="", parsed=MatchResult(score=scores[n], reasons=["r"],
                        matched_skills=[], gaps=["g"]), usage=Usage(input_tokens=1))
    return llm


def test_score_job_uses_cheap_model_and_sends_cv_and_job(s):
    seen = {}

    def llm(spec, model, prompt, out):
        seen.update(model=model, prompt=prompt)
        return LLMReply(raw="", parsed=MatchResult(score=10, reasons=[], matched_skills=[],
                                                   gaps=[]), usage=Usage())

    score_job(CV(summary="Teacher of Year 3"), job(1, "Need Selenium"), s, CostMeter(s), llm=llm)
    assert seen["model"] == "gpt-5.4-mini"
    assert "Teacher of Year 3" in seen["prompt"] and "Need Selenium" in seen["prompt"]
    assert "honest" in seen["prompt"].lower()


def test_long_descriptions_are_truncated(s):
    seen = {}

    def llm(spec, model, prompt, out):
        seen["len"] = len(prompt)
        return LLMReply(raw="", parsed=MatchResult(score=1, reasons=[], matched_skills=[],
                                                   gaps=[]), usage=Usage())

    score_job(CV(), job(1, "x" * 50_000), s, CostMeter(s), llm=llm)
    assert seen["len"] < 15_000


def test_rank_orders_by_score_desc(s):
    ranked = rank_jobs(CV(), [job(1), job(2), job(3)], s, CostMeter(s),
                       llm=fake_scores({"1": 20, "2": 90, "3": 55}))
    assert [r.job.id for r in ranked] == ["linkedin:2", "linkedin:3", "linkedin:1"]
    assert ranked[0].match.score == 90


def test_one_failed_job_is_kept_last_with_error(s):
    def llm(spec, model, prompt, out):
        if "Role 2" in prompt:
            return LLMReply(raw="garbage", parsed=None, usage=Usage())
        return fake_scores({"1": 40, "3": 70})(spec, model, prompt, out)

    ranked = rank_jobs(CV(), [job(1), job(2), job(3)], s, CostMeter(s), llm=llm)
    assert [r.job.id for r in ranked] == ["linkedin:3", "linkedin:1", "linkedin:2"]
    assert ranked[-1].match is None and ranked[-1].error


def test_cost_cap_stops_scoring(s):
    tight = s.model_copy(update={"max_cost_per_run_usd": 0.0})
    with pytest.raises(CostCapExceeded):
        rank_jobs(CV(), [job(1)], tight, CostMeter(tight), llm=fake_scores({"1": 1}))


def test_agent_output_error_type_is_reused():
    assert issubclass(AgentOutputError, RuntimeError)


def test_timeout_on_one_job_does_not_sink_the_run(s):
    def llm(spec, model, prompt, out):
        if "Role 2" in prompt:
            raise TimeoutError("read timed out")
        return fake_scores({"1": 40, "3": 70})(spec, model, prompt, out)

    ranked = rank_jobs(CV(), [job(1), job(2), job(3)], s, CostMeter(s), llm=llm)
    assert [r.job.id for r in ranked][-1] == "linkedin:2"
    assert ranked[-1].error == "TimeoutError"

import pytest

from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter, llm_cost
from jobcv.schemas import Usage


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path)


def test_llm_cost_uses_model_prices(s):
    u = Usage(input_tokens=1_000_000, cached_input_tokens=0, output_tokens=1_000_000)
    assert llm_cost(s, "gpt-5.4", u) == pytest.approx(2.50 + 15.00)


def test_cached_tokens_are_billed_at_cached_rate(s):
    # OpenAI counts cached tokens inside input_tokens
    u = Usage(input_tokens=1_000_000, cached_input_tokens=1_000_000, output_tokens=0)
    assert llm_cost(s, "gpt-5.4-mini", u) == pytest.approx(0.075)


def test_unknown_model_price_fails_loudly(s):
    with pytest.raises(KeyError, match="price"):
        llm_cost(s, "gpt-unknown", Usage(input_tokens=1))


def test_actual_cost_and_user_price_are_separate(s):
    m = CostMeter(s)
    m.add_apify(0.006)
    m.add_llm("scorer", "gpt-5.4-mini", Usage(input_tokens=10_000, output_tokens=1_000))
    r = m.record()
    expected_llm = 10_000 * 0.75 / 1e6 + 1_000 * 4.50 / 1e6
    assert r.apify_usd == pytest.approx(0.006)
    assert r.llm_usd_by_agent["scorer"] == pytest.approx(expected_llm)
    assert r.actual_cost_usd == pytest.approx(0.006 + expected_llm)
    assert r.price_to_user_usd == pytest.approx(r.actual_cost_usd * 3.0)
    assert r.tokens_by_agent["scorer"].input_tokens == 10_000


def test_cap_stops_spend_before_it_happens(s):
    m = CostMeter(s.model_copy(update={"max_cost_per_run_usd": 0.01}))
    m.add_apify(0.008)
    m.check(0.002)  # exactly at the cap is allowed
    with pytest.raises(CostCapExceeded):
        m.check(0.0021)


def test_estimate_search_covers_apify_and_scoring(s):
    m = CostMeter(s)
    est = m.estimate_search(n_jobs=10, apify_usd=0.0151)
    assert est.apify_usd == pytest.approx(0.0151)
    assert est.llm_usd > 0
    assert est.total_usd == pytest.approx(est.apify_usd + est.llm_usd)
    assert est.within_cap is True


def test_estimate_tailor_is_worst_case_over_all_attempts(s):
    m = CostMeter(s)
    one = m.estimate_tailor(n_jobs=1)
    two = m.estimate_tailor(n_jobs=2)
    assert two.llm_usd == pytest.approx(2 * one.llm_usd)
    fewer = CostMeter(s.model_copy(update={"max_review_attempts": 1})).estimate_tailor(1)
    assert fewer.llm_usd < one.llm_usd


def test_estimate_flags_runs_over_cap(s):
    m = CostMeter(s.model_copy(update={"max_cost_per_run_usd": 0.05}))
    assert m.estimate_tailor(n_jobs=20).within_cap is False


def test_check_llm_estimates_before_call(s):
    m = CostMeter(s.model_copy(update={"max_cost_per_run_usd": 0.0001}))
    with pytest.raises(CostCapExceeded):
        m.check_llm("editor", "gpt-5.4")


def test_cost_cap_stops_a_search_before_apify_is_called(s):
    from jobcv.jobs.cache import JobCache, JobSearchService
    from jobcv.schemas import Country, SearchQuery

    class Source:
        name = "linkedin"
        calls = 0

        def estimate_cost(self, q, limit):
            return 0.0015 * limit

        def search(self, q, limit, recent_only=False):
            Source.calls += 1
            raise AssertionError("must not be called")

    tight = s.model_copy(update={"max_cost_per_run_usd": 0.01})
    svc = JobSearchService(Source(), JobCache(tight.jobs_cache_db), tight)
    with pytest.raises(CostCapExceeded):
        svc.search(SearchQuery(title="QA", country=Country.UAE, max_results=50),
                   meter=CostMeter(tight))
    assert Source.calls == 0

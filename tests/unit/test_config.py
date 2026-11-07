from pathlib import Path

from jobcv.config import Settings


def make(tmp_path: Path, **env) -> Settings:
    # _env_file=None: tests never read the real .env (it holds secrets)
    return Settings(_env_file=None, data_dir=tmp_path, **env)


def test_defaults_match_spec(tmp_path):
    s = make(tmp_path)
    assert s.strong_model == "gpt-5.4"
    assert s.cheap_model == "gpt-5.4-mini"
    assert s.job_cache_ttl_hours == 4
    assert s.job_max_age_days == 30
    assert s.cv_ttl_hours == 24
    assert s.max_cost_per_run_usd == 1.0
    assert s.markup == 3.0
    assert s.max_review_attempts == 3
    assert s.apify_actor_id == "bebity/linkedin-jobs-scraper"


def test_model_prices_are_configured_for_both_models(tmp_path):
    s = make(tmp_path)
    for model in (s.strong_model, s.cheap_model):
        price = s.model_prices[model]
        assert price.input_per_1m > 0 and price.output_per_1m > 0


def test_env_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBCV_MARKUP", "2.5")
    monkeypatch.setenv("JOBCV_JOB_CACHE_TTL_HOURS", "6")
    s = make(tmp_path)
    assert s.markup == 2.5
    assert s.job_cache_ttl_hours == 6


def test_secrets_come_from_unprefixed_env_names(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("APIFY_TOKEN", "apify-test")
    s = make(tmp_path)
    assert s.openai_api_key.get_secret_value() == "sk-test"
    assert s.apify_token.get_secret_value() == "apify-test"
    assert "sk-test" not in repr(s)  # secrets never printed


def test_job_cache_and_user_db_are_separate_files(tmp_path):
    s = make(tmp_path)
    assert s.jobs_cache_db != s.user_db
    assert s.jobs_cache_db.parent == tmp_path

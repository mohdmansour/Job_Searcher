"""All tunable settings. Values come from env vars (prefix JOBCV_) or `.env`.

Secrets use their conventional names (OPENAI_API_KEY, APIFY_TOKEN) and are SecretStr,
so they never appear in repr/logs.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice(BaseModel):
    """USD per 1M tokens. Update from https://developers.openai.com/api/docs/pricing"""

    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float


DEFAULT_MODEL_PRICES = {
    # Read from OpenAI pricing page on 2026-11-08 (standard tier).
    "gpt-5.4": ModelPrice(input_per_1m=2.50, cached_input_per_1m=0.25, output_per_1m=15.00),
    "gpt-5.4-mini": ModelPrice(input_per_1m=0.75, cached_input_per_1m=0.075, output_per_1m=4.50),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBCV_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- secrets ---
    openai_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("OPENAI_API_KEY", "JOBCV_OPENAI_API_KEY")
    )
    apify_token: SecretStr | None = Field(
        None, validation_alias=AliasChoices("APIFY_TOKEN", "JOBCV_APIFY_TOKEN")
    )

    # --- LLM (provider is always OpenAI) ---
    strong_model: str = "gpt-5.4"  # CV Parser, CV Editor, CV Reviewer
    cheap_model: str = "gpt-5.4-mini"  # Match Scorer
    model_prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_MODEL_PRICES))
    max_review_attempts: int = 3
    llm_timeout_secs: float = 120  # per HTTP call; a hung call was seen live (no reply >10 min)
    llm_max_retries: int = 2  # OpenAI SDK retries on timeout / connection errors
    # (input, output) tokens per call, used ONLY for pre-run estimates: ~2x the real usage
    # measured in the live tests on 2026-11-08 (parser ~1k/0.4k, edit+review round ~$0.023).
    token_estimates: dict[str, tuple[int, int]] = Field(default_factory=lambda: {
        "parser": (2500, 1000),
        "scorer": (3500, 400),
        "editor": (3000, 1500),
        "reviewer": (4000, 600),
    })

    # --- Apify ---
    apify_actor_id: str = "bebity/linkedin-jobs-scraper"
    apify_price_per_job_usd: float = 0.0015  # FREE tier, read 2026-11-08
    apify_price_per_start_usd: float = 0.00005  # charged once per GB of run memory
    apify_memory_gb: int = 2  # the Actor's default; also used in the cost estimate
    apify_timeout_secs: int = 600

    # --- jobs cache ---
    job_cache_ttl_hours: float = 4
    job_max_age_days: int = 30
    incremental_window: str = "r86400"  # smallest date filter the Actor supports (24h)

    # --- cost meter ---
    max_cost_per_run_usd: float = 1.0
    markup: float = 3.0

    # --- CV / privacy ---
    cv_ttl_hours: float = 24
    ocr_min_chars: int = 200  # below this much extracted text, fall back to OCR
    tesseract_cmd: str = "C:/Program Files/Tesseract-OCR/tesseract.exe"  # or "tesseract" on Linux
    tessdata_dir: Path = Path("tessdata")  # holds eng + ara .traineddata (tessdata_best)

    # --- storage ---
    data_dir: Path = Path("data")

    @property
    def jobs_cache_db(self) -> Path:
        return self.data_dir / "jobs_cache.db"  # public job data only

    @property
    def user_db(self) -> Path:
        return self.data_dir / "user.db"  # CVs, runs, scores (personal data)

    @property
    def user_files_dir(self) -> Path:
        return self.data_dir / "user"


@lru_cache
def get_settings() -> Settings:
    return Settings()

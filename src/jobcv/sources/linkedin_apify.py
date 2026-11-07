"""LinkedIn jobs via the Apify Actor `bebity/linkedin-jobs-scraper`.

Plain code only — no agent ever calls this. The mapper is the only place that knows the
Actor's output fields. Poster names/photos and other personal fields are deliberately dropped.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from jobcv.config import Settings
from jobcv.schemas import Job, SearchQuery
from jobcv.sources.base import SourceResult, utc_from_ms
from jobcv.sources.location import resolve_location
from jobcv.text import detect_language

# (actor_id, run_input, max_items, max_charge_usd) -> (items, actual_cost_usd)
ApifyRunner = Callable[[str, dict, int, float], tuple[list[dict], float]]


def build_input(q: SearchQuery, limit: int, recent_window: str | None) -> dict:
    loc = resolve_location(q)
    n_searches = len(loc["locations"])
    rows = max(1, -(-limit // n_searches))  # ceil: rows is PER location search
    run_input = {
        "titles": [q.title],
        **loc,
        "rows": rows,  # never 0: 0 means "everything" for this Actor
        "companyProfile": False,  # paid add-on, not needed
        "enrichCompany": False,  # paid add-on + poster personal data, not needed
    }
    if recent_window:
        run_input["publishedAt"] = recent_window
    return run_input


def map_item(item: dict, fetched_at: datetime, remote_search: bool = False) -> Job | None:
    job_id = str(item.get("id") or "").strip()
    title = (item.get("title") or "").strip()
    description = (item.get("description") or "").strip()
    if not (job_id and title and description):
        return None  # useless for matching
    # postedAtTimestamp is a premium field; the standard output has publishedAt "YYYY-MM-DD".
    posted = utc_from_ms(item.get("postedAtTimestamp")) or _parse_date(item.get("publishedAt"))
    # workType is often empty (seen in the real recording), so also check the location text.
    work_type = f"{item.get('workType') or ''} {item.get('location') or ''}".lower()
    return Job(
        id=f"linkedin:{job_id}",
        source="linkedin",
        title=title,
        company=(item.get("companyName") or "").strip(),
        location=(item.get("location") or "").strip(),
        remote=remote_search or "remote" in work_type,  # remote search => Actor filtered it
        description=description,
        url=f"https://www.linkedin.com/jobs/view/{job_id}",  # canonical; raw URLs vary by country

        posted_at=posted,
        fetched_at=fetched_at,
        language=detect_language(description),
    )


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not re.match(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def charged_cost(run: dict, items_received: int = 0) -> float:
    """USD actually charged for a pay-per-event run: sum(event count x event price).

    Apify's event counts can lag behind (seen live: 4 items reported, 5 charged), so the item
    event is billed at least once per dataset item we actually received."""
    counts = dict(run.get("chargedEventCounts") or {})
    if counts or items_received:
        item_event = "apify-default-dataset-item"
        counts[item_event] = max(counts.get(item_event, 0), items_received)
    events = (((run.get("pricingInfo") or {}).get("pricingPerEvent") or {})
              .get("actorChargeEvents") or {})
    total = sum(n * float(events.get(name, {}).get("eventPriceUsd") or 0) for name, n in counts.items())
    return round(total, 6) if counts else float(run.get("usageTotalUsd") or 0.0)


class LinkedInApifySource:
    name = "linkedin"

    def __init__(self, settings: Settings, runner: ApifyRunner | None = None):
        self.s = settings
        self._runner = runner or self._real_runner

    def estimate_cost(self, q: SearchQuery, limit: int) -> float:
        # One start event per GB of run memory (the real run charged 2 at 2 GB).
        starts = self.s.apify_price_per_start_usd * self.s.apify_memory_gb
        return starts + limit * self.s.apify_price_per_job_usd

    def search(self, q: SearchQuery, limit: int, recent_only: bool = False) -> SourceResult:
        window = self.s.incremental_window if recent_only else None
        run_input = build_input(q, limit, window)
        max_charge = self.estimate_cost(q, limit)
        items, cost = self._runner(self.s.apify_actor_id, run_input, limit, max_charge)
        now = datetime.now(UTC)
        jobs = [j for j in (map_item(i, now, q.remote) for i in items) if j][:limit]
        return SourceResult(jobs=jobs, cost_usd=cost)

    def _real_runner(self, actor_id, run_input, max_items, max_charge):
        from apify_client import ApifyClient

        if not self.s.apify_token:
            raise RuntimeError("APIFY_TOKEN is not set")
        client = ApifyClient(self.s.apify_token.get_secret_value())
        run = client.actor(actor_id).call(
            run_input=run_input,
            max_items=max_items,  # hard bound on billed items
            max_total_charge_usd=Decimal(str(round(max_charge, 5))),
            memory_mbytes=self.s.apify_memory_gb * 1024,
            run_timeout=timedelta(seconds=self.s.apify_timeout_secs),
            wait_duration=timedelta(seconds=self.s.apify_timeout_secs + 60),
            logger=None,
        )
        if run is None:
            raise RuntimeError("Apify run did not finish")
        run = run if isinstance(run, dict) else run.model_dump(by_alias=True)
        if run.get("status") != "SUCCEEDED":
            raise RuntimeError(f"Apify run ended with status {run.get('status')}")
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        # The Run returned by call() can be a snapshot taken before billing settles
        # (real run: 0.0016 reported vs 0.0061 charged). Re-read it, and price the charged events.
        final = client.run(run["id"]).get()
        final = final if isinstance(final, dict) else final.model_dump(by_alias=True)
        return items, charged_cost(final, items_received=len(items))

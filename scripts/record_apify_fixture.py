"""ONE real Apify call (5 jobs) -> tests/fixtures/apify_bebity_5jobs.json.

Run manually only:  uv run python scripts/record_apify_fixture.py
Poster/recruiter personal fields are stripped before saving.
"""

import json
from pathlib import Path

from jobcv.config import Settings
from jobcv.schemas import Country, SearchQuery
from jobcv.sources.linkedin_apify import LinkedInApifySource, build_input

OUT = Path("tests/fixtures/apify_bebity_5jobs.json")
LIMIT = 5


def main() -> None:
    s = Settings()
    src = LinkedInApifySource(s)
    q = SearchQuery(title="QA Engineer", country=Country.UAE, max_results=LIMIT)
    run_input = build_input(q, LIMIT, None)
    print("input:", json.dumps(run_input))
    items, cost = src._real_runner(s.apify_actor_id, run_input, LIMIT, src.estimate_cost(q, LIMIT))
    clean = [{k: v for k, v in it.items() if not k.startswith("poster")} for it in items]
    OUT.write_text(
        json.dumps({"input": run_input, "cost_usd": cost, "items": clean}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"saved {len(clean)} items, reported cost ${cost:.4f}")
    print("fields:", sorted({k for it in clean for k in it}))


if __name__ == "__main__":
    main()

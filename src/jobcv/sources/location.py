"""Location Resolver: SearchQuery -> the location part of the bebity Actor input.

Actor facts (input schema read 2026-11-08):
- `locations` is a list of free-text places; each title x location is one search.
- `workTypes` codes: "1" On-site, "2" Remote, "3" Hybrid.
Remote = remote jobs listed in the chosen country (not worldwide), per the approved spec.
"""

from jobcv.schemas import SearchQuery

REMOTE_WORK_TYPE = "2"


def resolve_location(q: SearchQuery) -> dict:
    country = q.country.value
    seen: set[str] = set()
    locations: list[str] = []
    for city in q.cities:
        key = city.casefold()
        if key not in seen:
            seen.add(key)
            locations.append(f"{city}, {country}")
    out: dict = {"locations": locations or [country]}
    if q.remote:
        out["workTypes"] = [REMOTE_WORK_TYPE]
    return out

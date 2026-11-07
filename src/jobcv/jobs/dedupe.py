"""Deduplicate jobs: exact (id, canonical URL) and fuzzy (normalized title + company + city).

Fuzzy matching lets Phase 2 merge the same posting found on different sources.
"""

import re
from urllib.parse import urlsplit, urlunsplit

from jobcv.schemas import Job
from jobcv.text import normalize

_COMPANY_SUFFIXES = re.compile(
    r"\b(llc|l l c|ltd|limited|inc|gmbh|ag|plc|co|corp|fz llc|fze|fzco|sa|bv|شركه|ذ م م)\b"
)


def canonical_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    host = parts.netloc.lower()
    if host.endswith(".linkedin.com"):
        host = "www.linkedin.com"  # ae.linkedin.com, de.linkedin.com ... are the same job
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, "", ""))


def fuzzy_key(job: Job) -> str:
    company = re.sub(r"\s+", " ", _COMPANY_SUFFIXES.sub(" ", normalize(job.company))).strip()
    city = normalize(job.location.split(",")[0])
    return f"{normalize(job.title)}|{company}|{city}"


def _merge(a: Job, b: Job) -> Job:
    newest, other = (a, b) if a.fetched_at >= b.fetched_at else (b, a)
    longest = max(a.description, b.description, key=len)
    return newest.model_copy(update={
        "description": longest,
        "posted_at": newest.posted_at or other.posted_at,
    })


def dedupe(jobs: list[Job]) -> list[Job]:
    """Merge duplicates; keeps the order in which each distinct job first appeared."""
    merged: list[Job] = []
    index: dict[str, int] = {}  # any key -> position in `merged`
    for job in jobs:
        keys = [f"id:{job.id}", f"url:{canonical_url(job.url)}", f"fz:{fuzzy_key(job)}"]
        hit = next((index[k] for k in keys if k in index), None)
        if hit is None:
            hit = len(merged)
            merged.append(job)
        else:
            merged[hit] = _merge(merged[hit], job)
        for k in keys:
            index.setdefault(k, hit)
    return merged

"""The engine: the fixed Phase 1 flow in plain code. API and CLI both call this.

    add_cv(pdf)                         -> cv_id            (extract/OCR + Parser agent)
    start_search(cv_id, query)          -> run_id, estimate (cache/Apify + Scorer per job)
    start_tailor(search_id, job_ids)    -> run_id, estimate (Editor/Reviewer loop + PDF per job)

Runs execute in a small thread pool (runs take minutes). A run whose estimate is over the
cap is never started (status stopped_cost_cap); the meter also stops a run mid-way.
"""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from jobcv.agents.base import LLMCall
from jobcv.agents.parser import parse_cv
from jobcv.agents.scorer import rank_jobs
from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter
from jobcv.cv.ingest import extract_cv_text
from jobcv.jobs.cache import JobCache, JobSearchService
from jobcv.pdf.render import pdf_filename, render_pdf
from jobcv.pipeline.tailor_loop import tailor_for_job
from jobcv.schemas import CV, Job, SearchQuery
from jobcv.sources.base import JobSource
from jobcv.sources.linkedin_apify import LinkedInApifySource
from jobcv.store import UserStore

log = logging.getLogger(__name__)

QUEUED, RUNNING, DONE, FAILED, STOPPED = "queued", "running", "done", "failed", "stopped_cost_cap"


class NotFound(LookupError):
    pass


class Engine:
    def __init__(
        self,
        settings: Settings,
        source: JobSource | None = None,
        llm: LLMCall | None = None,
        renderer: Callable[[CV, Path], Path] = render_pdf,
        workers: int = 2,
        synchronous: bool = False,  # run jobs inline (CLI, tests)
    ):
        self.s = settings
        self.store = UserStore(settings)
        self.store.fail_interrupted()  # one engine per data dir: leftovers are from a dead process
        self.search_service = JobSearchService(source or LinkedInApifySource(settings),
                                               JobCache(settings.jobs_cache_db), settings)
        self.llm, self.renderer = llm, renderer
        self.synchronous = synchronous
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jobcv")

    def _submit(self, fn, *args) -> Future | None:
        if self.synchronous:
            fn(*args)
            return None
        return self.pool.submit(fn, *args)

    # ---------------- CV ----------------
    def add_cv(self, pdf: bytes) -> str:
        """Blocking: extract text (OCR if needed) and parse. Usually 10-40 seconds."""
        meter = CostMeter(self.s)
        ex = extract_cv_text(pdf, self.s)
        cv = parse_cv(ex.text, ex.language, self.s, meter, llm=self.llm)
        cv_id = self.store.add_cv(ex.language, ex.method, ex.text, cv.model_dump_json(),
                                  meter.record().model_dump(mode="json"))
        log.info("cv %s added: lang=%s method=%s", cv_id, ex.language, ex.method)
        return cv_id

    def get_cv(self, cv_id: str) -> tuple[CV, str]:
        row = self.store.get_cv(cv_id)
        if row is None:
            raise NotFound("cv not found or expired")
        return CV.model_validate_json(row["cv_json"]), row["raw_text"]

    def delete_cv(self, cv_id: str) -> bool:
        return self.store.delete_cv(cv_id)

    # ---------------- search ----------------
    def start_search(self, cv_id: str, q: SearchQuery, force_refresh: bool = False):
        self.get_cv(cv_id)
        meter = CostMeter(self.s)
        apify = self.search_service.source.estimate_cost(q, q.max_results)
        est = meter.estimate_search(q.max_results, apify)
        status = QUEUED if est.within_cap else STOPPED
        run_id = self.store.add_run(
            "search", cv_id, {"query": q.model_dump(mode="json"), "force_refresh": force_refresh},
            est.model_dump(), status)
        if est.within_cap:
            self._submit(self._run_search, run_id, cv_id, q, force_refresh)
        else:
            self.store.update_run(run_id, status=STOPPED, error="estimate exceeds the cost cap")
        return run_id, est

    def _run_search(self, run_id: str, cv_id: str, q: SearchQuery, force_refresh: bool) -> None:
        meter = CostMeter(self.s)
        self.store.update_run(run_id, status=RUNNING)
        try:
            cv, _ = self.get_cv(cv_id)
            res = self.search_service.search(q, meter=meter, force_refresh=force_refresh)
            ranked = rank_jobs(cv, res.jobs, self.s, meter, llm=self.llm)
            result = {
                "last_updated": res.last_updated.isoformat(), "from_cache": res.from_cache,
                "jobs": [{"job": r.job.model_dump(mode="json"),
                          "match": r.match.model_dump() if r.match else None,
                          "error": r.error} for r in ranked],
            }
            self.store.update_run(run_id, status=DONE, result=result,
                                  cost=meter.record().model_dump(mode="json"))
        except CostCapExceeded as e:
            self.store.update_run(run_id, status=STOPPED, error=str(e),
                                  cost=meter.record().model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001 - every run must end in a visible state
            # type only: exception messages (e.g. validation errors) can contain CV text
            log.error("search run %s failed: %s", run_id, type(e).__name__)
            self.store.update_run(run_id, status=FAILED, error=type(e).__name__,
                                  cost=meter.record().model_dump(mode="json"))

    def get_search(self, run_id: str) -> dict:
        run = self.store.get_run(run_id, "search")
        if run is None:
            raise NotFound("run not found or expired")
        return run

    # ---------------- tailor ----------------
    def start_tailor(self, search_run_id: str, job_ids: list[str], extra_info: str = ""):
        search = self.get_search(search_run_id)
        if search["status"] != DONE:
            raise ValueError("search run is not finished")
        jobs = {j["job"]["id"]: Job.model_validate(j["job"]) for j in search["result"]["jobs"]}
        unknown = [j for j in job_ids if j not in jobs]
        if unknown or not job_ids:
            raise ValueError(f"unknown job ids: {unknown}" if unknown else "no jobs selected")
        est = CostMeter(self.s).estimate_tailor(len(job_ids))
        status = QUEUED if est.within_cap else STOPPED
        run_id = self.store.add_run("tailor", search["cv_id"],
                                    {"job_ids": job_ids, "has_extra_info": bool(extra_info)},
                                    est.model_dump(), status, parent_id=search_run_id)
        if est.within_cap:
            # extra_info is personal data: passed in memory only, never stored in the request
            self._submit(self._run_tailor, run_id, search["cv_id"],
                         [jobs[j] for j in job_ids], extra_info)
        else:
            self.store.update_run(run_id, status=STOPPED, error="estimate exceeds the cost cap")
        return run_id, est

    def _run_tailor(self, run_id: str, cv_id: str, jobs: list[Job], extra_info: str) -> None:
        meter = CostMeter(self.s)
        self.store.update_run(run_id, status=RUNNING)
        results: list[dict] = []
        try:
            cv, raw = self.get_cv(cv_id)
            out_dir = self.store.files_dir(cv_id) / run_id
            for job in jobs:
                out = tailor_for_job(cv, raw, job, self.s, meter, extra_info=extra_info,
                                     llm=self.llm)
                pdf = self.renderer(out.tailored_cv, out_dir / pdf_filename(job.title, job.company))
                results.append({**out.model_dump(mode="json"), "pdf": pdf.name})
                self.store.update_run(run_id, status=RUNNING, result=results)  # progress
            self.store.update_run(run_id, status=DONE, result=results,
                                  cost=meter.record().model_dump(mode="json"))
        except CostCapExceeded as e:
            self.store.update_run(run_id, status=STOPPED, result=results, error=str(e),
                                  cost=meter.record().model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001 - every run must end in a visible state
            log.error("tailor run %s failed: %s", run_id, type(e).__name__)
            self.store.update_run(run_id, status=FAILED, result=results, error=type(e).__name__,
                                  cost=meter.record().model_dump(mode="json"))

    def get_tailor(self, run_id: str) -> dict:
        run = self.store.get_run(run_id, "tailor")
        if run is None:
            raise NotFound("run not found or expired")
        return run

    def pdf_path(self, run_id: str, name: str) -> Path:
        run = self.get_tailor(run_id)
        names = {r["pdf"] for r in run["result"] or []}
        if name not in names:  # only files this run produced; no path traversal
            raise NotFound("file not found")
        return self.store.files_dir(run["cv_id"]) / run_id / name

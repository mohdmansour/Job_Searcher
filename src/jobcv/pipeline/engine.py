"""The engine: the fixed Phase 1 flow in plain code. API and CLI both call this.

    add_cv(pdf)                         -> cv_id            (extract/OCR + Parser agent)
    start_search(cv_id, query)          -> run_id, estimate (cache/Apify + Scorer per job)
    start_tailor(search_id, job_ids)    -> run_id, estimate (Editor/Reviewer loop + PDF per job)

Runs execute in a small thread pool (runs take minutes). A run whose estimate is over the
cap is never started (status stopped_cost_cap); the meter also stops a run mid-way.
"""

import logging
import shutil
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from pathlib import Path

from jobcv.accounts import Accounts, Claim, Refused
from jobcv.agents.base import LLMCall
from jobcv.agents.parser import parse_cv
from jobcv.agents.scorer import rank_jobs
from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter, Estimate
from jobcv.cv.ingest import extract_cv_text
from jobcv.jobs.cache import JobCache, JobSearchService
from jobcv.pdf.render import pdf_filename, render_pdf
from jobcv.pipeline.tailor_loop import tailor_for_job
from jobcv.schemas import CV, Job, SearchQuery
from jobcv.sources.base import JobSource
from jobcv.sources.linkedin_apify import LinkedInApifySource
from jobcv.store import LOCAL_OWNER, UserStore

log = logging.getLogger(__name__)

UPLOAD_RESERVE_USD = 0.02  # a CV upload costs about $0.01; held from the daily budget

QUEUED, RUNNING, DONE, FAILED, STOPPED = "queued", "running", "done", "failed", "stopped_cost_cap"


class NotFound(LookupError):
    pass


class CvDeleted(Exception):
    """The CV was deleted while its run was working. Nothing more may be done with it."""


MAX_CONFIRMED = 8


def confirmed_facts(confirmed: list[tuple[str, str]]) -> str:
    """What the user ticked, as extra information the editor may use as a source."""
    lines = [f"- {label}: {details}" if details else f"- {label}" for label, details in confirmed]
    return ("The candidate confirms these are true about themself (they ticked them in the "
            "suggestions, with any details they added):\n" + "\n".join(lines))


def _free_name(name: str, taken: set[str]) -> str:
    """Two jobs can share a title and company; each still needs its own PDF."""
    stem, n = name.removesuffix(".pdf"), 1
    while name in taken:
        n += 1
        name = f"{stem} ({n}).pdf"
    taken.add(name)
    return name


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
        self.accounts = Accounts(settings)
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
    def add_cv(self, pdf: bytes, owner: str = LOCAL_OWNER) -> str:
        """Blocking: extract text (OCR if needed) and parse. Usually 10-40 seconds."""
        meter = CostMeter(self.s)
        ex = extract_cv_text(pdf, self.s)  # free and local: a bad file uses no upload
        claim = self.accounts.claim(owner, "upload", cost_usd=UPLOAD_RESERVE_USD)
        try:
            cv = parse_cv(ex.text, ex.language, self.s, meter, llm=self.llm)
        finally:
            self.accounts.settle(claim, spent_usd=meter.record().actual_cost_usd)
        cv_id = self.store.add_cv(ex.language, ex.method, ex.text, cv.model_dump_json(),
                                  meter.record().model_dump(mode="json"), owner=owner,
                                  replace=owner != LOCAL_OWNER)  # one active CV per account
        log.info("cv %s added: lang=%s method=%s", cv_id, ex.language, ex.method)
        return cv_id

    def get_cv(self, cv_id: str, owner: str = LOCAL_OWNER) -> tuple[CV, str]:
        row = self.store.get_cv(cv_id, owner=owner)
        if row is None:
            raise NotFound("cv not found or expired")
        return CV.model_validate_json(row["cv_json"]), row["raw_text"]

    def delete_cv(self, cv_id: str, owner: str = LOCAL_OWNER) -> bool:
        return self.store.delete_cv(cv_id, owner=owner)

    def delete_user_data(self, owner: str) -> int:
        """All CVs, runs and PDFs of one account. The allowance counters stay (SPEC-accounts)."""
        return self.store.delete_all(owner)

    # ---------------- estimates (no paid calls) ----------------
    def estimate_search(self, q: SearchQuery) -> Estimate:
        apify = self.search_service.source.estimate_cost(q, q.max_results)
        return CostMeter(self.s).estimate_search(q.max_results, apify)

    def estimate_tailor(self, n_jobs: int) -> Estimate:
        return CostMeter(self.s).estimate_tailor(n_jobs)

    # ---------------- search ----------------
    def start_search(self, cv_id: str, q: SearchQuery, force_refresh: bool = False,
                     owner: str = LOCAL_OWNER):
        self.get_cv(cv_id, owner)
        if not self.accounts.unlimited(owner):
            if q.max_results > self.s.free_max_results:
                raise Refused(403, "free_limit")
            force_refresh = False  # bypassing the cache costs Apify money
        est = self.estimate_search(q)
        status = QUEUED if est.within_cap else STOPPED
        claim = (self.accounts.claim(owner, "search", cost_usd=est.total_usd)
                 if est.within_cap else None)
        run_id = self._add_run(claim, "search", cv_id, {
            "query": q.model_dump(mode="json"), "force_refresh": force_refresh},
            est.model_dump(), status, owner=owner)
        if claim:
            self._submit(self._run_search, run_id, cv_id, q, force_refresh, owner, claim)
        else:
            self.store.update_run(run_id, status=STOPPED, error="estimate exceeds the cost cap")
        return run_id, est

    def _add_run(self, claim: Claim | None, *args, **kwargs) -> str:
        """Records the run; if that fails (the CV was just deleted), the claim is given back."""
        run_id = self.store.add_run(*args, **kwargs)
        if run_id is None:
            if claim:
                self.accounts.settle(claim, refund=claim.n, spent_usd=0.0)
            raise NotFound("cv not found or expired")
        return run_id

    def _run_search(self, run_id: str, cv_id: str, q: SearchQuery, force_refresh: bool,
                    owner: str, claim: Claim) -> None:
        meter = CostMeter(self.s)
        refund = 1  # unless jobs were found, or the user deleted the CV
        self.store.update_run(run_id, status=RUNNING)
        try:
            cv, _ = self.get_cv(cv_id, owner)
            res = self.search_service.search(q, meter=meter, force_refresh=force_refresh)
            ranked = rank_jobs(cv, res.jobs, self.s, meter, llm=self.llm,
                               check=partial(self._require_cv, cv_id))
            result = {
                "last_updated": res.last_updated.isoformat(), "from_cache": res.from_cache,
                "jobs": [{"job": r.job.model_dump(mode="json"),
                          "match": r.match.model_dump() if r.match else None,
                          "error": r.error} for r in ranked],
            }
            refund = 0 if ranked else 1
            self.store.update_run(run_id, status=DONE, result=result,
                                  cost=meter.record().model_dump(mode="json"))
        except CvDeleted:
            refund = 0
            log.info("search run %s stopped: its cv was deleted", run_id)
        except CostCapExceeded as e:
            self.store.update_run(run_id, status=STOPPED, error=str(e),
                                  cost=meter.record().model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001 - every run must end in a visible state
            # type only: exception messages (e.g. validation errors) can contain CV text
            log.error("search run %s failed: %s", run_id, type(e).__name__)
            self.store.update_run(run_id, status=FAILED, error=type(e).__name__,
                                  cost=meter.record().model_dump(mode="json"))
        finally:
            self.accounts.settle(claim, refund=refund, spent_usd=meter.record().actual_cost_usd)

    def get_search(self, run_id: str, owner: str = LOCAL_OWNER) -> dict:
        run = self.store.get_run(run_id, "search", owner=owner)
        if run is None:
            raise NotFound("run not found or expired")
        return run

    # ---------------- tailor ----------------
    def start_tailor(self, search_run_id: str, job_ids: list[str], extra_info: str = "",
                     owner: str = LOCAL_OWNER, confirmed: list[tuple[str, str]] | None = None):
        """`confirmed`: missing skills the user ticked before tailoring (details optional)."""
        if confirmed:
            extra_info = "\n\n".join(p for p in (extra_info.strip(), confirmed_facts(confirmed)) if p)
        return self._start_tailoring(search_run_id, job_ids, extra_info, owner)

    def start_redo(self, tailor_id: str, job_id: str, confirmed: list[tuple[str, str]],
                   owner: str = LOCAL_OWNER):
        """Make one tailored CV again with suggestions the user confirmed. Free accounts get one
        redo per tailored CV, not counted in the allowance; a redo's own result is final."""
        tailor = self.get_tailor(tailor_id, owner)
        if job_id not in {r["job_id"] for r in tailor["result"] or []}:
            raise ValueError("this run didn't produce a CV for that job")
        if not confirmed or len(confirmed) > MAX_CONFIRMED:
            raise ValueError(f"choose between 1 and {MAX_CONFIRMED} suggestions")
        free = not self.accounts.unlimited(owner)
        if free:
            if (tailor["request"] or {}).get("redo_of"):
                raise Refused(403, "redo_used")
            self.accounts.claim_redo(tailor_id, job_id)
        try:
            return self._start_tailoring(tailor["parent_id"], [job_id], confirmed_facts(confirmed),
                                         owner, redo=(tailor_id, job_id) if free else None)
        except Exception:
            if free:
                self.accounts.release_redo(tailor_id, job_id)
            raise

    def _start_tailoring(self, search_run_id: str, job_ids: list[str], extra_info: str,
                         owner: str, redo: tuple[str, str] | None = None):
        search = self.get_search(search_run_id, owner)
        if search["status"] != DONE:
            raise ValueError("search run is not finished")
        jobs = {j["job"]["id"]: Job.model_validate(j["job"]) for j in search["result"]["jobs"]}
        unknown = [j for j in job_ids if j not in jobs]
        if unknown or not job_ids:
            raise ValueError(f"unknown job ids: {unknown}" if unknown else "no jobs selected")
        est = self.estimate_tailor(len(job_ids))
        status = QUEUED if est.within_cap else STOPPED
        n = 0 if redo else len(job_ids)  # a free redo doesn't use the allowance
        claim = (self.accounts.claim(owner, "tailor", n=n, cost_usd=est.total_usd)
                 if est.within_cap else None)
        request = {"job_ids": job_ids, "has_extra_info": bool(extra_info)}
        if redo:
            request["redo_of"] = redo[0]
        run_id = self._add_run(claim, "tailor", search["cv_id"], request,
                               est.model_dump(), status, parent_id=search_run_id, owner=owner)
        if claim:
            # extra_info is personal data: passed in memory only, never stored in the request
            self._submit(self._run_tailor, run_id, search["cv_id"],
                         [jobs[j] for j in job_ids], extra_info, owner, claim, redo)
        else:
            self.store.update_run(run_id, status=STOPPED, error="estimate exceeds the cost cap")
            if redo:
                self.accounts.release_redo(*redo)
        return run_id, est

    def _require_cv(self, cv_id: str) -> None:
        """Called before each paid step: a deleted CV must stop being sent anywhere."""
        if not self.store.cv_exists(cv_id):
            raise CvDeleted

    def _run_tailor(self, run_id: str, cv_id: str, jobs: list[Job], extra_info: str,
                    owner: str, claim: Claim, redo: tuple[str, str] | None = None) -> None:
        meter = CostMeter(self.s)
        self.store.update_run(run_id, status=RUNNING)
        results: list[dict] = []
        check = partial(self._require_cv, cv_id)
        names: set[str] = set()
        deleted = False
        try:
            cv, raw = self.get_cv(cv_id, owner)
            out_dir = self.store.files_dir(cv_id) / run_id
            for job in jobs:
                check()
                out = tailor_for_job(cv, raw, job, self.s, meter, extra_info=extra_info,
                                     llm=self.llm, check=check)
                name = _free_name(pdf_filename(job.title, job.company), names)
                pdf = self.renderer(out.tailored_cv, out_dir / name)
                check()
                results.append({**out.model_dump(mode="json"), "pdf": pdf.name})
                self.store.update_run(run_id, status=RUNNING, result=results)  # progress
            self.store.update_run(run_id, status=DONE, result=results,
                                  cost=meter.record().model_dump(mode="json"))
        except CvDeleted:
            deleted = True
            log.info("tailor run %s stopped: its cv was deleted", run_id)
        except CostCapExceeded as e:
            self.store.update_run(run_id, status=STOPPED, result=results, error=str(e),
                                  cost=meter.record().model_dump(mode="json"))
        except Exception as e:  # noqa: BLE001 - every run must end in a visible state
            log.error("tailor run %s failed: %s", run_id, type(e).__name__)
            self.store.update_run(run_id, status=FAILED, result=results, error=type(e).__name__,
                                  cost=meter.record().model_dump(mode="json"))
        finally:
            if not self.store.cv_exists(cv_id):  # however the run ended, leave no file behind
                shutil.rmtree(self.store.files_dir(cv_id), ignore_errors=True)
            # only CVs actually produced use the allowance
            self.accounts.settle(claim, refund=0 if deleted else len(jobs) - len(results),
                                 spent_usd=meter.record().actual_cost_usd)
            if redo and not results and not deleted:  # no CV came out: the redo is given back
                self.accounts.release_redo(*redo)

    def get_tailor(self, run_id: str, owner: str = LOCAL_OWNER) -> dict:
        run = self.store.get_run(run_id, "tailor", owner=owner)
        if run is None:
            raise NotFound("run not found or expired")
        return run

    def pdf_path(self, run_id: str, name: str, owner: str = LOCAL_OWNER) -> Path:
        run = self.get_tailor(run_id, owner)
        names = {r["pdf"] for r in run["result"] or []}
        if name not in names:  # only files this run produced; no path traversal
            raise NotFound("file not found")
        path = self.store.files_dir(run["cv_id"]) / run_id / name
        if not path.is_file():  # deleted at this very moment
            raise NotFound("file not found")
        return path

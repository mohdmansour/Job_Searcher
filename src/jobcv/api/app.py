"""FastAPI service over the Engine.

Every route needs a signed-in user and only ever reaches that user's data. Routes are plain
`def`: the engine is blocking, FastAPI runs them in its threadpool. Long work (search,
tailoring) runs in the engine's background workers. Run one server process per data folder:
at startup, unfinished runs are treated as interrupted.
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from jobcv.accounts import Refused
from jobcv.api.auth import CurrentUser, Verifier, clerk_verifier
from jobcv.config import get_settings
from jobcv.cost.meter import CostCapExceeded, CostRecord, Estimate
from jobcv.cv.ingest import CvTooLarge, OcrUnavailable
from jobcv.pipeline.engine import Engine, NotFound
from jobcv.schemas import (
    ChangeLogEntry,
    Country,
    Job,
    MatchResult,
    SearchQuery,
    Suggestions,
    Violation,
)
from jobcv.schemas.jobs import ShortText

log = logging.getLogger(__name__)
MAX_PDF_BYTES = 10 * 1024 * 1024
SWEEP_EVERY_SECONDS = 15 * 60


# ---------------- request / response models ----------------
class Me(BaseModel):
    user_id: str  # Clerk's id, needed to list an owner account in JOBCV_UNLIMITED_USER_IDS
    free_searches_left: int
    free_tailors_left: int
    unlimited: bool
    free_max_results: int


class CVCreated(BaseModel):
    cv_id: str
    language: str
    extraction: Literal["text", "ocr"]


class CVStatus(CVCreated):
    pass


class EstimateSearchRequest(BaseModel):
    country: Country
    cities: list[ShortText] = Field(default_factory=list, max_length=10)
    remote: bool = False
    max_results: int = Field(default=25, ge=1, le=200)


class EstimateTailorRequest(BaseModel):
    n_jobs: int = Field(ge=1, le=20)


class EstimateOut(Estimate):
    price_to_user_usd: float


class SearchRequest(BaseModel):
    cv_id: str
    title: str = Field(min_length=1, max_length=200)
    more_titles: list[ShortText] = Field(default_factory=list, max_length=2)
    country: Country
    cities: list[ShortText] = Field(default_factory=list, max_length=10)
    remote: bool = False
    max_results: int = Field(default=25, ge=1, le=200)
    force_refresh: bool = False  # bypasses the job cache (billable)


class RunStarted(BaseModel):
    run_id: str
    status: str
    estimate: Estimate


class RankedJobOut(BaseModel):
    job: Job
    match: MatchResult | None
    error: str | None = None


class SearchRunOut(BaseModel):
    run_id: str
    status: str
    estimate: Estimate
    last_updated: str | None = None
    from_cache: bool | None = None
    jobs: list[RankedJobOut] = Field(default_factory=list)
    cost: CostRecord | None = None
    error: str | None = None


class ConfirmedItem(BaseModel):
    """Something the user ticked as true about themself, with optional details."""

    label: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=500)


class TailorRequest(BaseModel):
    run_id: str
    job_ids: list[str] = Field(min_length=1, max_length=20)
    user_extra_info: str = Field(default="", max_length=5000)
    confirmed: list[ConfirmedItem] = Field(default_factory=list, max_length=15)


class TailoredJobOut(BaseModel):
    job_id: str
    pdf_url: str
    review_status: str
    attempts: int
    warning: bool
    remaining_violations: list[Violation]
    change_log: list[ChangeLogEntry]
    suggestions: Suggestions = Field(default_factory=list)
    redo_available: bool = False  # can this CV be made again with ticked suggestions, for free


class RedoRequest(BaseModel):
    job_id: str
    confirmed: list[ConfirmedItem] = Field(min_length=1, max_length=8)


class TailorRunOut(BaseModel):
    tailor_id: str
    status: str
    estimate: Estimate
    results: list[TailoredJobOut] = Field(default_factory=list)
    cost: CostRecord | None = None
    error: str | None = None


# ---------------- app ----------------
def _sweeper(engine: Engine, stop: threading.Event) -> None:
    while not stop.wait(SWEEP_EVERY_SECONDS):
        try:
            removed = engine.store.sweep()
            if removed:
                log.info("retention sweep removed %d expired CVs", removed)
        except Exception:
            log.exception("retention sweep failed")


def create_app(engine: Engine | None = None, verifier: Verifier | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine or Engine(get_settings())
        app.state.verifier = verifier or clerk_verifier(app.state.engine.s)
        app.state.engine.store.fail_interrupted()  # left by a server that has stopped
        app.state.engine.accounts.clear_active()
        app.state.engine.store.sweep()
        stop = threading.Event()
        threading.Thread(target=_sweeper, args=(app.state.engine, stop), daemon=True).start()
        yield
        stop.set()
        app.state.engine.pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Job CV Engine", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(NotFound)
    def not_found(_request: Request, e: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(Refused)
    def refused(_request: Request, e: Refused) -> JSONResponse:
        # allowance_used, free_limit (403); rate_limited, daily_budget (429)
        return JSONResponse({"detail": {"code": e.code}}, status_code=e.status)

    @app.middleware("http")
    async def log_error_types_only(request: Request, call_next):
        # a server traceback can quote CV text (validation errors do)
        try:
            return await call_next(request)
        except Exception as e:  # noqa: BLE001
            log.error("%s request failed: %s", request.method, type(e).__name__)
            return JSONResponse({"detail": "server error"}, status_code=500)

    def get_engine(request: Request) -> Engine:
        return request.app.state.engine

    EngineDep = Annotated[Engine, Depends(get_engine)]

    @app.get("/me")
    def me(engine: EngineDep, user: CurrentUser) -> Me:
        return Me(user_id=user.id, **engine.accounts.status(user.id))

    @app.delete("/me/data", status_code=204)
    def delete_my_data(engine: EngineDep, user: CurrentUser) -> Response:
        """Works from any device: needs no CV id kept in a browser."""
        engine.delete_user_data(user.id)
        return Response(status_code=204)

    @app.post("/cv", status_code=201)
    def upload_cv(engine: EngineDep, user: CurrentUser,
                  file: Annotated[UploadFile, File()]) -> CVCreated:
        data = file.file.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(413, "PDF larger than 10 MB")
        try:
            cv_id = engine.add_cv(data, owner=user.id)
        except CvTooLarge as e:
            raise HTTPException(413, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except OcrUnavailable as e:
            raise HTTPException(503, "OCR is not available on this server") from e
        except CostCapExceeded as e:
            raise HTTPException(402, str(e)) from e
        row = engine.store.get_cv(cv_id, owner=user.id)
        if row is None:  # replaced by a parallel upload from the same account
            raise NotFound("cv not found or expired")
        return CVCreated(cv_id=cv_id, language=row["language"], extraction=row["method"])

    @app.get("/cv/{cv_id}")
    def cv_status(engine: EngineDep, user: CurrentUser, cv_id: str) -> CVStatus:
        row = engine.store.get_cv(cv_id, owner=user.id)
        if row is None:
            raise HTTPException(404, "cv not found or expired")
        return CVStatus(cv_id=cv_id, language=row["language"], extraction=row["method"])

    def priced(engine: Engine, est: Estimate) -> EstimateOut:
        return EstimateOut(**est.model_dump(), price_to_user_usd=est.total_usd * engine.s.markup)

    @app.post("/estimate/search")
    def estimate_search(engine: EngineDep, _user: CurrentUser,
                        req: EstimateSearchRequest) -> EstimateOut:
        # the title doesn't affect the price, so the form can ask before one is typed
        q = SearchQuery(title="estimate", **req.model_dump())
        return priced(engine, engine.estimate_search(q))

    @app.post("/estimate/tailor")
    def estimate_tailor(engine: EngineDep, _user: CurrentUser,
                        req: EstimateTailorRequest) -> EstimateOut:
        return priced(engine, engine.estimate_tailor(req.n_jobs))

    @app.delete("/cv/{cv_id}", status_code=204)
    def delete_cv(engine: EngineDep, user: CurrentUser, cv_id: str) -> Response:
        if not engine.delete_cv(cv_id, owner=user.id):
            raise HTTPException(404, "cv not found")
        return Response(status_code=204)

    @app.post("/search", status_code=202)
    def start_search(engine: EngineDep, user: CurrentUser, req: SearchRequest) -> RunStarted:
        q = SearchQuery(title=req.title, more_titles=req.more_titles, country=req.country,
                        cities=req.cities,
                        remote=req.remote, max_results=req.max_results)
        run_id, est = engine.start_search(req.cv_id, q, force_refresh=req.force_refresh,
                                          owner=user.id)
        return RunStarted(run_id=run_id, status=engine.get_search(run_id, user.id)["status"], estimate=est)

    @app.get("/runs/{run_id}")
    def get_run(engine: EngineDep, user: CurrentUser, run_id: str) -> SearchRunOut:
        run = engine.get_search(run_id, user.id)
        result = run["result"] or {}
        return SearchRunOut(
            run_id=run_id, status=run["status"], estimate=run["estimate"],
            last_updated=result.get("last_updated"), from_cache=result.get("from_cache"),
            jobs=result.get("jobs", []), cost=run["cost"], error=run["error"])

    @app.post("/tailor", status_code=202)
    def start_tailor(engine: EngineDep, user: CurrentUser, req: TailorRequest) -> RunStarted:
        try:
            run_id, est = engine.start_tailor(
                req.run_id, req.job_ids, req.user_extra_info, owner=user.id,
                confirmed=[(c.label.strip(), c.details.strip()) for c in req.confirmed])
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return RunStarted(run_id=run_id, status=engine.get_tailor(run_id, user.id)["status"], estimate=est)

    @app.get("/tailor/{tailor_id}")
    def get_tailor(engine: EngineDep, user: CurrentUser, tailor_id: str,
                   request: Request) -> TailorRunOut:
        run = engine.get_tailor(tailor_id, user.id)
        unlimited = engine.accounts.unlimited(user.id)
        is_redo = bool((run["request"] or {}).get("redo_of"))

        def redo_ok(job_id: str) -> bool:
            if unlimited:
                return True
            return not is_redo and not engine.accounts.redo_used(tailor_id, job_id)

        results = [
            TailoredJobOut(
                **{k: r[k] for k in ("job_id", "review_status", "attempts", "warning",
                                     "remaining_violations", "change_log")},
                suggestions=r.get("suggestions", []),  # runs made before suggestions existed
                redo_available=redo_ok(r["job_id"]),
                pdf_url=str(request.url_for("download_pdf", tailor_id=tailor_id, name=r["pdf"])),
            )
            for r in run["result"] or []
        ]
        return TailorRunOut(tailor_id=tailor_id, status=run["status"], estimate=run["estimate"],
                            results=results, cost=run["cost"], error=run["error"])

    @app.post("/tailor/{tailor_id}/redo", status_code=202)
    def redo_tailor(engine: EngineDep, user: CurrentUser, tailor_id: str,
                    req: RedoRequest) -> RunStarted:
        """Make one tailored CV again with the suggestions the user ticked (details optional)."""
        confirmed = [(c.label.strip(), c.details.strip()) for c in req.confirmed]
        try:
            run_id, est = engine.start_redo(tailor_id, req.job_id, confirmed, owner=user.id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return RunStarted(run_id=run_id, status=engine.get_tailor(run_id, user.id)["status"],
                          estimate=est)

    @app.get("/files/{tailor_id}/{name}", name="download_pdf")
    def download_pdf(engine: EngineDep, user: CurrentUser, tailor_id: str,
                     name: str) -> FileResponse:
        path = engine.pdf_path(tailor_id, name, user.id)
        return FileResponse(path, media_type="application/pdf", filename=name)

    return app


app = create_app()

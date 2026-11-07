"""FastAPI service over the Engine. Minimal Phase 1 API, no accounts/payments.

Run ids are random 128-bit tokens; whoever holds one can read that run (there are no user
accounts in Phase 1). Routes are plain `def`: the engine is blocking, FastAPI runs them in
its threadpool. Long work (search, tailoring) runs in the engine's background workers.
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jobcv.config import get_settings
from jobcv.cost.meter import CostCapExceeded, CostRecord, Estimate
from jobcv.cv.ingest import OcrUnavailable
from jobcv.pipeline.engine import Engine, NotFound
from jobcv.schemas import ChangeLogEntry, Country, Job, MatchResult, SearchQuery, Violation

log = logging.getLogger(__name__)
MAX_PDF_BYTES = 10 * 1024 * 1024
SWEEP_EVERY_SECONDS = 15 * 60


# ---------------- request / response models ----------------
class CVCreated(BaseModel):
    cv_id: str
    language: str
    extraction: Literal["text", "ocr"]


class SearchRequest(BaseModel):
    cv_id: str
    title: str = Field(min_length=1, max_length=200)
    country: Country
    cities: list[str] = Field(default_factory=list, max_length=10)
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


class TailorRequest(BaseModel):
    run_id: str
    job_ids: list[str] = Field(min_length=1, max_length=20)
    user_extra_info: str = Field(default="", max_length=5000)


class TailoredJobOut(BaseModel):
    job_id: str
    pdf_url: str
    review_status: str
    attempts: int
    warning: bool
    remaining_violations: list[Violation]
    change_log: list[ChangeLogEntry]


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


def create_app(engine: Engine | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine or Engine(get_settings())
        app.state.engine.store.sweep()
        stop = threading.Event()
        threading.Thread(target=_sweeper, args=(app.state.engine, stop), daemon=True).start()
        yield
        stop.set()
        app.state.engine.pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Job CV Engine", version="0.1.0", lifespan=lifespan)

    def get_engine(request: Request) -> Engine:
        return request.app.state.engine

    EngineDep = Annotated[Engine, Depends(get_engine)]

    @app.post("/cv", status_code=201)
    def upload_cv(engine: EngineDep, file: Annotated[UploadFile, File()]) -> CVCreated:
        data = file.file.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(413, "PDF larger than 10 MB")
        try:
            cv_id = engine.add_cv(data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except OcrUnavailable as e:
            raise HTTPException(503, "OCR is not available on this server") from e
        except CostCapExceeded as e:
            raise HTTPException(402, str(e)) from e
        row = engine.store.get_cv(cv_id)
        return CVCreated(cv_id=cv_id, language=row["language"], extraction=row["method"])

    @app.delete("/cv/{cv_id}", status_code=204)
    def delete_cv(engine: EngineDep, cv_id: str) -> Response:
        if not engine.delete_cv(cv_id):
            raise HTTPException(404, "cv not found")
        return Response(status_code=204)

    @app.post("/search", status_code=202)
    def start_search(engine: EngineDep, req: SearchRequest) -> RunStarted:
        q = SearchQuery(title=req.title, country=req.country, cities=req.cities,
                        remote=req.remote, max_results=req.max_results)
        try:
            run_id, est = engine.start_search(req.cv_id, q, force_refresh=req.force_refresh)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        return RunStarted(run_id=run_id, status=engine.get_search(run_id)["status"], estimate=est)

    @app.get("/runs/{run_id}")
    def get_run(engine: EngineDep, run_id: str) -> SearchRunOut:
        try:
            run = engine.get_search(run_id)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        result = run["result"] or {}
        return SearchRunOut(
            run_id=run_id, status=run["status"], estimate=run["estimate"],
            last_updated=result.get("last_updated"), from_cache=result.get("from_cache"),
            jobs=result.get("jobs", []), cost=run["cost"], error=run["error"])

    @app.post("/tailor", status_code=202)
    def start_tailor(engine: EngineDep, req: TailorRequest) -> RunStarted:
        try:
            run_id, est = engine.start_tailor(req.run_id, req.job_ids, req.user_extra_info)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return RunStarted(run_id=run_id, status=engine.get_tailor(run_id)["status"], estimate=est)

    @app.get("/tailor/{tailor_id}")
    def get_tailor(engine: EngineDep, tailor_id: str, request: Request) -> TailorRunOut:
        try:
            run = engine.get_tailor(tailor_id)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        results = [
            TailoredJobOut(
                **{k: r[k] for k in ("job_id", "review_status", "attempts", "warning",
                                     "remaining_violations", "change_log")},
                pdf_url=str(request.url_for("download_pdf", tailor_id=tailor_id, name=r["pdf"])),
            )
            for r in run["result"] or []
        ]
        return TailorRunOut(tailor_id=tailor_id, status=run["status"], estimate=run["estimate"],
                            results=results, cost=run["cost"], error=run["error"])

    @app.get("/files/{tailor_id}/{name}", name="download_pdf")
    def download_pdf(engine: EngineDep, tailor_id: str, name: str) -> FileResponse:
        try:
            path = engine.pdf_path(tailor_id, name)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        return FileResponse(path, media_type="application/pdf", filename=name)

    return app


app = create_app()

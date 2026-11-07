"""CLI for running the Phase 1 flow locally (same Engine as the API, run inline).

  jobcv countries
  jobcv cv add CV.pdf
  jobcv search --cv ID --title "QA Engineer" --country "United Arab Emirates" [--city Dubai] [--remote] [--max 10]
  jobcv tailor --run RUN_ID --job JOB_ID [--job JOB_ID ...] [--extra "text"] [--out DIR]
  jobcv run-all CV.pdf --title ... --country ... [--max 5] [--pick 1] [--out DIR]
  jobcv cv delete ID
  jobcv sweep
"""

import argparse
import shutil
import sys
from pathlib import Path

from jobcv.config import get_settings
from jobcv.cost.meter import CostMeter
from jobcv.pipeline.engine import DONE, Engine
from jobcv.schemas import Country, SearchQuery


def _country(value: str) -> Country:
    for c in Country:
        if value.casefold() in (c.value.casefold(), c.name.casefold()):
            return c
    raise argparse.ArgumentTypeError(f"unknown country {value!r}; see `jobcv countries`")


def _confirm(est, yes: bool) -> bool:
    print(f"Estimated cost: ${est.total_usd:.4f} (Apify ${est.apify_usd:.4f} + LLM "
          f"${est.llm_usd:.4f}), cap ${est.cap_usd:.2f}")
    if not est.within_cap:
        print("Over the cost cap: not started.")
        return False
    if yes:
        return True
    return input("Proceed? [y/N] ").strip().lower() == "y"


def _print_cost(run) -> None:
    c = run.get("cost") or {}
    if c:
        print(f"Actual cost: ${c['actual_cost_usd']:.4f} | price to user (x{c['markup']}): "
              f"${c['price_to_user_usd']:.4f}")


def cmd_search(engine: Engine, args) -> str | None:
    q = SearchQuery(title=args.title, country=args.country, cities=args.city or [],
                    remote=args.remote, max_results=args.max)
    apify = engine.search_service.source.estimate_cost(q, q.max_results)
    est = CostMeter(engine.s).estimate_search(q.max_results, apify)
    if not _confirm(est, args.yes):
        return None
    run_id, _ = engine.start_search(args.cv, q, force_refresh=args.force_refresh)
    run = engine.get_search(run_id)
    print(f"\nSearch run {run_id}: {run['status']}"
          + (f" ({run['error']})" if run["error"] else ""))
    if run["status"] == DONE:
        r = run["result"]
        print(f"Jobs last updated {r['last_updated']} ({'cache' if r['from_cache'] else 'fresh'})\n")
        for i, j in enumerate(r["jobs"], 1):
            m, job = j["match"], j["job"]
            score = f"{m['score']:>3}" if m else "ERR"
            print(f"{i:>2}. [{score}] {job['title']} — {job['company']} ({job['location']})")
            print(f"      id: {job['id']}")
            if m:
                print(f"      gaps: {'; '.join(m['gaps'][:4])}")
    _print_cost(run)
    return run_id


def cmd_tailor(engine: Engine, run_id: str, job_ids: list[str], extra: str, out: Path,
               yes: bool) -> None:
    if not _confirm(CostMeter(engine.s).estimate_tailor(len(job_ids)), yes):
        return
    t_id, _ = engine.start_tailor(run_id, job_ids, extra)
    run = engine.get_tailor(t_id)
    print(f"\nTailor run {t_id}: {run['status']}" + (f" ({run['error']})" if run["error"] else ""))
    out.mkdir(parents=True, exist_ok=True)
    for r in run["result"] or []:
        dest = out / r["pdf"]
        shutil.copy(engine.pdf_path(t_id, r["pdf"]), dest)
        flag = "  WARNING: review still FAILED" if r["warning"] else ""
        print(f"- {r['job_id']}: review {r['review_status']} after {r['attempts']} attempt(s)"
              f"{flag}\n  PDF: {dest}")
        for v in r["remaining_violations"]:
            print(f"    [{v['problem']}] {v['adapted_text']} — {v['explanation']}")
        for c in r["change_log"][:5]:
            print(f"    changed: {c['original'][:70]!r} -> {c['adapted'][:70]!r}")
    _print_cost(run)


def main(argv: list[str] | None = None, engine: Engine | None = None) -> int:
    p = argparse.ArgumentParser(prog="jobcv", description="Job search + CV tailoring (Phase 1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("countries")
    sub.add_parser("sweep", help="delete expired CVs, runs and PDFs")

    cv = sub.add_parser("cv").add_subparsers(dest="cv_cmd", required=True)
    cv.add_parser("add").add_argument("pdf", type=Path)
    cv.add_parser("delete").add_argument("cv_id")

    def search_args(sp):
        sp.add_argument("--title", required=True)
        sp.add_argument("--country", required=True, type=_country)
        sp.add_argument("--city", action="append")
        sp.add_argument("--remote", action="store_true")
        sp.add_argument("--max", type=int, default=10)
        sp.add_argument("--force-refresh", action="store_true")
        sp.add_argument("--yes", "-y", action="store_true", help="do not ask before spending")

    s = sub.add_parser("search")
    s.add_argument("--cv", required=True)
    search_args(s)

    t = sub.add_parser("tailor")
    t.add_argument("--run", required=True)
    t.add_argument("--job", action="append", required=True)
    t.add_argument("--extra", default="")
    t.add_argument("--out", type=Path, default=Path("output"))
    t.add_argument("--yes", "-y", action="store_true")

    a = sub.add_parser("run-all", help="cv add + search + tailor the top --pick jobs")
    a.add_argument("pdf", type=Path)
    search_args(a)
    a.add_argument("--pick", type=int, default=1)
    a.add_argument("--extra", default="")
    a.add_argument("--out", type=Path, default=Path("output"))

    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic output on Windows consoles

    if args.cmd == "countries":
        for c in Country:
            print(c.value)
        return 0

    engine = engine or Engine(get_settings(), synchronous=True)
    if args.cmd == "sweep":
        print(f"removed {engine.store.sweep()} expired CV(s)")
    elif args.cmd == "cv" and args.cv_cmd == "add":
        cv_id = engine.add_cv(args.pdf.read_bytes())
        print(f"cv_id: {cv_id}")
    elif args.cmd == "cv" and args.cv_cmd == "delete":
        print("deleted" if engine.delete_cv(args.cv_id) else "not found")
    elif args.cmd == "search":
        cmd_search(engine, args)
    elif args.cmd == "tailor":
        cmd_tailor(engine, args.run, args.job, args.extra, args.out, args.yes)
    elif args.cmd == "run-all":
        args.cv = engine.add_cv(args.pdf.read_bytes())
        print(f"cv_id: {args.cv}")
        run_id = cmd_search(engine, args)
        if run_id:
            run = engine.get_search(run_id)
            ids = [j["job"]["id"] for j in run["result"]["jobs"] if j["match"]][: args.pick]
            if ids:
                cmd_tailor(engine, run_id, ids, args.extra, args.out, args.yes)
    engine.pool.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

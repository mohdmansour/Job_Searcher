"""Per-user data store (CVs, runs, scores, PDFs). PERSONAL DATA — kept apart from the job cache.

Everything has an expiry (settings.cv_ttl_hours, default 24h). `sweep()` deletes expired rows
and files; `delete_cv()` removes a CV with all its runs and PDFs immediately.
"""

import json
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jobcv.config import Settings

SCHEMA = """
create table if not exists cvs (
  id text primary key, created_at text, expires_at text,
  language text, method text, raw_text text, cv_json text, cost_json text);
create table if not exists runs (
  id text primary key, kind text, cv_id text, parent_id text, created_at text, expires_at text,
  status text, request_json text, estimate_json text, result_json text, cost_json text,
  error text);
create index if not exists runs_cv on runs(cv_id);
"""


def new_id() -> str:
    return uuid.uuid4().hex


class UserStore:
    def __init__(self, settings: Settings, now=lambda: datetime.now(UTC)):
        self.s, self.now = settings, now
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.s.user_db, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def _expiry(self) -> tuple[str, str]:
        now = self.now()
        return now.isoformat(), (now + timedelta(hours=self.s.cv_ttl_hours)).isoformat()

    def files_dir(self, cv_id: str) -> Path:
        return self.s.user_files_dir / cv_id

    # ---------------- CVs ----------------
    def add_cv(self, language: str, method: str, raw_text: str, cv_json: str,
               cost: dict) -> str:
        cv_id = new_id()
        created, expires = self._expiry()
        with self._db() as db:
            db.execute("insert into cvs values (?,?,?,?,?,?,?,?)",
                       (cv_id, created, expires, language, method, raw_text, cv_json,
                        json.dumps(cost)))
        return cv_id

    def get_cv(self, cv_id: str) -> sqlite3.Row | None:
        with self._db() as db:
            return db.execute("select * from cvs where id = ? and expires_at > ?",
                              (cv_id, self.now().isoformat())).fetchone()

    def delete_cv(self, cv_id: str) -> bool:
        with self._db() as db:
            found = db.execute("delete from cvs where id = ?", (cv_id,)).rowcount > 0
            db.execute("delete from runs where cv_id = ?", (cv_id,))
        shutil.rmtree(self.files_dir(cv_id), ignore_errors=True)
        return found

    # ---------------- runs ----------------
    def add_run(self, kind: str, cv_id: str, request: dict, estimate: dict, status: str,
                parent_id: str | None = None) -> str:
        run_id = new_id()
        created, expires = self._expiry()
        with self._db() as db:
            db.execute(
                "insert into runs (id, kind, cv_id, parent_id, created_at, expires_at, status,"
                " request_json, estimate_json) values (?,?,?,?,?,?,?,?,?)",
                (run_id, kind, cv_id, parent_id, created, expires, status, json.dumps(request),
                 json.dumps(estimate)))
        return run_id

    def update_run(self, run_id: str, *, status: str, result: Any = None, cost: dict | None = None,
                   error: str | None = None) -> None:
        with self._db() as db:
            db.execute(
                "update runs set status = ?, result_json = coalesce(?, result_json),"
                " cost_json = coalesce(?, cost_json), error = ? where id = ?",
                (status, None if result is None else json.dumps(result),
                 None if cost is None else json.dumps(cost), error, run_id))

    def get_run(self, run_id: str, kind: str | None = None) -> dict | None:
        with self._db() as db:
            row = db.execute("select * from runs where id = ? and expires_at > ?",
                             (run_id, self.now().isoformat())).fetchone()
        if row is None or (kind and row["kind"] != kind):
            return None
        out = dict(row)
        for k in ("request_json", "estimate_json", "result_json", "cost_json"):
            out[k[:-5]] = json.loads(out.pop(k)) if out[k] else None
        return out

    def fail_interrupted(self) -> int:
        """Runs left queued/running by a process that died can never finish: mark them failed."""
        with self._db() as db:
            return db.execute(
                "update runs set status = 'failed', error = 'interrupted'"
                " where status in ('queued', 'running')").rowcount

    # ---------------- retention ----------------
    def sweep(self) -> int:
        """Delete everything past its expiry. Returns the number of CVs removed."""
        now = self.now().isoformat()
        with self._db() as db:
            expired = [r[0] for r in db.execute("select id from cvs where expires_at <= ?", (now,))]
            db.execute("delete from runs where expires_at <= ?", (now,))
        for cv_id in expired:
            self.delete_cv(cv_id)
        return len(expired)

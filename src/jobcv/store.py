"""Per-user data store (CVs, runs, scores, PDFs). PERSONAL DATA — kept apart from the job cache.

Everything has an expiry (settings.cv_ttl_hours, default 24h). `sweep()` deletes expired rows
and files; `delete_cv()` removes a CV with all its runs and PDFs immediately.
"""

import json
import logging
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jobcv.config import Settings

log = logging.getLogger(__name__)

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


LOCAL_OWNER = "local"  # the command line. No signed-in user can ever have this id.


def new_id() -> str:
    return uuid.uuid4().hex


class UserStore:
    def __init__(self, settings: Settings, now=lambda: datetime.now(UTC)):
        self.s, self.now = settings, now
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            for table in ("cvs", "runs"):
                columns = {row[1] for row in db.execute(f"pragma table_info({table})")}
                if "user_id" not in columns:  # databases from before accounts
                    db.execute(f"alter table {table} add column user_id text")
            db.execute("create index if not exists cvs_owner on cvs(user_id)")

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.s.user_db, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("pragma secure_delete = on")  # deleted CV text must not linger in the file
        return db

    def _expiry(self) -> tuple[str, str]:
        now = self.now()
        return now.isoformat(), (now + timedelta(hours=self.s.cv_ttl_hours)).isoformat()

    def files_dir(self, cv_id: str) -> Path:
        return self.s.user_files_dir / cv_id

    # ---------------- CVs ----------------
    def add_cv(self, language: str, method: str, raw_text: str, cv_json: str,
               cost: dict, owner: str = LOCAL_OWNER, replace: bool = False) -> str:
        """`replace`: this becomes the owner's only CV, in one step, so parallel uploads
        can't delete each other."""
        cv_id = new_id()
        created, expires = self._expiry()
        replaced: list[str] = []
        with self._db() as db:
            db.execute("begin immediate")
            if replace:
                replaced = [r[0] for r in db.execute("select id from cvs where user_id = ?",
                                                     (owner,))]
            for old in replaced:
                self._delete_rows(db, old)
            db.execute("insert into cvs (id, created_at, expires_at, language, method, raw_text,"
                       " cv_json, cost_json, user_id) values (?,?,?,?,?,?,?,?,?)",
                       (cv_id, created, expires, language, method, raw_text, cv_json,
                        json.dumps(cost), owner))
        for old in replaced:
            self._remove_files(old)
        return cv_id

    def get_cv(self, cv_id: str, owner: str = LOCAL_OWNER) -> sqlite3.Row | None:
        with self._db() as db:
            return db.execute("select * from cvs where id = ? and user_id = ? and expires_at > ?",
                              (cv_id, owner, self.now().isoformat())).fetchone()

    def cv_exists(self, cv_id: str) -> bool:
        """For background work only: anything acting for a user must go through get_cv."""
        with self._db() as db:
            return db.execute("select 1 from cvs where id = ?", (cv_id,)).fetchone() is not None

    def delete_cv(self, cv_id: str, owner: str = LOCAL_OWNER) -> bool:
        with self._db() as db:
            mine = db.execute("select 1 from cvs where id = ? and user_id = ?",
                              (cv_id, owner)).fetchone() is not None
        if mine:
            self._purge(cv_id)
        return mine

    def delete_all(self, owner: str) -> int:
        """Everything of one owner: their CVs, runs and files. Returns how many CVs."""
        with self._db() as db:
            ids = [r[0] for r in db.execute("select id from cvs where user_id = ?", (owner,))]
        for cv_id in ids:
            self._purge(cv_id)
        return len(ids)

    @staticmethod
    def _delete_rows(db: sqlite3.Connection, cv_id: str) -> None:
        db.execute("delete from cvs where id = ?", (cv_id,))
        db.execute("delete from runs where cv_id = ?", (cv_id,))

    def _remove_files(self, cv_id: str) -> None:
        folder = self.files_dir(cv_id)
        shutil.rmtree(folder, ignore_errors=True)
        if folder.exists():  # e.g. a download is still open on Windows
            log.warning("files of cv %s are still in use; the next sweep removes them", cv_id)

    def _purge(self, cv_id: str) -> None:
        with self._db() as db:
            self._delete_rows(db, cv_id)
        self._remove_files(cv_id)

    # ---------------- runs ----------------
    def add_run(self, kind: str, cv_id: str, request: dict, estimate: dict, status: str,
                parent_id: str | None = None, owner: str = LOCAL_OWNER) -> str | None:
        """None if the owner's CV no longer exists; checked in the same statement as the insert
        so that a run can't outlive a CV deleted at this moment."""
        run_id = new_id()
        created, expires = self._expiry()
        with self._db() as db:
            added = db.execute(
                "insert into runs (id, kind, cv_id, parent_id, created_at, expires_at, status,"
                " request_json, estimate_json, user_id) select ?,?,?,?,?,?,?,?,?,?"
                " where exists (select 1 from cvs where id = ? and user_id = ?)",
                (run_id, kind, cv_id, parent_id, created, expires, status, json.dumps(request),
                 json.dumps(estimate), owner, cv_id, owner)).rowcount
        return run_id if added else None

    def update_run(self, run_id: str, *, status: str, result: Any = None, cost: dict | None = None,
                   error: str | None = None) -> None:
        with self._db() as db:
            db.execute(
                "update runs set status = ?, result_json = coalesce(?, result_json),"
                " cost_json = coalesce(?, cost_json), error = ? where id = ?",
                (status, None if result is None else json.dumps(result),
                 None if cost is None else json.dumps(cost), error, run_id))

    def get_run(self, run_id: str, kind: str | None = None,
                owner: str = LOCAL_OWNER) -> dict | None:
        now = self.now().isoformat()
        with self._db() as db:  # a run holds scores and CV text, so it ends when its CV does
            row = db.execute("select r.* from runs r join cvs c on c.id = r.cv_id"
                             " where r.id = ? and r.user_id = ? and r.expires_at > ?"
                             " and c.expires_at > ?", (run_id, owner, now, now)).fetchone()
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
            self._purge(cv_id)
        self._remove_orphan_files()
        return len(expired)

    def _remove_orphan_files(self) -> None:
        """Files with no CV record can't be reached or expired any other way."""
        root = self.s.user_files_dir
        if not root.is_dir():
            return
        with self._db() as db:
            known = {r[0] for r in db.execute("select id from cvs")}
        for folder in root.iterdir():
            if folder.is_dir() and folder.name not in known:
                shutil.rmtree(folder, ignore_errors=True)

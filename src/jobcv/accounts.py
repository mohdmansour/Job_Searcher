"""Free allowance and abuse limits (SPEC-accounts). Kept in its own database, apart from CVs and
the job cache, and holding only Clerk user ids, counters and dollar amounts.

Every claim is one transaction that checks and takes everything at once, so parallel requests
can't both get the last free search or overspend the daily budget. A claim is settled exactly
once when its work ends: that frees the run slot, can refund the allowance, and swaps the
reserved cost for what was really spent.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from jobcv.config import Settings
from jobcv.store import LOCAL_OWNER

Kind = Literal["search", "tailor", "upload"]

SCHEMA = """
create table if not exists usage (
  user_id text primary key, searches integer not null default 0,
  tailors integer not null default 0, bonus_searches integer not null default 0,
  bonus_tailors integer not null default 0);
create table if not exists uploads (
  user_id text, day text, n integer not null default 0, primary key (user_id, day));
create table if not exists spending (day text primary key, usd real not null default 0);
create table if not exists active (user_id text primary key);
create table if not exists redos (tailor_id text, job_id text, primary key (tailor_id, job_id));
"""


class Refused(Exception):
    """A limit was reached. `status` and `code` are what the API answers with."""

    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


@dataclass
class Claim:
    owner: str
    kind: Kind
    n: int = 0
    reserved_usd: float = 0.0
    day: str = ""
    free: bool = False  # unlimited accounts get a claim that settles to nothing
    settled: bool = False


class Accounts:
    def __init__(self, settings: Settings, now=lambda: datetime.now(UTC)):
        self.s, self.now = settings, now
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("pragma table_info(usage)")}
            for col in ("bonus_searches", "bonus_tailors"):  # databases from before grants
                if col not in columns:
                    db.execute(f"alter table usage add column {col} integer not null default 0")

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.s.accounts_db, timeout=30)

    def unlimited(self, owner: str) -> bool:
        return owner == LOCAL_OWNER or owner in self.s.unlimited_user_ids

    def _limit(self, kind: Kind) -> int:
        return self.s.free_searches if kind == "search" else self.s.free_tailors

    def claim(self, owner: str, kind: Kind, n: int = 1, cost_usd: float = 0.0) -> Claim:
        """Takes `n` of the allowance, the run slot (not for uploads), and `cost_usd` of
        today's budget, or raises Refused and takes nothing."""
        if self.unlimited(owner):
            return Claim(owner, kind)
        day = self.now().date().isoformat()
        with self._db() as db:  # rolls back on Refused
            db.execute("begin immediate")
            if kind == "upload":
                db.execute("insert or ignore into uploads (user_id, day) values (?, ?)",
                           (owner, day))
                if not db.execute("update uploads set n = n + 1 where user_id = ? and day = ?"
                                  " and n < ?", (owner, day, self.s.daily_cv_uploads)).rowcount:
                    raise Refused(429, "rate_limited")
            else:
                col = "searches" if kind == "search" else "tailors"
                db.execute("insert or ignore into usage (user_id) values (?)", (owner,))
                if not db.execute(f"update usage set {col} = {col} + ? where user_id = ?"
                                  f" and {col} + ? <= ? + bonus_{col}",
                                  (n, owner, n, self._limit(kind))).rowcount:
                    raise Refused(403, "allowance_used")
                try:
                    db.execute("insert into active (user_id) values (?)", (owner,))
                except sqlite3.IntegrityError:
                    raise Refused(429, "rate_limited") from None
            db.execute("insert or ignore into spending (day) values (?)", (day,))
            if not db.execute("update spending set usd = usd + ? where day = ? and usd + ? <= ?",
                              (cost_usd, day, cost_usd, self.s.daily_free_budget_usd)).rowcount:
                raise Refused(429, "daily_budget")
        return Claim(owner, kind, n if kind != "upload" else 0, cost_usd, day, free=True)

    def settle(self, claim: Claim, refund: int = 0, spent_usd: float | None = None) -> None:
        """When the work ends. `refund`: how much of the allowance to give back. `spent_usd`:
        the real cost (None keeps the reservation)."""
        if not claim.free or claim.settled:
            return
        claim.settled = True
        refund = max(0, min(refund, claim.n))
        delta = 0.0 if spent_usd is None else spent_usd - claim.reserved_usd
        with self._db() as db:
            if refund:
                col = "searches" if claim.kind == "search" else "tailors"
                db.execute(f"update usage set {col} = max({col} - ?, 0) where user_id = ?",
                           (refund, claim.owner))
            if claim.kind != "upload":
                db.execute("delete from active where user_id = ?", (claim.owner,))
            db.execute("update spending set usd = max(usd + ?, 0) where day = ?",
                       (delta, claim.day))

    def grant(self, owner: str, searches: int = 0, tailors: int = 0) -> None:
        """The owner gives one account extra free uses, on top of the normal allowance."""
        if searches < 0 or tailors < 0:
            raise ValueError("a grant adds uses; it can't take them away")
        with self._db() as db:
            db.execute("insert or ignore into usage (user_id) values (?)", (owner,))
            db.execute("update usage set bonus_searches = bonus_searches + ?,"
                       " bonus_tailors = bonus_tailors + ? where user_id = ?",
                       (searches, tailors, owner))

    def claim_redo(self, tailor_id: str, job_id: str) -> None:
        """The one free redo of a tailored CV, taken atomically: a second claim is refused."""
        try:
            with self._db() as db:
                db.execute("insert into redos (tailor_id, job_id) values (?, ?)", (tailor_id, job_id))
        except sqlite3.IntegrityError:
            raise Refused(403, "redo_used") from None

    def release_redo(self, tailor_id: str, job_id: str) -> None:
        """A redo that produced no CV is given back."""
        with self._db() as db:
            db.execute("delete from redos where tailor_id = ? and job_id = ?", (tailor_id, job_id))

    def redo_used(self, tailor_id: str, job_id: str) -> bool:
        with self._db() as db:
            return db.execute("select 1 from redos where tailor_id = ? and job_id = ?",
                              (tailor_id, job_id)).fetchone() is not None

    def clear_active(self) -> None:
        """At server start: runs of a server that stopped can never finish."""
        with self._db() as db:
            db.execute("delete from active")

    def status(self, owner: str) -> dict:
        with self._db() as db:
            row = db.execute("select searches, tailors, bonus_searches, bonus_tailors from usage"
                             " where user_id = ?", (owner,)).fetchone() or (0, 0, 0, 0)
        return {"free_searches_left": max(self.s.free_searches + row[2] - row[0], 0),
                "free_tailors_left": max(self.s.free_tailors + row[3] - row[1], 0),
                "unlimited": self.unlimited(owner),
                "free_max_results": self.s.free_max_results}

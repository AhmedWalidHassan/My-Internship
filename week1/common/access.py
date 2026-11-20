"""
Week 3 Task 6 — who's asking. The user directory, access scopes, and the ONE ACL check that every
path to a passage goes through (both retrievers, the Task 5 version catalog, the graph's retrieve
node).

Rules, each one a decision (week3/task_06_who_is_asking/ACCESS.md):

* Groups come from `_directory.csv`, looked up by `user_id`. Never from the request body, the
  question or the conversation. An unknown user is an error (401), never a default user.
* A chunk is visible when its `acl_groups` intersect the user's groups.
* A chunk with NO ACL metadata is visible to NO ONE (fail closed). "Visible to everyone" would turn
  every metadata bug (a missing column, a loader that drops a field) into a silent leak; "visible
  to no one" turns it into a missing answer, which the eval and the ingestion log both show.
* The access scope is identified by a hash of the sorted group set: it keys the answer cache and
  is logged, so logs show who could see what without listing group names.
* A directory that is missing, unreadable or malformed is an outage (503), not "everyone is an
  employee": the service can't tell who is asking, so it answers no one.
"""

from __future__ import annotations

import csv
import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

PUBLIC = frozenset({"all"})          # what everyone in the directory has; also the CLI's default scope


class UnknownUser(Exception):
    """The user_id is not in the directory (or no user_id was given)."""


class DirectoryUnavailable(Exception):
    """The directory file is missing, unreadable or malformed: nobody can be identified."""


@dataclass(frozen=True)
class User:
    user_id: str
    groups: frozenset
    name: str = ""
    title: str = ""
    department: str = ""
    office: str = ""
    hire_date: str = ""

    @property
    def scope(self) -> str:
        return scope_id(self.groups)


def parse_groups(raw) -> frozenset:
    """'all;managers' -> {'all', 'managers'} (';' or ',' separated, blanks dropped)."""
    return frozenset(g.strip() for g in str(raw or "").replace(",", ";").split(";") if g.strip())


def chunk_groups(meta: dict) -> frozenset | None:
    """The groups allowed to see a chunk, or None when it has no ACL metadata."""
    groups = parse_groups(meta.get("acl_groups"))
    return groups or None


def can_see(meta: dict, groups) -> bool:
    """THE access check. No ACL metadata -> visible to no one."""
    acl = chunk_groups(meta)
    return acl is not None and not acl.isdisjoint(groups)


def is_restricted(meta: dict) -> bool:
    """Anything not open to every employee (a chunk without an ACL counts as restricted)."""
    return chunk_groups(meta) != PUBLIC


def scope_id(groups) -> str:
    """A stable, opaque id for a group set: 'all|hr' -> 'a1b2c3d4e5f6'. Same groups, same id."""
    return hashlib.sha256("|".join(sorted(groups)).encode()).hexdigest()[:12]


class Directory:
    """`_directory.csv` (user_id, name, title, department, office, groups, hire_date), re-read when the
    file changes, so a group change applies to the next request without a restart."""

    REQUIRED = ("user_id", "groups")

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._stamp = None
        self._users: dict[str, User] = {}

    def _load(self) -> dict[str, User]:
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
            if stamp == self._stamp:
                return self._users
            with self.path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
                fields = rows[0].keys() if rows else ()
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            raise DirectoryUnavailable(f"user directory {self.path} unreadable: {type(e).__name__}") from e
        missing = [c for c in self.REQUIRED if c not in fields]
        if not rows or missing:
            raise DirectoryUnavailable(f"user directory {self.path} has no users"
                                       + (f" (missing columns: {', '.join(missing)})" if missing else ""))
        users: dict[str, User] = {}
        for r in rows:
            uid = (r.get("user_id") or "").strip()
            if not uid:
                continue
            if uid in users:   # two rows, two group sets: which one is true? Neither is safe to pick.
                raise DirectoryUnavailable(f"user directory {self.path}: user_id {uid} listed twice")
            users[uid] = User(uid, parse_groups(r.get("groups")), *(
                (r.get(k) or "").strip() for k in ("name", "title", "department", "office", "hire_date")))
        self._stamp, self._users = stamp, users
        return users

    def lookup(self, user_id: str | None) -> User:
        """The user, or UnknownUser (-> 401). DirectoryUnavailable (-> 503) if the file can't be read."""
        with self._lock:
            users = self._load()
        if not user_id or user_id not in users:
            raise UnknownUser(user_id or "")
        return users[user_id]

    def check(self) -> int:
        """How many users the directory holds (readiness); raises DirectoryUnavailable."""
        with self._lock:
            return len(self._load())

"""In-process synchronization for resources that are not yet database-locked.

`RateLimitService` uses `pg_advisory_xact_lock` / `BEGIN IMMEDIATE` to make
abuse-control counters race-safe across processes. The in-memory / JSON-file
resource stores (documents, reviews, tasks) don't have that yet -- their
"count existing rows, then check quota, then write" sequence can interleave
across concurrent requests (FastAPI runs sync path functions in a
threadpool, and `await` points yield the event loop for async ones), letting
two simultaneous requests both pass a quota check that should only allow one
of them through.

`guarded()` closes that race for a single process by serializing the
check-and-write block per (resource, identity) key. It does NOT protect a
horizontally scaled deployment (multiple processes/instances) -- that needs
the same database-level locking `RateLimitService` already uses. Tracked as
a Sprint 2 follow-up: move quota-checked writes onto `PostgresApplicationStore`
with real DB constraints/locks instead of this in-process guard.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import threading

_registry_lock = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _get_lock(key: str) -> threading.Lock:
    with _registry_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


@contextmanager
def guarded(*key_parts: str) -> Iterator[None]:
    """Serialize the wrapped block against other callers sharing this key."""
    key = "\0".join(key_parts)
    lock = _get_lock(key)
    with lock:
        yield

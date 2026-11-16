"""Per-session conversation memory with a sliding TTL.

WHERE THE STATE LIVES: in this process's memory. That is correct for one worker
and wrong for two. With `uvicorn --workers 2`, every worker has its own store, so:

  * a follow-up that lands on worker B has no history from worker A ("it" is
    never resolved), and the user sees the assistant forget mid-conversation;
  * DELETE /session/{id} only clears the copy on the worker that served it;
  * each worker also loads its own index and embedding model (memory x N).

The fix is to move this mapping out of the process: Redis (one key per session,
EXPIRE = the TTL) or a LangGraph checkpointer keyed by thread_id = session_id.
The Assistant only needs a dict-like object (`get`, `setdefault`, `pop`), so that
swap does not touch the graph. Sticky sessions at the load balancer would hide
the problem but lose every conversation whenever a worker restarts.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator, MutableMapping


class SessionStore(MutableMapping):
    """session_id -> list of (question, answer) turns.

    * Sliding TTL: a session expires `ttl_seconds` after it was last read or
      written, so an active conversation never expires mid-way.
    * Bounded: beyond `max_sessions`, the least recently used session is dropped,
      so a client inventing a new session_id per request can't exhaust memory.
    * Thread-safe per operation (the API runs requests in a thread pool). Two
      concurrent requests in the SAME session can still interleave their turns;
      that's a client bug we don't try to serialise.
    """

    def __init__(self, ttl_seconds: float = 3600, max_sessions: int = 10_000,
                 clock: Callable[[], float] = time.monotonic):
        self.ttl = float(ttl_seconds)
        self.max_sessions = int(max_sessions)
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, list]] = OrderedDict()   # oldest access first
        self._lock = threading.RLock()

    def _expired(self, last_seen: float, now: float) -> bool:
        return now - last_seen > self.ttl

    def _purge(self, now: float) -> None:
        """Drop expired sessions. They sit at the front (least recently used first)."""
        while self._data:
            key, (last_seen, _) = next(iter(self._data.items()))
            if not self._expired(last_seen, now):
                break
            del self._data[key]

    def __getitem__(self, session_id: str) -> list:
        with self._lock:
            now = self._clock()
            last_seen, turns = self._data[session_id]          # KeyError if unknown
            if self._expired(last_seen, now):
                del self._data[session_id]
                raise KeyError(session_id)
            self._data[session_id] = (now, turns)              # touch
            self._data.move_to_end(session_id)
            return turns

    def __setitem__(self, session_id: str, turns: list) -> None:
        with self._lock:
            now = self._clock()
            self._purge(now)
            self._data[session_id] = (now, turns)
            self._data.move_to_end(session_id)
            while len(self._data) > self.max_sessions:
                self._data.popitem(last=False)

    def __delitem__(self, session_id: str) -> None:
        with self._lock:
            del self._data[session_id]

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            self._purge(self._clock())
            return iter(list(self._data))

    def __len__(self) -> int:
        with self._lock:
            self._purge(self._clock())
            return len(self._data)

"""Thread-safe sliding-window QPS rate limiter for auxiliary model API calls.

Each auxiliary model has a ``qps`` (queries per second) setting.
When multiple documents are indexed in parallel threads, all threads share
this limiter so aggregate call rate never exceeds the model's QPS limit.

Usage::

    from auxmodels.rate_limiter import acquire
    acquire(model_id=3, qps=5)   # blocks until a slot is available
    response = llm.invoke(...)   # guaranteed to be within QPS budget
"""

from __future__ import annotations

import threading
import time
from collections import deque

# One deque per model_id, protected by a single global lock.
# The deque stores the monotonic timestamps of recent calls.
_lock: threading.Lock = threading.Lock()
_windows: dict[int, deque[float]] = {}


def try_acquire(model_id: int, qps: int) -> bool:
    """Non-blocking: return *True* if a QPS slot was consumed, *False* if over-budget.

    Useful in async HTTP handlers where blocking is unacceptable.
    """
    if qps <= 0:
        return True
    with _lock:
        now = time.monotonic()
        window = _windows.setdefault(model_id, deque())
        cutoff = now - 1.0
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) < qps:
            window.append(now)
            return True
        return False


def acquire(model_id: int, qps: int) -> None:
    """Block the calling thread until a QPS slot is available.

    Parameters
    ----------
    model_id: Unique ID of the AIModel whose QPS budget to consume.
    qps:      Maximum allowed calls per second (0 or negative = unlimited).
    """
    if qps <= 0:
        return  # unlimited — no throttling

    while True:
        with _lock:
            now = time.monotonic()
            window = _windows.setdefault(model_id, deque())

            # Evict timestamps that have fallen outside the 1-second window
            cutoff = now - 1.0
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) < qps:
                # Slot available — record this call and return
                window.append(now)
                return

            # Over budget — calculate how long until the oldest call expires
            sleep_until = window[0] + 1.0

        # Sleep outside the lock so other threads can make progress
        sleep_for = sleep_until - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

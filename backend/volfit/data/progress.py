"""Progress hook for long DATA-LAYER operations (a chain download, a paged
history pull) — the data layer knows how far it got, the api layer owns the
narration (volfit.api.activity), and this tiny contextvar bridge keeps the
dependency pointing the right way (api -> data, never data -> api).

    # api layer, around a fetch:
    with progress.bind(lambda done, total, label: handle.update(...)):
        provider.fetch_chain(...)

    # data layer, inside the download loop:
    progress.report(bytes_so_far, content_length, "3.2 / 13.0 MB")

``report`` is a no-op when nothing is bound (tests, scripts, the scheduler's
own probes), so providers can call it unconditionally. Context variables are
per thread/task: a worker thread that binds its own callback narrates its own
download.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Callable, Iterator

ProgressCallback = Callable[[int, int, str], None]

_current: contextvars.ContextVar[ProgressCallback | None] = contextvars.ContextVar(
    "volfit_data_progress", default=None
)


def report(done: int, total: int = 0, label: str = "") -> None:
    """Report progress of the current bound operation (no-op when unbound).
    ``total`` 0 = indeterminate; ``label`` is the human caption ("3.2 / 13.0 MB")."""
    cb = _current.get()
    if cb is not None:
        try:
            cb(int(done), int(total), label)
        except Exception:  # noqa: BLE001 — narration must never break a fetch
            pass


@contextmanager
def bind(callback: ProgressCallback | None) -> Iterator[None]:
    """Route ``report`` calls to ``callback`` for the duration of the block."""
    token = _current.set(callback)
    try:
        yield
    finally:
        _current.reset(token)


def bytes_label(done: int, total: int) -> str:
    """"3.2 / 13.0 MB" (or "3.2 MB" with no known total)."""
    mb = 1e6
    if total > 0:
        return f"{done / mb:.1f} / {total / mb:.1f} MB"
    return f"{done / mb:.1f} MB"

"""Where providers keep small on-disk caches (contract listings, ladders).

One convention for every provider: ``VOLFIT_CACHE_DIR`` when set, else
``<backend>/data/cache`` (gitignored). Files are per (provider, key, exchange
day) so a stale day is never reused; a missing or unwritable directory only
disables the cache (a fetch never fails on a cache)."""

from __future__ import annotations

import os
from pathlib import Path

#: Default location, relative to the backend package root.
_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "cache"


def cache_dir(subdir: str | None = None, create: bool = True) -> Path | None:
    """The cache directory (optionally a provider sub-directory), created on
    demand; None when it cannot be created (the caller then skips caching)."""
    root = Path(os.environ.get("VOLFIT_CACHE_DIR") or _DEFAULT)
    path = root / subdir if subdir else root
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
    return path

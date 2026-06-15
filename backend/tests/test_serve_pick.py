"""Startup data-source auto-pick (serve._pick_active).

The active source on launch must be one that can actually SERVE data, not merely
connect — otherwise a connected-but-capped Bloomberg (its feed_status is now a
cheap connectivity check that can't see the daily cap) would be auto-picked and
the app would boot on an empty surface. Invariants:

1. A forced source is honoured verbatim.
2. A connected feed that can't resolve a ladder (capped/gated) is skipped for the
   next source that serves.
3. Synthetic always serves and is the final fallback.
"""

from datetime import date

import serve
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)


class _Capped(SyntheticProvider):
    """Connects (green) but every data request is refused — a capped/gated feed."""

    def feed_status(self):
        return ("green", "connected")

    def available_expiries(self, ticker):
        raise RuntimeError("daily capacity reached")


class _Serving(SyntheticProvider):
    """Reachable and serves ladders normally (stands in for a healthy Yahoo)."""

    def feed_status(self):
        return ("amber", "delayed")


def _providers():
    return {
        "bloomberg": _Capped(reference_date=REF),
        "yahoo": _Serving(reference_date=REF),
        "synthetic": SyntheticProvider(reference_date=REF),
    }


def test_forced_source_is_honoured():
    assert serve._pick_active(_providers(), "bloomberg") == "bloomberg"


def test_capped_source_skipped_for_one_that_serves():
    # Bloomberg connects but can't serve -> auto-pick falls through to Yahoo.
    assert serve._pick_active(_providers(), "") == "yahoo"


def test_synthetic_is_the_final_fallback():
    only_capped = {"bloomberg": _Capped(reference_date=REF),
                   "synthetic": SyntheticProvider(reference_date=REF)}
    assert serve._pick_active(only_capped, "") == "synthetic"


def test_can_serve_true_for_a_healthy_feed():
    assert serve._can_serve(_Serving(reference_date=REF)) is True
    # Fewer attempts / no gap keeps the capped probe quick in the test.
    assert serve._can_serve(_Capped(reference_date=REF), attempts=1, gap=0.0) is False

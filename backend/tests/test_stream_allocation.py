"""The live-slot allocation policy (volfit.data.stream_allocation): focus
first, the per-ticker floor, the fair share of the remainder — deterministic
and stable, on SPY / NVDA-shaped plans (10,000 vs 1,600 planned contracts,
a 950 budget) and small hand-checkable ones."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from volfit.data.stream_allocation import (
    STREAM_TICKER_FLOOR,
    allocate,
    normalize_focus,
    ticker_floor,
)

#: The fixture ladder: daily rungs from the Oct-16 monthly on.
FIRST_EXPIRY = date(2026, 10, 16)


def _plan(ticker: str, expiries: int, per_expiry: int) -> tuple[list[str], dict[str, str]]:
    """A ranked plan: rank r cycles the expiries so every rung's belly comes
    first (like |ln K/S| / sqrt(T) does on a real ladder); returns the
    contracts in rank order and their expiry map."""
    contracts, expiry_of = [], {}
    for r in range(per_expiry):
        for e in range(expiries):
            c = f"O:{ticker}:E{e:02d}:R{r:04d}"
            contracts.append(c)
            expiry_of[c] = (FIRST_EXPIRY + timedelta(days=e)).isoformat()
    return contracts, expiry_of


@pytest.fixture
def desk():
    spy, spy_exp = _plan("SPY", 25, 400)  # 10,000 planned
    nvda, nvda_exp = _plan("NVDA", 9, 178)  # 1,602 planned
    expiry_of = {**spy_exp, **nvda_exp}
    return {"SPY": spy, "NVDA": nvda}, expiry_of


def _live_of(alloc, ticker: str) -> list[str]:
    return [c for c in alloc.live if c.startswith(f"O:{ticker}:")]


def test_fair_share_gives_every_ticker_its_floor_and_half_the_budget(desk):
    """Without a focus the budget is split round-robin: SPY and NVDA each get
    475 (NVDA well above its 60 floor) instead of 874 / 76 by global rank."""
    plans, expiry_of = desk
    alloc = allocate(plans, set(), 950, floor=60, expiry_of=expiry_of.get)
    assert len(alloc.live) == 950 and len(alloc.dropped) == 11_602 - 950
    assert alloc.shares["SPY"].live == 475 and alloc.shares["NVDA"].live == 475
    assert alloc.shares["NVDA"].live >= STREAM_TICKER_FLOOR
    assert alloc.shares["SPY"].requested == 10_000 and alloc.shares["NVDA"].requested == 1602
    # each ticker's live set is a rank PREFIX of its own plan
    assert _live_of(alloc, "SPY") == plans["SPY"][:475]
    assert _live_of(alloc, "NVDA") == plans["NVDA"][:475]
    # the priority order interleaves the rounds (NVDA before SPY by name)
    assert alloc.live[:4] == [plans["NVDA"][0], plans["SPY"][0], plans["NVDA"][1], plans["SPY"][1]]
    assert alloc.focus == [] and alloc.as_dict()["tickers"]["NVDA"]["live"] == 475


def test_focus_node_gets_its_whole_planned_rung_then_the_rest_is_shared(desk):
    """NVDA's Oct-16 rung in focus: every one of its 178 planned contracts is
    live (nearest-the-money first), the remaining 772 slots are shared
    equally — SPY 386, NVDA 386 more (the focus is not charged against
    NVDA's share of the remainder)."""
    plans, expiry_of = desk
    rung = [c for c in plans["NVDA"] if expiry_of[c] == "2026-10-16"]
    assert len(rung) == 178
    alloc = allocate(plans, {("NVDA", "2026-10-16")}, 950, floor=60, expiry_of=expiry_of.get)
    assert alloc.live[:178] == rung  # the focus first, in rank order
    assert set(rung) <= set(alloc.live)
    assert alloc.shares["NVDA"].focus == 178 and alloc.shares["NVDA"].live == 178 + 386
    assert alloc.shares["SPY"].live == 386 and alloc.shares["SPY"].focus == 0
    assert len(alloc.live) == 950
    assert alloc.focus == [("NVDA", "2026-10-16")]
    # the non-focus part of NVDA is still a rank prefix of its plan minus the rung
    rest = [c for c in plans["NVDA"] if c not in set(rung)]
    assert [c for c in _live_of(alloc, "NVDA") if c not in set(rung)] == rest[:386]


def test_focus_cannot_starve_a_ticker_below_its_floor():
    """A focus rung larger than the budget: the focus-less ticker's floor is
    reserved first, the focus takes the rest (its nearest-the-money), the
    floor phase then tops up the other ticker to exactly its floor."""
    spy, spy_exp = _plan("SPY", 1, 1200)  # one 1,200-contract rung
    nvda, nvda_exp = _plan("NVDA", 3, 100)
    expiry_of = {**spy_exp, **nvda_exp}
    alloc = allocate({"SPY": spy, "NVDA": nvda}, {("SPY", "2026-10-16")}, 950, floor=60, expiry_of=expiry_of.get)
    assert alloc.shares["NVDA"].live == 60 and alloc.shares["SPY"].live == 890
    assert alloc.shares["SPY"].focus == 890
    assert _live_of(alloc, "SPY") == spy[:890] and _live_of(alloc, "NVDA") == nvda[:60]
    assert len(alloc.live) == 950


def test_small_plans_take_what_they_have_and_free_the_rest():
    """A ticker whose plan is smaller than its share leaves the round; the
    others absorb the slots; nothing is dropped when everything fits."""
    a, _ = _plan("AAA", 1, 5)
    b, _ = _plan("BBB", 1, 50)
    alloc = allocate({"AAA": a, "BBB": b}, set(), 30, floor=10)
    assert alloc.shares["AAA"].live == 5 and alloc.shares["BBB"].live == 25
    fits = allocate({"AAA": a, "BBB": b}, set(), 100, floor=10)
    assert fits.dropped == [] and len(fits.live) == 55
    assert allocate({"AAA": a}, set(), 0).live == []
    assert allocate({}, set(), 10).live == [] and allocate({"AAA": []}, set(), 10).shares == {}


def test_unknown_pseudo_ticker_keeps_input_order():
    """Contracts of unknown ticker are passed under one pseudo key in input
    order: the cap is a prefix of that order (the pre-policy behaviour)."""
    alloc = allocate({"": ["O:A", "O:B", "O:C", "O:D"]}, set(), 3)
    assert alloc.live == ["O:A", "O:B", "O:C"] and alloc.dropped == ["O:D"]


def test_deterministic_and_stable_under_a_no_op_replan(desk):
    """Same inputs → byte-identical answer (the callers diff the sets); an
    unrelated focus change on one ticker moves only the OTHER ticker's far end
    (its live set stays a prefix — no reshuffle)."""
    plans, expiry_of = desk
    focus = {("NVDA", "2026-10-16")}
    first = allocate(plans, focus, 950, floor=60, expiry_of=expiry_of.get)
    again = allocate(dict(reversed(list(plans.items()))), set(focus), 950, floor=60, expiry_of=expiry_of.get)
    assert again.live == first.live and again.dropped == first.dropped and again.shares == first.shares
    moved = allocate(plans, {("NVDA", "2026-10-17")}, 950, floor=60, expiry_of=expiry_of.get)
    spy_before, spy_after = _live_of(first, "SPY"), _live_of(moved, "SPY")
    shorter = min(len(spy_before), len(spy_after))
    assert spy_before[:shorter] == spy_after[:shorter]  # a prefix either way
    assert abs(len(spy_before) - len(spy_after)) <= 1  # same-size rungs: ±1 at the far end


def test_duplicates_and_case_are_normalised():
    a = ["O:X", "O:X", "O:Y"]
    alloc = allocate({"spy": a}, {("spy", " 2026-10-16 ")}, 5, expiry_of=lambda c: "2026-10-16")
    assert alloc.live == ["O:X", "O:Y"] and alloc.shares["SPY"].focus == 2
    assert alloc.focus == [("SPY", "2026-10-16")]
    assert normalize_focus([("nvda", "2026-10-16")]) == {("NVDA", "2026-10-16")}


def test_floor_env_knob(monkeypatch):
    monkeypatch.delenv("VOLFIT_MASSIVE_WS_FLOOR", raising=False)
    assert ticker_floor() == STREAM_TICKER_FLOOR == 60
    monkeypatch.setenv("VOLFIT_MASSIVE_WS_FLOOR", "120")
    assert ticker_floor() == 120
    monkeypatch.setenv("VOLFIT_MASSIVE_WS_FLOOR", "junk")
    assert ticker_floor() == 60
    monkeypatch.setenv("VOLFIT_MASSIVE_WS_FLOOR", "-5")
    assert ticker_floor() == 0

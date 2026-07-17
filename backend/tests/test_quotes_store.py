"""Offline tests for the backtest NBBO quotes flat-file reader.

Uses the ``source_uri`` hook to point the store at a tiny local CSV with the real
``quotes_v1`` schema, so the duckdb reduction (last NBBO per contract at-or-before
the target instant) runs fully offline — no S3, no credentials.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

pytest.importorskip("duckdb")  # flatfiles extra (pyproject): optional, lazily imported

from backtest.quotes_store import QuotesFlatFileStore, _to_ns  # noqa: E402

EXPIRY = date(2024, 8, 16)
TARGET = datetime(2024, 8, 16, 19, 45, 0)  # 15:45 ET, UTC-naive
_T = _to_ns(TARGET)

#: quotes_v1 header (probed live 2026-06-21).
HEADER = (
    "ticker,ask_exchange,ask_price,ask_size,bid_exchange,bid_price,bid_size,"
    "sequence_number,sip_timestamp"
)


def _row(sym: str, bid: float, ask: float, ns: int) -> str:
    return f"{sym},1,{ask},10,1,{bid},10,0,{ns}"


def _write_fixture(path) -> None:
    """Three paired strikes (C/P) at F=545, each with an early, a chosen (just
    before target) and an after-target quote that must be excluded."""
    rows = [HEADER]
    # (strike, call_mid, put_mid) consistent with F=545, D=1: C-P = F-K.
    book = [(540, 8.0, 3.0), (545, 5.0, 5.0), (550, 3.0, 8.0)]
    for strike, cmid, pmid in book:
        digits = f"{int(strike * 1000):08d}"
        for cp, mid in (("C", cmid), ("P", pmid)):
            sym = f"O:SPY240816{cp}{digits}"
            # stale quote (wide), then the chosen NBBO just before target, then a
            # post-target quote with a wrong price that must NOT be selected.
            rows.append(_row(sym, mid - 0.5, mid + 0.5, _T - 5_000_000_000))
            rows.append(_row(sym, mid - 0.1, mid + 0.1, _T - 1_000_000_000))
            rows.append(_row(sym, 99.0, 99.0, _T + 1_000_000_000))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture()
def store(tmp_path):
    csv = tmp_path / "quotes.csv"
    _write_fixture(csv)
    return QuotesFlatFileStore(source_uri=lambda _day: str(csv))


def test_reconstructs_real_bid_ask_at_target(store):
    chain = store.chain_at("SPY", [EXPIRY], TARGET)
    assert chain is not None
    assert chain.exercise_style == "american"
    assert len(chain.quotes) == 6  # 3 strikes x {C, P}
    # The chosen NBBO is the just-before-target one (spread 0.2), not the stale
    # (spread 1.0) nor the post-target (99/99).
    atm_call = next(q for q in chain.quotes if q.call_put == "C" and q.strike == 545.0)
    assert atm_call.bid == pytest.approx(4.9)
    assert atm_call.ask == pytest.approx(5.1)
    assert atm_call.mid == pytest.approx(5.0)


def test_parity_spot_recovered(store):
    chain = store.chain_at("SPY", [EXPIRY], TARGET)
    assert chain is not None
    assert chain.spot == pytest.approx(545.0, abs=0.2)


def test_index_style_override(store):
    chain = store.chain_at("SPY", [EXPIRY], TARGET, exercise_style="european")
    assert chain is not None
    assert chain.exercise_style == "european"


def test_after_target_only_returns_none(store):
    # A target before every quote in the file → nothing at-or-before it.
    early = datetime(2024, 8, 16, 0, 0, 0)
    assert store.chain_at("SPY", [EXPIRY], early) is None


def test_zero_bid_becomes_one_sided(tmp_path):
    csv = tmp_path / "q.csv"
    sym = f"O:SPY240816C{int(545 * 1000):08d}"
    csv.write_text(
        HEADER + "\n" + _row(sym, 0.0, 0.30, _T - 1_000_000_000) + "\n",
        encoding="utf-8",
    )
    store = QuotesFlatFileStore(source_uri=lambda _day: str(csv))
    chain = store.chain_at("SPY", [EXPIRY], TARGET)
    # A single one-sided (0-bid) quote → no parity pair → no usable chain.
    assert chain is None

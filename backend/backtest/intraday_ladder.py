"""Expiry ladders for the intraday 0DTE captures (R2 item 10 / V3.8).

Pure selection logic shared by both capture twins (``capture_intraday`` flat
files, ``capture_intraday_rest``): given the expiries actually listed on the
day's board, which rungs the fixture keeps. Split out of ``capture_intraday``
(the 400-line policy); every name is re-exported there, so
``from backtest.capture_intraday import LADDERS`` still works.
"""

from __future__ import annotations

from datetime import date

#: Expiry ladder kept per day: every expiry within MAX_DAILY_DTE calendar days
#: (the 0DTE/daily structure under study) plus up to TERM_ANCHORS third-Friday
#: monthlies within TERM_ANCHOR_MAX_DTE (the term/calendar anchor the fits and
#: the graph need). Everything else on the OPRA board is dropped.
MAX_DAILY_DTE = 7
TERM_ANCHORS = 2
TERM_ANCHOR_MAX_DTE = 90

#: ``--ladder term`` shape: the DAILY capture's term-structure ladder
#: (capture.py: MIN/MAX_DTE 7/400, 10 expiries, 3 front weeklies) adapted to
#: the intraday horizon — front weeklies + third-Friday monthlies out to
#: TERM_MAX_DTE, capped at the TERM_MAX_EXPIRIES nearest. Same-day expiries
#: are excluded (the intraday replay drops 0DTE rungs anyway: calendar t = 0
#: in the graph clock — see graph_intraday.instant_state).
TERM_MAX_DTE = 120
TERM_MAX_EXPIRIES = 6
TERM_FRONT_WEEKLIES = 3


def _is_monthly(e: date) -> bool:
    return e.weekday() == 4 and 15 <= e.day <= 21


def select_expiries(available: set[date], day: date) -> list[date]:
    """The kept ladder: dailies (DTE <= MAX_DAILY_DTE) + nearby monthlies."""
    dailies = [e for e in available if 0 <= (e - day).days <= MAX_DAILY_DTE]
    monthlies = sorted(
        e for e in available
        if _is_monthly(e) and MAX_DAILY_DTE < (e - day).days <= TERM_ANCHOR_MAX_DTE
    )[:TERM_ANCHORS]
    return sorted(set(dailies) | set(monthlies))


def select_expiries_term(available: set[date], day: date) -> list[date]:
    """``--ladder term``: all in-range monthlies (1 <= DTE <= TERM_MAX_DTE)
    plus the nearest TERM_FRONT_WEEKLIES non-monthly expiries, capped at the
    TERM_MAX_EXPIRIES nearest overall — capture.py's daily selection shape on
    the intraday ``select_expiries`` signature. 0DTE is deliberately excluded
    (see the TERM_* constants note)."""
    cand = sorted(e for e in available if 1 <= (e - day).days <= TERM_MAX_DTE)
    monthlies = [e for e in cand if _is_monthly(e)]
    chosen = set(monthlies)
    for e in (e for e in cand if not _is_monthly(e)):
        if len(chosen) >= len(monthlies) + TERM_FRONT_WEEKLIES:
            break
        chosen.add(e)
    return sorted(chosen)[:TERM_MAX_EXPIRIES]


#: --ladder name -> selector. "0dte" IS select_expiries (default, byte-identical).
LADDERS = {"0dte": select_expiries, "term": select_expiries_term}

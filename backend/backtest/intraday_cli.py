"""Shared CLI surface of the two intraday capture twins (flat files + REST).

The sampling grid (``--times`` XOR ``--step [--from --to]``), the expiry
``--ladder`` and the OCC ``--roots`` override are parsed identically by
``capture_intraday`` and ``capture_intraday_rest``. Split out of
``capture_intraday`` (the 400-line policy); every name is re-exported there,
so ``from backtest.capture_intraday import grid_times`` still works.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta

from backtest.intraday_ladder import LADDERS, TERM_MAX_DTE, TERM_MAX_EXPIRIES
from backtest.roots import parse_roots_arg

#: Default intraday sampling: every 30 minutes from 10:00 ET (past the opening
#: auction noise) to 15:30, plus the 15:45 before-close instant the daily
#: capture uses (so the two campaigns share a comparable end-of-day point).
DEFAULT_TIMES = tuple(
    time(h, m) for h in range(10, 16) for m in (0, 30) if not (h == 15 and m == 30)
) + (time(15, 30), time(15, 45))

#: ``--step`` grid defaults (V3.8 replay campaign): 09:45 ET (past the opening
#: auction) to 15:45 ET (the daily capture's before-close instant).
GRID_FROM = time(9, 45)
GRID_TO = time(15, 45)


def _parse_times(raw: str | None) -> tuple[time, ...]:
    if not raw:
        return DEFAULT_TIMES
    return tuple(time.fromisoformat(part.strip()) for part in raw.split(","))


def grid_times(step_min: int, t_from: time = GRID_FROM, t_to: time = GRID_TO) -> tuple[time, ...]:
    """Regular ET wall-time grid ``t_from..t_to`` INCLUSIVE every ``step_min``
    minutes (the V3.8 15-minute campaign grid). ``session_instants`` still
    clips at the session close, so half-days keep only surviving instants."""
    if step_min <= 0:
        raise ValueError("--step must be a positive number of minutes")
    anchor = date(2000, 1, 3)  # any fixed day: only the wall times survive
    cur, end = datetime.combine(anchor, t_from), datetime.combine(anchor, t_to)
    out: list[time] = []
    while cur <= end:
        out.append(cur.time())
        cur += timedelta(minutes=step_min)
    return tuple(out)


def resolve_times(times: str | None, step: int | None,
                  t_from: str | None, t_to: str | None) -> tuple[time, ...]:
    """Shared CLI grid resolution for BOTH capture twins: ``--times`` XOR
    ``--step [--from --to]``; neither given = DEFAULT_TIMES (the legacy grid,
    byte-identical)."""
    if step is not None and times:
        raise SystemExit("--times and --step are mutually exclusive")
    if step is None:
        if t_from or t_to:
            raise SystemExit("--from/--to require --step")
        return _parse_times(times)
    return grid_times(step,
                      time.fromisoformat(t_from) if t_from else GRID_FROM,
                      time.fromisoformat(t_to) if t_to else GRID_TO)


def add_grid_args(ap: argparse.ArgumentParser) -> None:
    """The shared --times/--step/--from/--to/--ladder CLI block (both twins)."""
    ap.add_argument("--times", default=None,
                    help="comma-separated ET wall times (default 10:00..15:45)")
    ap.add_argument("--step", type=int, default=None,
                    help="regular grid in minutes (e.g. 15); excludes --times")
    ap.add_argument("--from", dest="grid_from", default=None, metavar="HH:MM",
                    help="grid start, ET wall time (default 09:45; needs --step)")
    ap.add_argument("--to", dest="grid_to", default=None, metavar="HH:MM",
                    help="grid end, ET wall time (default 15:45; needs --step)")
    ap.add_argument("--ladder", choices=tuple(LADDERS), default="0dte",
                    help="expiry ladder: 0dte (dailies + 2 monthly anchors, the"
                         " default) or term (front weeklies + monthlies to"
                         f" {TERM_MAX_DTE} DTE, capped at {TERM_MAX_EXPIRIES})")


def add_roots_arg(ap: argparse.ArgumentParser) -> None:
    """The shared ``--roots`` override flag (both twins; grammar in backtest.roots)."""
    ap.add_argument("--roots", action="append", default=None,
                    metavar="TICKER=ROOT,ROOT[;TICKER=...]",
                    help="OCC roots per ticker, e.g. 'SPX=SPX,SPXW;NDX=NDX,NDXP'"
                         " (single-quote it in PowerShell: ';' and ',' are"
                         " shell-active); repeatable. Default: the universe"
                         " registry (SPX/NDX/RUT), else the ticker itself")


def roots_override_from_args(args: argparse.Namespace) -> dict[str, tuple[str, ...]] | None:
    """``--roots`` values (possibly repeated) -> the override map, or None."""
    return parse_roots_arg(";".join(args.roots)) if args.roots else None

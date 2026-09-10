"""``python -m backtest.fixture_scan [--regime R] [--asset A]`` — list the fixtures
that carry two contracts per (expiry, strike, side) and what the replay-time
hygiene (backtest.fixture_hygiene) drops from each. Read-only: nothing on disk
changes; the same function runs on every ``replay.load_fixture``.

One row per affected fixture: asset · as-of · per expiry the duplicate keys,
the dropped quotes and the kept series rank (low / high / mixed) · the quote
count before → after; then a summary line. Exit 0 always (a report, not a gate).
"""

from __future__ import annotations

import argparse
import json
import os

from backtest.replay import DEDUPE_ENV, list_fixtures, load_fixture


def scan(regime: str | None = None, asset: str | None = None) -> list[dict]:
    """The affected fixtures (path, asset, as_of, before, after, report)."""
    os.environ[DEDUPE_ENV] = "1"  # the scan always dedupes, whatever the shell says
    rows: list[dict] = []
    for path in list_fixtures(regime=regime, asset=asset):
        fx = load_fixture(path)
        if not fx.hygiene:
            continue
        with open(path, encoding="utf-8") as fh:
            before = len(json.load(fh)["quotes"])
        rows.append({
            "path": path, "asset": fx.asset, "as_of": fx.as_of.isoformat(),
            "before": before, "after": len(fx.chain.quotes), "report": fx.hygiene,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--regime", default=None)
    ap.add_argument("--asset", default=None)
    args = ap.parse_args()
    total = len(list_fixtures(regime=args.regime, asset=args.asset))
    rows = scan(args.regime, args.asset)
    dropped = 0
    for r in rows:
        parts = [
            f"{iso}: {e['nDuplicateKeys']} dup keys, -{e['nDropped']} ({e['keptRank']}"
            f"{', ' + str(e['nOneSided']) + ' one-sided' if e['nOneSided'] else ''}"
            f"{', ' + str(e.get('nMonotone', 0)) + ' off-series strikes' if e.get('nMonotone') else ''})"
            for iso, e in sorted(r["report"].items())
        ]
        print(f"{r['asset']:6} {r['as_of']}  {r['before']:4d} -> {r['after']:4d}  | " + "; ".join(parts))
        dropped += r["before"] - r["after"]
    by_asset: dict[str, int] = {}
    for r in rows:
        by_asset[r["asset"]] = by_asset.get(r["asset"], 0) + 1
    print(
        f"\n{len(rows)} of {total} fixtures carry duplicate contracts "
        f"({', '.join(f'{a} {n}' for a, n in sorted(by_asset.items())) or 'none'}); "
        f"{dropped} quotes dropped at replay."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

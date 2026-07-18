"""Side-by-side ablation comparison across benchmark sweep tags (R3 item 14).

The learned-beta / OT ablations are adjudicated by the pack: run each variant
under its own ``--tag`` over the SAME evaluation window (``--pair-start``),
then compare here. Rows are intersected on their natural key first — a
variant that skipped a day or node must not win by scoring an easier set —
and every aggregate is reported per (regime, design, R) next to the first
tag (the baseline), with the skill delta the decision reads.

Run::

    python -m backtest.benchmark_compare --tags _b14_base,_b14_learned,_b14_ot
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from backtest.benchmark_pack import RESULTS_DIR, load_parts, summarize_by

_KEY = ("regime", "as_of", "design", "ssr", "ticker", "expiry")


def _keyed(rows: list[dict]) -> dict[tuple, dict]:
    return {tuple(r.get(k) for k in _KEY): r for r in rows}


def compare(tags: list[str]) -> dict:
    """Intersect the tags' scored sets, aggregate each, attach baseline deltas."""
    by_tag = {}
    for tag in tags:
        rows = load_parts(tag=tag)
        if not rows:
            raise SystemExit(f"no part files for tag '{tag}'")
        by_tag[tag] = _keyed(rows)
    shared = set.intersection(*(set(m) for m in by_tag.values()))
    if not shared:
        raise SystemExit("the tags share no scored (regime, day, design, R, node) rows")

    base_tag = tags[0]
    out: dict = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tags": tags,
        "baseline": base_tag,
        "nShared": len(shared),
        "nDropped": {t: len(m) - len(shared) for t, m in by_tag.items()},
        "byGroup": [],
    }
    summaries = {
        t: {
            tuple(rec[k] for k in ("regime", "design", "ssr")): rec
            for rec in summarize_by(
                [m[k] for k in shared], ("regime", "design", "ssr")
            )
        }
        for t, m in by_tag.items()
    }
    for group in sorted(summaries[base_tag]):
        entry: dict = dict(zip(("regime", "design", "ssr"), group))
        for t in tags:
            rec = summaries[t].get(group, {})
            cell = {
                "atm_skill": rec.get("atm_skill"),
                "atm_graph_rms": rec.get("atm_graph_rms"),
                "zeta_mean": rec.get("zeta_mean"),
                "zeta_std": rec.get("zeta_std"),
                "n": rec.get("n"),
            }
            if t != base_tag:
                b = summaries[base_tag].get(group, {})
                if cell["atm_skill"] is not None and b.get("atm_skill") is not None:
                    cell["skill_delta"] = round(cell["atm_skill"] - b["atm_skill"], 3)
            entry[t] = cell
        out["byGroup"].append(entry)
    return out


def _print(result: dict) -> None:
    tags = result["tags"]
    print(f"shared scored rows: {result['nShared']} "
          f"(dropped per tag: {result['nDropped']})")
    head = f"{'regime':<16}{'design':<14}{'R':>2}"
    for t in tags:
        head += f"{t + ' skill':>20}{'ζ std':>8}"
    print(head)
    for e in result["byGroup"]:
        line = f"{e['regime']:<16}{e['design']:<14}{e['ssr']:>2}"
        for t in tags:
            c = e[t]
            skill = c.get("atm_skill")
            delta = c.get("skill_delta")
            s = "—" if skill is None else f"{skill:+g}"
            if delta is not None:
                s += f" ({delta:+g})"
            z = c.get("zeta_std")
            line += f"{s:>20}{('—' if z is None else f'{z:g}'):>8}"
        print(line)
    print("\nskill = baseline-prior RMS − graph RMS (ATM bp, positive = graph wins);"
          "\n(±x) = skill delta vs the first tag; adjudicate on the delta + ζ honesty.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare benchmark ablation sweeps by tag.")
    ap.add_argument("--tags", required=True,
                    help="comma-separated sweep tags; FIRST is the baseline")
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "ablation_compare.json"))
    args = ap.parse_args()
    # The verdict table prints ζ / — / − (U+03B6, U+2014, U+2212); a legacy
    # Windows console is cp1252 and would UnicodeEncodeError on them AFTER the
    # multi-hour sweep. Force UTF-8 so the final step never crashes on display.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass  # redirected/older stream without reconfigure — best effort
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if len(tags) < 2:
        raise SystemExit("need at least two tags to compare")
    result = compare(tags)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    _print(result)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

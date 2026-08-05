# Frozen data for the LQD paper

`lqd_paper_snapshot_20260804_0208.json` — the single data artifact behind every
real-market figure in the paper. Produced by `../scripts/fetch_snapshot.py`
(in-process driver, no server) on 2026-08-04 02:08 UTC.

## Provenance

- **Source**: Massive REST feed (delayed tier), after-hours book of the
  Monday 2026-08-03 US session. Reference date 2026-08-03.
- **Universe**: SPY (spot 757.67) and NVDA (spot 206.80), 8 expiries each,
  maturities 1 day to 1.37 years (2026-08-05 .. 2027-12-17).
- **Fit recipe** (stamped in the manifest `fitSettings`): model LQD,
  Legendre order nOrder=16 (per-slice quote-count guard applies), logistic
  optimization chart, fit mode **haircut** with 0.005 (0.5 vol pt) band
  shrink, weightScheme equal, regLambda 1e-6 / regPower 1.0, calendar
  coupling on (symmetric surface solver). Local-vol and wing projection OFF —
  the exported curves are the raw fitted LQD slices.
- **Quality**: 16/16 lit nodes fitted and ready, zero per-node issues,
  median rms 5.9 vol bp, worst 24.6 vol bp (NVDA 2026-08-05, the 1-day node).
- **Embedded inputs**: full normalized chains, per-node prepared quotes with
  forward provenance, market settings — the file is self-contained for
  offline recalibration (`includesInputs: true`).

## Known family-level advisory (deliberate, documented)

The publish exit gate reported `SPY: wing projection introduced a calendar
crossing (1840.6bp)`, so this artifact was exported with `require_clean=False`.
Forensics (2026-08-03): the gap is the *vol-space* order audit at equal
log-moneyness, and its argmax sits at **k = +0.981 between the 1-day and
3-day SPY expiries**, whose common quote span is only [-0.028, +0.016]. Both
call prices there are ~1e-20 of forward: the "crossing" lives entirely in the
economically empty extrapolated wing (the documented empty-envelope
phenomenon), not in any quoted region. A price-space check across all
adjacent pairs on the full display grid finds no violation above 1e-6 of
forward. Per-node quality is clean; the paper's calendar section uses this
very case as a live illustration of why calendar enforcement is confined to
the common quote support.

## Reproducing

```powershell
. .\restart.local.ps1     # provides VOLFIT_MASSIVE_KEY
.venv\Scripts\python.exe Papers\lqd_paper\scripts\fetch_snapshot.py
```

A rerun fetches the then-current book — it will NOT reproduce this file
byte-for-byte. This JSON is the frozen reference; regenerating figures must
read it, never refetch.

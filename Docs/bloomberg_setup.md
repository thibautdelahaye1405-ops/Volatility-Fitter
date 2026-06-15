# Bloomberg data source — setup & troubleshooting

Short operator note for getting the Bloomberg (`xbbg`) source live and reading
the Data Source light. For the full help-desk write-up of the current
entitlement gate, see
[`bloomberg_workflow_review_account.md`](bloomberg_workflow_review_account.md).

## Prerequisites

- A **running, logged-in Bloomberg Terminal** on the same machine (Desktop API
  / DAPI, `localhost:8194`).
- Python packages in the venv: `xbbg` (the pyo3 1.3.0 engine) and `blpapi`
  (3.26.x). Both are already installed; `pip install xbbg blpapi` if not.

## Running with Bloomberg

```powershell
.\restart.ps1 -Bloomberg     # force Bloomberg active on launch
.\restart.ps1                # auto-pick best reachable (Bloomberg > Yahoo > Massive > Synthetic)
```

All sources are always registered; the in-app **Data Source** selector (TopBar)
switches between them at runtime and shows a status light each. `restart.ps1`
captures the backend to `backend/data/serve.{out,err}.log` and waits for `:8000`
to bind, so a startup failure is visible rather than a vanishing window.

## Reading the Data Source light

`feed_status()` reports one of three states (`volfit/data/bloomberg.py`):

| Light | Meaning |
|---|---|
| **green** "real-time (Terminal)" | a `PX_LAST` came back — data is flowing |
| **red** "no Terminal" | no blpapi session (Terminal closed / not logged in / xbbg missing) |
| **red** "&lt;reason&gt;" | session connected but Bloomberg **refused** the request — the real `responseError` reason, e.g. `workflow review needed`, `not entitled`, `daily request limit reached` |

The third case is the important one: **the Terminal is fine; the account is
gated.** No code change clears it — it's resolved on the Bloomberg side.

## One-line probe (does the Terminal answer?)

```powershell
.venv\Scripts\python -c "from xbbg import blp; print(blp.bdp('SPY US Equity','PX_LAST'))"
```

- Prints a price → entitlements are good; the app will show Bloomberg green.
- Raises `responseError ... subcategory=WORKFLOW_REVIEW_NEEDED` (or similar)
  → connected but gated; take the
  [help-desk account](bloomberg_workflow_review_account.md) to Bloomberg.
- Raises a connection/session error → Terminal not running or not logged in.

## Notes

- The pyo3 `xbbg` logs each *failed* request at WARN to stderr; the provider
  calls `xbbg.set_log_level('error')` (`quiet_xbbg_logs`) on first use to keep
  the console clean — a failed probe is reported via the status light, not spam.
- Dividends: on a Bloomberg-active launch, `serve.py` best-effort imports each
  watchlist ticker's `DVD_HIST_ALL` schedule into its market settings (discrete
  cash dividends for the forward / de-Americanization model).
- Symbol search uses the `//blp/instruments` service (free-text → securities),
  falling back to a substring/echo search if that service is unavailable.

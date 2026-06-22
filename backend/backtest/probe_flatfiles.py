"""Phase 0 gate — probe the Massive/Polygon flat-file bucket for the NBBO quotes
product, its column layout, and its history reach.

This decides the whole backtest data design (the ROADMAP "governing constraint"):
whether the configured flat-file S3 credentials are entitled to the *quotes*
product (real bid/ask) as opposed to only the trade aggregates the live app uses
today (``minute_aggs_v1`` / ``day_aggs_v1`` -> zero-spread close).

Run with the flat-file creds in the environment (dot-source restart.local.ps1):

    . .\\restart.local.ps1
    .\\.venv\\Scripts\\python.exe backend\\backtest\\probe_flatfiles.py

It does ONLY cheap, early-stopping head reads (``LIMIT`` with no WHERE filter), so
it never downloads a whole multi-GB quotes day-file. It reports, per product per
probe day: OK + the column list, or the failure reason (403 entitlement vs 404
missing). Nothing is written.
"""

from __future__ import annotations

import os
from datetime import date

#: S3-compatible layout (mirrors volfit.data.flatfiles).
BUCKET = os.environ.get("VOLFIT_FLATFILES_BUCKET", "flatfiles")
PREFIX = os.environ.get("VOLFIT_FLATFILES_PREFIX", "us_options_opra")
ENDPOINT = os.environ.get("VOLFIT_FLATFILES_ENDPOINT", "files.massive.com")

#: Candidate product names. The trade aggregates are known-good (the live app
#: reads them); the quotes products are what we are gating on. Polygon has used
#: both ``quotes_v1`` and a bare ``quotes`` over time, so probe both.
PRODUCTS = ["quotes_v1", "quotes", "minute_aggs_v1", "day_aggs_v1"]

#: One trading day per regime window we care about (plus a recent day to test the
#: entitlement independent of history depth).
PROBE_DAYS = {
    "recent": date(2026, 6, 18),
    "spike_aug2024": date(2024, 8, 5),
    "high_oct2022": date(2022, 10, 13),
    "low_jul2023": date(2023, 7, 26),
}


def _connect():
    """A DuckDB connection wired to the flat-file bucket (mirrors flatfiles._connect)."""
    import duckdb

    key = os.environ.get("VOLFIT_FLATFILES_KEY", "")
    secret = os.environ.get("VOLFIT_FLATFILES_SECRET", "")
    if not (key and secret):
        raise SystemExit(
            "VOLFIT_FLATFILES_KEY/_SECRET not set — dot-source restart.local.ps1 first."
        )
    host = ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-east-1';")
    con.execute("SET s3_url_style='path';")
    con.execute("SET s3_use_ssl=true;")
    con.execute("SET s3_endpoint=?;", [host])
    con.execute("SET s3_access_key_id=?;", [key])
    con.execute("SET s3_secret_access_key=?;", [secret])
    return con


def _uri(product: str, d: date) -> str:
    return f"s3://{BUCKET}/{PREFIX}/{product}/{d:%Y}/{d:%m}/{d:%Y-%m-%d}.csv.gz"


def _classify(err: str) -> str:
    """Turn an S3/duckdb error into a short reason (entitlement vs missing)."""
    low = err.lower()
    if "403" in low or "access denied" in low or "forbidden" in low:
        return "403 NOT ENTITLED"
    if "404" in low or "not found" in low or "no files found" in low or "nosuchkey" in low:
        return "404 MISSING"
    return err[:140].replace("\n", " ")


def main() -> int:
    con = _connect()
    print(f"endpoint={ENDPOINT} bucket={BUCKET} prefix={PREFIX}\n")
    for product in PRODUCTS:
        print(f"== {product} ==")
        for label, d in PROBE_DAYS.items():
            uri = _uri(product, d)
            try:
                df = con.execute(
                    "SELECT * FROM read_csv_auto(?, sample_size=1000) LIMIT 3", [uri]
                ).df()
                print(f"  {label:14s} {d}  OK  cols={list(df.columns)}")
            except Exception as exc:  # noqa: BLE001 - probe must report every failure
                print(f"  {label:14s} {d}  {_classify(str(exc))}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

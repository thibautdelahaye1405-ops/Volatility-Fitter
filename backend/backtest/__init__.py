"""Offline backtest harness for the Vol-Fitter (runs outside the FastAPI app).

A two-phase design (see ROADMAP / the backtest plan):

  * capture phase  — slow, network/quota-bound, run once, writes immutable
    per-(asset, date, time) NBBO chain fixtures from the Massive/Polygon flat
    files (the ``quotes_v1`` product = real bid/ask, multi-year reach);
  * compute phase  — fully offline, deterministic, re-runnable for every model
    x hyperparameter set, replaying fixtures through a ``StaticProvider``.

This package is purely additive: it imports the production ``volfit`` engine but
changes none of it.
"""

"""Explicit previous-close prior seeding (the ``POST /workflow/seed-priors``
verb), split out of volfit.api.workflow — re-exported there as
``workflow.seed_priors`` so the router and every test seam keep their name.

For each lit node without a saved prior: switch the as-of to the previous
close of the TICKER's own source (a pinned name seeds off its feed —
volfit.api.state_sources), fetch + calibrate that chain, save the LQD fit as
the node's prior, then restore the live as-of.
"""

from __future__ import annotations

from volfit.api import service
from volfit.api.state import AppState
from volfit.api.workflow_stages import lit_nodes


def seed_priors(state: AppState, tickers: list[str] | None = None, fit_mode: str = "mid") -> int:
    """Seed previous-close priors for the lit nodes lacking a saved one.

    Returns the number of priors seeded. Skips nodes that already have a saved
    prior and tickers whose source has no previous-close history.
    """
    from volfit.api.state import AsOfSelection, PriorRecord

    chosen = tickers if tickers is not None else state.active_tickers()
    seeded = 0
    live = state.as_of
    try:
        for ticker in chosen:
            if "prev_close" not in state.provider_for(ticker).historical_modes():
                continue  # this ticker's source has no previous close to seed from
            nodes = [
                (t, iso) for t, iso in lit_nodes(state, [ticker])
                if state.get_prior((t, iso)) is None
            ]
            if not nodes:
                continue
            state.set_as_of(AsOfSelection(mode="prev_close"))
            for t, iso in nodes:
                try:
                    record = service._compute_fit(state, t, iso, fit_mode)
                except Exception:  # noqa: BLE001 — an unfittable node is skipped, never fatal
                    continue
                prior = PriorRecord(
                    curve=service.model_curve(record),
                    params=record.result.params,
                    t=record.prepared.t,
                )
                state.save_prior((t, iso), prior)
                seeded += 1
            state.set_as_of(live)  # restore between tickers (set_as_of clears caches)
    finally:
        state.set_as_of(live)
    return seeded

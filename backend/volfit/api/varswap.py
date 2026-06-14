"""Variance-swap quote service functions: apply / undo / redo on a node.

Thin orchestration over volfit.api.varswap_session (the pure var-swap edit
machine) and volfit.api.service (fitting + payload assembly), mirroring
volfit.api.edits for option quotes. Every function returns the *refreshed*
SmileData: a successful var-swap edit bumps the var-swap session version, so
the smile_payload call refits the slice through the normal fit cache (the
var-swap penalty is now in the objective) — the same "instant refit" model.

Var-swap quotes are node-level and model-independent, so these endpoints serve
both the Parametric and Local-Vol workspaces; the Local-Vol surface fit reads
the same session through its own cache (volfit.api.affine_fit).
"""

from __future__ import annotations

from volfit.api import service
from volfit.api.schemas import SmileData, VarSwapEditRequest
from volfit.api.state import AppState


def apply_varswap_edit(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str, edit: VarSwapEditRequest
) -> SmileData:
    """Apply one set/exclude/include/remove/reset action, then refit and respond.

    Raises UnknownNodeError for a bad node (router -> 404) and ValueError for a
    bad edit — missing/non-positive level, or excluding/including a non-existent
    quote (router -> 422); the session is untouched on failure.
    """
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    session = state.varswap_session((ticker, iso))
    session.apply(edit.action, edit.level)
    return service.smile_payload(state, ticker, iso, fit_mode)


def undo_varswap(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Pop the last var-swap edit; empty stack just returns the current payload."""
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    session = state.varswap_session_if_exists((ticker, iso))
    if session is not None:
        session.undo()
    return service.smile_payload(state, ticker, iso, fit_mode)


def redo_varswap(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Restore the last undone var-swap edit; empty stack is a no-op."""
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    session = state.varswap_session_if_exists((ticker, iso))
    if session is not None:
        session.redo()
    return service.smile_payload(state, ticker, iso, fit_mode)

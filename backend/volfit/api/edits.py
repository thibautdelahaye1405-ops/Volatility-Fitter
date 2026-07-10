"""Quote-edit service functions: apply / undo / redo on a smile node.

Thin orchestration over volfit.api.session (the pure edit-state machine) and
volfit.api.service (fitting + payload assembly). Every function returns the
*refreshed* SmileData: a successful edit bumps the session version, so the
smile_payload call refits the slice through the normal fit cache — that is
the "instant refit" of the Phase 5 fit-session model. Kept separate from
service.py only for the <= 400 lines per file policy (imports are
one-directional: edits -> service).
"""

from __future__ import annotations

from volfit.api import service
from volfit.api.schemas import QuoteEditRequest, SmileData
from volfit.api.state import AppState


def apply_quote_edit(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str, edit: QuoteEditRequest
) -> SmileData:
    """Apply one exclude/include/amend/reset action, then refit and respond.

    Raises UnknownNodeError for a bad node (router -> 404) and ValueError for
    a bad edit — out-of-range index, missing mid, or the minimum-included-
    quotes guard (router -> 422); the session is untouched on failure.
    """
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    # The baseline fit also pins n_quotes (prepared arrays are deterministic
    # per node, so the index space is stable for the whole session). Before any
    # calibration (gated workflow) the index space comes from the prepared quotes
    # directly, so quotes can be edited pre-Calibrate too.
    record = service.fit_or_get(state, ticker, iso, fit_mode)
    prepared = record.prepared if record is not None else service.prepare_slice(state, ticker, iso)
    if prepared is None:
        raise ValueError("fetch quotes before editing this node")
    session = state.session((ticker, iso))
    session.apply(edit.action, edit.index, edit.mid, n_quotes=int(prepared.k.size))
    # Governance kernel (R1 item 8): quote interventions are audited — action,
    # strike coordinate and (for amends) the new mid IV, after validation so
    # only edits that actually landed are recorded.
    k = float(prepared.k[edit.index]) if edit.index is not None else None
    state.log_event(
        "quote_edit", scope=f"{ticker}/{iso}",
        payload={"action": edit.action, "index": edit.index, "k": k, "mid": edit.mid},
    )
    return service.smile_payload(state, ticker, iso, fit_mode)


def undo_edit(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Pop the last edit; on an empty stack just return the current payload."""
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    session = state.session_if_exists((ticker, iso))
    if session is not None:
        session.undo()
    return service.smile_payload(state, ticker, iso, fit_mode)


def redo_edit(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Restore the last undone edit; empty stack is a no-op, never an error."""
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    session = state.session_if_exists((ticker, iso))
    if session is not None:
        session.redo()
    return service.smile_payload(state, ticker, iso, fit_mode)

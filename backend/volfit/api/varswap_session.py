"""Per-(ticker, expiry) variance-swap quote sessions.

A node has at most ONE var-swap quote (the var-swap level is a single scalar
per smile), so this is the var-swap analogue of volfit.api.session.EditSession
but over a single value instead of a quote map. It records the user's add /
adjust / exclude decisions and supports bounded undo/redo and reset, with a
``version`` appended to the fit-cache key so an edit refits the node without any
explicit cache eviction.

Var-swap quotes are model-independent (a market fact about the node), so the
*same* session is shared by the Parametric (LQD/SVI/sigmoid) and Local-Vol
(affine surface) fits — exactly like the option-quote edit session. The undo/
redo history is kept SEPARATE from the option-quote session, so resetting the
var-swap does not touch the user's excluded/amended option quotes.

Pure logic — no FastAPI imports. ``apply`` raises ValueError (no mutation) on
bad input; the router maps that to HTTP 422.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Undo history bound (snapshots are tiny; 100 steps is plenty).
MAX_UNDO_DEPTH = 100

#: Actions accepted by VarSwapSession.apply (mirrors schemas.VarSwapEditRequest).
#: - "set"     add or adjust the quote level (requires a positive ``level``);
#: - "exclude" keep the level but drop it from calibration;
#: - "include" re-activate an excluded quote;
#: - "remove"  delete the quote entirely (back to no var-swap);
#: - "reset"   alias of remove plus a clean slate (still undoable).
ACTIONS = ("set", "exclude", "include", "remove", "reset")


@dataclass(frozen=True)
class VarSwapState:
    """Net var-swap quote state of one node.

    ``level`` is the quoted var-swap *volatility* (e.g. 0.18), None when no
    quote exists; ``excluded`` keeps a level on record but out of the fit.
    """

    level: float | None = None
    excluded: bool = False

    @property
    def is_active(self) -> bool:
        """True when a quote should enter the calibration penalty."""
        return self.level is not None and not self.excluded


class VarSwapSession:
    """Single var-swap quote + undo/redo stacks for one smile node."""

    def __init__(self) -> None:
        self.state = VarSwapState()
        self.version: int = 0  # bumped on every change; part of fit-cache keys
        self._undo: list[VarSwapState] = []
        self._redo: list[VarSwapState] = []

    # ------------------------------------------------------------- read side
    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    # ------------------------------------------------------------------ edits
    def apply(self, action: str, level: float | None) -> None:
        """Apply one var-swap action; raise ValueError (no mutation) on bad input."""
        if action not in ACTIONS:
            raise ValueError(f"unknown var-swap action {action!r}")
        if action in ("set",):
            if level is None or not level > 0.0:
                raise ValueError("'set' requires a positive var-swap vol")
            nxt = replace(self.state, level=float(level), excluded=False)
        elif action == "exclude":
            if self.state.level is None:
                raise ValueError("no var-swap quote to exclude")
            nxt = replace(self.state, excluded=True)
        elif action == "include":
            if self.state.level is None:
                raise ValueError("no var-swap quote to include")
            nxt = replace(self.state, excluded=False)
        else:  # remove / reset
            nxt = VarSwapState()
        self._commit(nxt)

    def _commit(self, nxt: VarSwapState) -> None:
        """Push the current state for undo, clear redo, install the new state."""
        self._undo.append(self.state)
        if len(self._undo) > MAX_UNDO_DEPTH:
            self._undo.pop(0)
        self._redo.clear()
        self.state = nxt
        self.version += 1

    # -------------------------------------------------------------- undo/redo
    def undo(self) -> bool:
        """Restore the previous state; False (no change) on empty stack."""
        if not self._undo:
            return False
        self._redo.append(self.state)
        self.state = self._undo.pop()
        self.version += 1
        return True

    def redo(self) -> bool:
        """Re-apply the last undone state; False on empty stack."""
        if not self._redo:
            return False
        self._undo.append(self.state)
        self.state = self._redo.pop()
        self.version += 1
        return True

    # ---------------------------------------------------------- serialization
    def to_doc(self, history: bool = True) -> dict:
        """JSON-safe dump (workspace serialization / publish manifests).

        With ``history`` False only the net quote state + version is captured
        — exactly what reproducing a fit needs (publish manifests use this)."""
        doc = {"version": self.version, "state": _vs_doc(self.state)}
        if history:
            doc["undo"] = [_vs_doc(s) for s in self._undo]
            doc["redo"] = [_vs_doc(s) for s in self._redo]
        return doc

    def load_doc(self, doc: dict) -> None:
        """Replace the session's content from a ``to_doc`` dump."""
        self.state = _vs_from_doc(doc.get("state", {}))
        self.version = int(doc.get("version", 0))
        self._undo = [_vs_from_doc(s) for s in doc.get("undo", [])]
        self._redo = [_vs_from_doc(s) for s in doc.get("redo", [])]


def _vs_doc(s: VarSwapState) -> dict:
    return {"level": s.level, "excluded": s.excluded}


def _vs_from_doc(d: dict) -> VarSwapState:
    return VarSwapState(
        level=None if d.get("level") is None else float(d["level"]),
        excluded=bool(d.get("excluded", False)),
    )

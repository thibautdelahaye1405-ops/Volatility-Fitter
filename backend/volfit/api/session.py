"""Per-(ticker, expiry) quote-edit sessions (ROADMAP Phase 5 fit sessions).

A session records the user's exclude / include / amend decisions against the
*prepared* quote array of one smile node (volfit.api.quotes), keyed by the
quote's stable position `index`. Edits change the calibration inputs only —
fit mode keeps choosing the weights — so one session is shared across all
fit modes of the node.

Undo/redo is snapshot-based: every successful `apply` pushes the previous
edit map onto a bounded undo stack and clears the redo stack ("reset" is
itself just another undoable edit). `version` increments on every change and
is appended to the fit-cache key, so an edit invalidates cached fits without
any explicit cache eviction.

Pure logic — no FastAPI imports. `apply` raises ValueError with a human
message on bad input (the edits router maps that to HTTP 422) and leaves the
session untouched on failure. Sessions are mutated from request worker
threads without an internal lock: concurrent edits to the *same* node are a
single-user UI non-goal, and AppState only locks the session registry.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A fit needs at least this many included quotes (LQD has 7 parameters but
#: 5 well-placed quotes still pin level/skew/curvature; fewer is meaningless).
MIN_INCLUDED_QUOTES = 5

#: Undo history bound: snapshots are tiny dicts, 100 steps is plenty.
MAX_UNDO_DEPTH = 100

#: Actions accepted by EditSession.apply (mirrors schemas.QuoteEditRequest).
ACTIONS = ("exclude", "include", "amend", "reset")


@dataclass(frozen=True)
class QuoteEdit:
    """Net edit state of one quote: excluded and/or mid-IV overridden."""

    excluded: bool = False
    amended_iv: float | None = None  # replacement mid implied vol, e.g. 0.21

    @property
    def is_default(self) -> bool:
        """True when the edit carries no information and can be dropped."""
        return not self.excluded and self.amended_iv is None


class EditSession:
    """Edit map + undo/redo stacks for one (ticker, expiry) smile node."""

    def __init__(self) -> None:
        self.edits: dict[int, QuoteEdit] = {}
        self.version: int = 0  # bumped on every change; part of fit-cache keys
        self._undo: list[dict[int, QuoteEdit]] = []
        self._redo: list[dict[int, QuoteEdit]] = []

    # ------------------------------------------------------------- read side
    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    # ------------------------------------------------------------------ edits
    def apply(self, action: str, index: int | None, mid: float | None, n_quotes: int) -> None:
        """Apply one edit action; raise ValueError (no mutation) on bad input.

        ``n_quotes`` is the length of the node's prepared quote array, used to
        validate ``index`` and to enforce the minimum-included-quotes guard.
        """
        next_edits = {} if action == "reset" else self._edited(action, index, mid, n_quotes)
        included = n_quotes - sum(1 for e in next_edits.values() if e.excluded)
        if included < MIN_INCLUDED_QUOTES:
            raise ValueError("too few quotes to fit")
        self._commit(next_edits)

    def _edited(
        self, action: str, index: int | None, mid: float | None, n_quotes: int
    ) -> dict[int, QuoteEdit]:
        """The would-be edit map after one non-reset action (validates input)."""
        if action not in ACTIONS:
            raise ValueError(f"unknown edit action {action!r}")
        if index is None:
            raise ValueError(f"{action!r} requires a quote index")
        if not 0 <= index < n_quotes:
            raise ValueError(f"quote index {index} out of range [0, {n_quotes})")
        current = self.edits.get(index, QuoteEdit())
        if action == "exclude":
            edit = QuoteEdit(excluded=True, amended_iv=current.amended_iv)
        elif action == "include":
            edit = QuoteEdit(excluded=False, amended_iv=current.amended_iv)
        else:  # amend: replace the mid implied vol, keep the exclusion flag
            if mid is None or not mid > 0.0:
                raise ValueError("'amend' requires a positive mid implied vol")
            edit = QuoteEdit(excluded=current.excluded, amended_iv=float(mid))
        next_edits = dict(self.edits)
        if edit.is_default:
            next_edits.pop(index, None)  # back to pristine: drop the entry
        else:
            next_edits[index] = edit
        return next_edits

    def _commit(self, next_edits: dict[int, QuoteEdit]) -> None:
        """Push the current map for undo, clear redo, install the new map."""
        self._undo.append(dict(self.edits))
        if len(self._undo) > MAX_UNDO_DEPTH:
            self._undo.pop(0)
        self._redo.clear()
        self.edits = next_edits
        self.version += 1

    # -------------------------------------------------------------- undo/redo
    def undo(self) -> bool:
        """Restore the previous edit map; False (no change) on empty stack."""
        if not self._undo:
            return False
        self._redo.append(dict(self.edits))
        self.edits = self._undo.pop()
        self.version += 1
        return True

    def redo(self) -> bool:
        """Re-apply the last undone edit map; False on empty stack."""
        if not self._redo:
            return False
        self._undo.append(dict(self.edits))
        self.edits = self._redo.pop()
        self.version += 1
        return True

    # ---------------------------------------------------------- serialization
    def to_doc(self, history: bool = True) -> dict:
        """JSON-safe dump (workspace serialization / publish manifests).

        With ``history`` False only the net edit map + version is captured —
        exactly what reproducing a fit needs (publish manifests use this)."""
        doc = {"version": self.version, "edits": _edits_doc(self.edits)}
        if history:
            doc["undo"] = [_edits_doc(m) for m in self._undo]
            doc["redo"] = [_edits_doc(m) for m in self._redo]
        return doc

    def load_doc(self, doc: dict) -> None:
        """Replace the session's content from a ``to_doc`` dump."""
        self.edits = _edits_from_doc(doc.get("edits", {}))
        self.version = int(doc.get("version", 0))
        self._undo = [_edits_from_doc(m) for m in doc.get("undo", [])]
        self._redo = [_edits_from_doc(m) for m in doc.get("redo", [])]


def _edits_doc(edits: dict[int, QuoteEdit]) -> dict:
    """JSON keys are strings, so quote indices serialize as str(index)."""
    return {
        str(i): {"excluded": e.excluded, "amendedIv": e.amended_iv}
        for i, e in sorted(edits.items())
    }


def _edits_from_doc(doc: dict) -> dict[int, QuoteEdit]:
    return {
        int(i): QuoteEdit(
            excluded=bool(d.get("excluded", False)),
            amended_iv=None if d.get("amendedIv") is None else float(d["amendedIv"]),
        )
        for i, d in doc.items()
    }

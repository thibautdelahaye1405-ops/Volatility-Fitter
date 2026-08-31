"""In-app Help Center — documentation catalog + safe file resolution.

The Help Center's "Documentation" page lists the repository's human-readable
documents (Markdown editions of the technical notes, the handoff pack, the
compiled note PDFs, the book and the LQD paper) and serves them inline. This
module owns three things:

* **Root discovery** — where ``Docs/`` and ``Papers/`` live. Source checkout:
  three parents up from this file (like ``volfit/api/frontend.py``). Override
  with ``VOLFIT_DOCS_ROOT`` (a directory containing ``Docs/`` and/or
  ``Papers/``). Frozen ``.exe`` (``sys._MEIPASS``): ``<MEIPASS>/docs_root``.
  When nothing exists the catalog simply reports ``available=False`` — the
  desktop bundle ships without Docs and that is NOT an error.
* **The catalog** — a non-recursive scan of each allow-listed root for ``*.md``
  and ``*.pdf`` (skipping ``_``-prefixed files and the internal
  ``ROADMAP.md`` / ``NOTATION.md``), with a title read from the first ``# ``
  heading of a Markdown file.
* **Safe file resolution** — the only path from a URL to a file on disk. The
  root key must be allow-listed, the name must be a plain ``.md``/``.pdf``
  file name (no separators, no ``..``), and the resolved path must stay inside
  the root directory. Anything else is a 400/404, never a read.

The small pydantic response models live here (not in ``schemas*.py``) because
they are local to this feature.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

#: Allow-listed documentation roots: URL key -> path relative to the docs root.
#: ``notes-pdf`` is Docs/notes itself: the 35 compiled note PDFs (primaries,
#: supplements and lecture rewrites) sit beside their .tex sources there.
DOC_ROOTS: dict[str, str] = {
    "notes-md": "Docs/handoff/notes",
    "handoff": "Docs/handoff",
    "docs": "Docs",
    "notes-pdf": "Docs/notes",
    "book": "Papers/book",
    "paper": "Papers/lqd_paper",
}

#: Suffixes each root serves: the Markdown roots list only ``.md`` (Docs/ and
#: Docs/handoff hold planning .md next to the docs), the PDF roots only
#: ``.pdf`` (Docs/notes carries .md guides for the LaTeX series that are
#: not documentation).
ROOT_SUFFIXES: dict[str, frozenset[str]] = {
    "notes-md": frozenset({".md"}),
    "handoff": frozenset({".md"}),
    "docs": frozenset({".md"}),
    "notes-pdf": frozenset({".pdf"}),
    "book": frozenset({".pdf"}),
    "paper": frozenset({".pdf"}),
}

#: Markdown roots searched (in order) when a document is requested by stem.
MARKDOWN_LOOKUP_ORDER: tuple[str, ...] = ("notes-md", "handoff", "docs")

#: File names never listed nor served (internal planning / notation files).
SKIP_NAMES: frozenset[str] = frozenset({"ROADMAP.md", "NOTATION.md"})

#: Servable suffixes -> catalog ``kind``.
KIND_BY_SUFFIX: dict[str, str] = {".md": "md", ".pdf": "pdf"}

#: Media types served by ``GET /help/files``.
MEDIA_TYPES: dict[str, str] = {
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
}

DOCS_ROOT_ENV = "VOLFIT_DOCS_ROOT"
_TITLE_SCAN_LINES = 60  # how far into a Markdown file we look for the first heading


# -- response models ---------------------------------------------------------


class HelpDocEntry(BaseModel):
    """One catalog row: a servable Markdown or PDF document."""

    id: str
    root: str
    name: str
    kind: Literal["md", "pdf"]
    title: str
    sizeBytes: int


class HelpDocsCatalog(BaseModel):
    """``GET /help/docs`` — ``available=False`` (empty) when no Docs tree exists."""

    available: bool
    root: str | None = None
    entries: list[HelpDocEntry] = Field(default_factory=list)


class HelpDocMarkdown(BaseModel):
    """``GET /help/docs/{doc_id}`` — one Markdown document's text."""

    id: str
    root: str
    name: str
    title: str
    markdown: str


# -- root discovery ----------------------------------------------------------


def _looks_like_docs_root(path: Path) -> bool:
    """A docs root is a directory holding ``Docs/`` and/or ``Papers/``."""
    return path.is_dir() and ((path / "Docs").is_dir() or (path / "Papers").is_dir())


def find_docs_root() -> Path | None:
    """Locate the directory containing ``Docs/`` and ``Papers/`` (or ``None``).

    Order: explicit ``VOLFIT_DOCS_ROOT`` (honoured even when it does not qualify
    — an explicit override never silently falls back to the checkout), then the
    frozen bundle's ``docs_root``, then the source checkout.
    """
    override = os.environ.get(DOCS_ROOT_ENV, "").strip()
    if override:
        candidate = Path(override)
        return candidate if _looks_like_docs_root(candidate) else None

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "docs_root"
        return bundled if _looks_like_docs_root(bundled) else None

    try:
        repo_root = Path(__file__).resolve().parents[3]
    except IndexError:  # unusually shallow install layout
        return None
    return repo_root if _looks_like_docs_root(repo_root) else None


# -- catalog -----------------------------------------------------------------


def _is_servable_name(name: str) -> bool:
    """Catalog/serve filter: allowed suffix, not ``_``-prefixed, not an internal file."""
    if not name or name.startswith("_") or name in SKIP_NAMES:
        return False
    return Path(name).suffix.lower() in KIND_BY_SUFFIX


def _markdown_title(path: Path, fallback: str) -> str:
    """First ``# `` heading of a Markdown file (else ``fallback``)."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for _ in range(_TITLE_SCAN_LINES):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("# "):
                    title = line[2:].strip()
                    if title:
                        return title
    except OSError:
        pass
    return fallback


def _entry_for(root_key: str, path: Path) -> HelpDocEntry:
    kind = KIND_BY_SUFFIX[path.suffix.lower()]
    title = _markdown_title(path, path.stem) if kind == "md" else path.stem
    return HelpDocEntry(
        id=path.stem,
        root=root_key,
        name=path.name,
        kind=kind,  # type: ignore[arg-type]
        title=title,
        sizeBytes=path.stat().st_size,
    )


def list_docs(root_dir: Path | None = None) -> HelpDocsCatalog:
    """Scan the allow-listed roots (non-recursively) into a catalog.

    ``root_dir=None`` runs :func:`find_docs_root`. Roots keep ``DOC_ROOTS``
    order; entries within a root are sorted by file name.
    """
    root = root_dir if root_dir is not None else find_docs_root()
    if root is None:
        return HelpDocsCatalog(available=False)

    entries: list[HelpDocEntry] = []
    for key, rel in DOC_ROOTS.items():
        directory = root / rel
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            if path.is_file() and _is_servable_name(path.name) and path.suffix.lower() in ROOT_SUFFIXES[key]:
                entries.append(_entry_for(key, path))
    return HelpDocsCatalog(available=True, root=str(root), entries=entries)


# -- safe resolution ---------------------------------------------------------


def _validate_name(name: str) -> None:
    """Reject anything that is not a plain, servable file name (400)."""
    bad = (
        not name
        or "/" in name
        or "\\" in name
        or ".." in name
        or "\x00" in name
        or name != Path(name).name
        or not _is_servable_name(name)
    )
    if bad:
        raise HTTPException(status_code=400, detail="invalid document name")


def _root_dir(root_key: str, root_dir: Path | None) -> Path:
    """The allow-listed root directory for ``root_key`` (404 when unavailable)."""
    if root_key not in DOC_ROOTS:
        raise HTTPException(status_code=404, detail="unknown documentation root")
    root = root_dir if root_dir is not None else find_docs_root()
    if root is None:
        raise HTTPException(status_code=404, detail="documentation not available")
    return (root / DOC_ROOTS[root_key]).resolve()


def resolve_file(root_key: str, name: str, root_dir: Path | None = None) -> Path:
    """Map ``(root_key, name)`` to an existing file inside that root, or raise.

    400 for a malformed/unsafe name (separators, ``..``, wrong suffix, escaping
    the root); 404 for an unknown root, an unavailable docs tree, or a missing
    file.
    """
    _validate_name(name)
    base = _root_dir(root_key, root_dir)
    if Path(name).suffix.lower() not in ROOT_SUFFIXES.get(root_key, frozenset()):
        raise HTTPException(status_code=400, detail="that root does not serve this file type")
    target = (base / name).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(status_code=400, detail="invalid document name")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="document not found")
    return target


def media_type_for(path: Path) -> str:
    """Response media type for a resolved document."""
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def read_markdown(doc_id: str, root_dir: Path | None = None) -> HelpDocMarkdown:
    """Read the Markdown document with stem ``doc_id`` (first root wins).

    Roots are searched in :data:`MARKDOWN_LOOKUP_ORDER`. 400 for a malformed id,
    404 when no root holds ``<doc_id>.md`` or the docs tree is unavailable.
    """
    name = f"{doc_id}.md"
    _validate_name(name)
    root = root_dir if root_dir is not None else find_docs_root()
    if root is None:
        raise HTTPException(status_code=404, detail="documentation not available")
    for key in MARKDOWN_LOOKUP_ORDER:
        base = (root / DOC_ROOTS[key]).resolve()
        target = (base / name).resolve()
        if target.is_relative_to(base) and target.is_file():
            text = target.read_text(encoding="utf-8", errors="replace")
            return HelpDocMarkdown(
                id=doc_id,
                root=key,
                name=name,
                title=_markdown_title(target, doc_id),
                markdown=text,
            )
    raise HTTPException(status_code=404, detail="document not found")

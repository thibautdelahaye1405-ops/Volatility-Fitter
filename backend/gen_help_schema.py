"""Regenerate the Help Center's bundled settings schema (HELP CENTER ARC, H1).

Thin CLI over :mod:`volfit.api.help_schema` — the builder itself lives in the
package so ``GET /help/settings-schema`` can serve the live version. Writes
frontend/src/lib/help/settingsSchema.json (the offline fallback the Settings
reference ships with); tests/test_help_schema.py fails when the committed
file drifts from the pydantic models, so a schema change must be followed by:

    cd backend ; ..\\.venv\\Scripts\\python gen_help_schema.py            # rewrite
    cd backend ; ..\\.venv\\Scripts\\python gen_help_schema.py --check    # exit 1 on drift
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from volfit.api.help_schema import build_schema, drift

#: Output path (repo root / frontend / src / lib / help / settingsSchema.json).
OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "help" / "settingsSchema.json"


def main(argv: list[str]) -> int:
    if "--check" in argv:
        problems = drift(OUT)
        for p in problems:
            print(p)
        return 1 if problems else 0
    doc = build_schema()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n = sum(len(m["fields"]) for m in doc["models"].values())
    print(f"wrote {OUT} ({n} fields)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

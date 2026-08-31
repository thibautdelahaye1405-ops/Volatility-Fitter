"""Settings schema for the Help Center (HELP CENTER ARC, H1).

The in-app Settings reference documents every field of the three settings
models — ``FitSettings``, ``OptionsSettings`` (volfit.api.schemas) and
``MarketSettings`` (volfit.api.schemas_market) — with hand-written prose
(frontend/src/lib/help/settingsDocs/*.ts) but with the MACHINE facts (type,
default, range, enum) derived from the pydantic models, never copied by hand.

:func:`build_schema` produces those facts as a JSON-able dict mirroring
``SettingsSchema`` in frontend/src/lib/help/types.ts::

    {generatedAt, models: {fit|options|market: {title, fields: [SchemaField…]}}}

with one ``SchemaField`` per model field — ``name``, a simplified ``type``
label (bool/int/float/str/enum/list/dict/object), the JSON ``default``,
``min``/``max`` (+ ``exclusiveMin``/``exclusiveMax``), ``enum`` choices and
``optional`` (accepts null). Two consumers:

* ``backend/gen_help_schema.py`` writes it to
  frontend/src/lib/help/settingsSchema.json (bundled, offline fallback) and
  ``--check`` / tests/test_help_schema.py fail on drift;
* ``GET /help/settings-schema`` (routers/help.py) serves the LIVE version so
  the reference shows the running server's defaults.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.api.schemas_market import MarketSettings

#: The three settings models, in reference order.
MODELS: dict[str, type[BaseModel]] = {
    "fit": FitSettings,
    "options": OptionsSettings,
    "market": MarketSettings,
}

_TYPE_LABELS = {
    "boolean": "bool",
    "integer": "int",
    "number": "float",
    "string": "str",
    "array": "list",
    "object": "dict",
}


def _resolve(prop: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Follow a ``$ref`` into ``$defs`` (pydantic emits enums / nested models by reference)."""
    if "$ref" in prop:
        name = prop["$ref"].rsplit("/", 1)[-1]
        return defs.get(name, {})
    return prop


def _field(name: str, prop: dict[str, Any], defs: dict[str, Any], fallback_default: Any = None) -> dict[str, Any]:
    """One SchemaField from a JSON-schema property (nullable unions unwrapped).

    ``fallback_default`` covers ``default_factory`` fields, which the JSON schema
    leaves without a ``default`` (e.g. ``dividends: list = Field(default_factory=list)``).
    """
    optional = False
    variants = prop.get("anyOf")
    if variants:
        non_null = [v for v in variants if v.get("type") != "null"]
        optional = len(non_null) < len(variants)
        prop = {**prop, **(_resolve(non_null[0], defs) if non_null else {})}
        prop.pop("anyOf", None)
    prop = {**prop, **_resolve(prop, defs)} if "$ref" in prop else prop
    out: dict[str, Any] = {"name": name}
    if "enum" in prop:
        out["type"] = "enum"
        out["enum"] = [str(v) for v in prop["enum"]]
    elif "const" in prop:
        out["type"] = "enum"
        out["enum"] = [str(prop["const"])]
    else:
        t = prop.get("type")
        out["type"] = _TYPE_LABELS.get(t, "object") if isinstance(t, str) else "object"
    # pydantic puts JSON-encoded defaults on the property itself.
    out["default"] = prop.get("default", fallback_default)
    for src, dst, excl in (
        ("minimum", "min", None),
        ("maximum", "max", None),
        ("exclusiveMinimum", "min", "exclusiveMin"),
        ("exclusiveMaximum", "max", "exclusiveMax"),
    ):
        if src in prop:
            out[dst] = prop[src]
            if excl:
                out[excl] = True
    if optional:
        out["optional"] = True
    return out


def build_schema() -> dict[str, Any]:
    """The full JSON document (deterministic: model field order)."""
    models: dict[str, Any] = {}
    for key, model in MODELS.items():
        js = model.model_json_schema()
        defs = js.get("$defs", {})
        props = js.get("properties", {})
        fields = []
        for n, info in model.model_fields.items():
            if n not in props:
                continue
            fb = info.default_factory() if info.default_factory is not None else None
            fields.append(_field(n, props[n], defs, fb))
        models[key] = {"title": model.__name__, "fields": fields}
    return {"generatedAt": date.today().isoformat(), "models": models}


def _strip_stamp(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "generatedAt"}


def drift(committed_path: Path) -> list[str]:
    """Human-readable differences between a committed JSON file and the live models."""
    live = _strip_stamp(build_schema())
    if not committed_path.is_file():
        return [f"{committed_path} is missing — run gen_help_schema.py"]
    committed = _strip_stamp(json.loads(committed_path.read_text(encoding="utf-8")))
    problems: list[str] = []
    for key in MODELS:
        a = {f["name"]: f for f in committed.get("models", {}).get(key, {}).get("fields", [])}
        b = {f["name"]: f for f in live["models"][key]["fields"]}
        for n in sorted(set(a) | set(b)):
            if n not in a:
                problems.append(f"{key}.{n}: new field (not in JSON)")
            elif n not in b:
                problems.append(f"{key}.{n}: removed field (still in JSON)")
            elif a[n] != b[n]:
                problems.append(f"{key}.{n}: changed {a[n]} -> {b[n]}")
    return problems

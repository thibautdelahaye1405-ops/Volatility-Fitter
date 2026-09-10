"""Lane presets of the series dialog (SERIES ARC S0, §3.1 of the roadmap).

Split from ``schemas_series`` under the 400-line policy. A preset resolves
against the series' frozen base fit settings into a :class:`LaneSpec`: the
LQD presets pin ``nOrder`` (the base's or the requested one), ``current``
mirrors the base's model with an empty patch, the LV presets ride the affine
stage of the lane state. Free = prior off + filter off; + prior = the
``hybrid`` persistence mode (the benchmark-adjudicated default); + filter =
``observationFilterMode`` active on top of it.
"""

from __future__ import annotations

from typing import Any

from volfit.api.schemas import FitSettings
from volfit.api.schemas_series import LaneSpec

_FAMILY_MODEL = {"lqd": "lqd", "svi": "svi", "sigmoid": "sigmoid"}


# ------------------------------------------------------------------- presets

#: The lane presets of the dialog (§3.1), in menu order. ``current`` is the
#: live settings verbatim (family resolved from the base at creation).
LANE_PRESET_IDS: tuple[str, ...] = (
    "lqd_free", "lqd_prior", "lqd_prior_filter", "svi_free", "mcs_free",
    "lv_free", "lv_prior", "current",
)

_FREE = {"priorPersistenceMode": "off", "observationFilterMode": "off"}
_PRIOR = {"priorPersistenceMode": "hybrid", "observationFilterMode": "off"}
_PRIOR_FILTER = {"priorPersistenceMode": "hybrid", "observationFilterMode": "active"}

_PRESETS: dict[str, dict[str, Any]] = {
    "lqd_free": {"family": "lqd", "patchOptions": _FREE, "name": "LQD-{n} free"},
    "lqd_prior": {"family": "lqd", "patchOptions": _PRIOR, "name": "LQD-{n} + prior"},
    "lqd_prior_filter": {
        "family": "lqd", "patchOptions": _PRIOR_FILTER, "name": "LQD-{n} + prior + filter",
    },
    "svi_free": {"family": "svi", "patchOptions": _FREE, "name": "SVI-JW free"},
    "mcs_free": {"family": "sigmoid", "patchOptions": _FREE, "name": "MCS free"},
    "lv_free": {"family": "lv", "patchOptions": {**_FREE, "localVolEnabled": True},
                "name": "LV affine free"},
    "lv_prior": {"family": "lv", "patchOptions": {**_PRIOR, "localVolEnabled": True},
                 "name": "LV affine + prior"},
}


def lane_preset(preset: str, base: FitSettings, n_order: int | None = None,
                lane_id: str | None = None) -> LaneSpec:
    """Resolve a preset against the series' base fit settings: the LQD
    presets pin ``nOrder`` (``n_order`` or the base's), ``current`` mirrors
    the base's model with an empty patch. Raises ``KeyError`` on an unknown
    preset id (the dialog offers ``LANE_PRESET_IDS`` only)."""
    if preset == "current":
        family = base.model if base.model in _FAMILY_MODEL else "lqd"
        return LaneSpec(id=lane_id or preset, name="Current Options", family=family)
    p = _PRESETS[preset]
    n = int(n_order or base.nOrder)
    patch_fit = {"nOrder": n} if p["family"] == "lqd" else {}
    return LaneSpec(
        id=lane_id or preset,
        name=p["name"].format(n=n),
        family=p["family"],
        patchFit=patch_fit,
        patchOptions=dict(p["patchOptions"]),
    )

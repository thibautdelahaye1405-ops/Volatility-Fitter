"""LV operator arc — the persisted-options lift of the time scheme.

A blob saved before ``lvLattice`` existed carries ``timeScheme = "implicit"``
only because that was the sole sane value then; ``settings_persist`` lifts it
to the new BDF2 default so a restored desk gets the second-order march
without a re-save. An explicit Rannacher choice survives, and a blob that
knows ``lvLattice`` (saved under the new dialog) means what it says.
"""

from __future__ import annotations

from volfit.api.schemas import OptionsSettings
from volfit.api.settings_persist import _coerce, _migrate_options


def test_pre_arc_implicit_lifts_to_bdf2():
    assert _migrate_options({"timeScheme": "implicit"})["timeScheme"] == "bdf2"
    opts = _coerce(OptionsSettings, {"timeScheme": "implicit", "gridXNodes": 20})
    assert opts.timeScheme == "bdf2" and opts.lvLattice == "graded" and opts.gridXNodes == 20


def test_pre_arc_rannacher_choice_survives():
    assert _migrate_options({"timeScheme": "rannacher"})["timeScheme"] == "rannacher"


def test_post_arc_implicit_means_implicit():
    raw = {"timeScheme": "implicit", "lvLattice": "uniform"}
    assert _migrate_options(raw)["timeScheme"] == "implicit"
    opts = _coerce(OptionsSettings, raw)
    assert opts.timeScheme == "implicit" and opts.lvLattice == "uniform"


def test_blob_without_scheme_is_untouched():
    assert "timeScheme" not in _migrate_options({"gridXNodes": 12})

"""API tests for the persisted Fit/Options defaults ([REQ 2026-06-15]).

The Options "Save as default" button writes the current Fit + Options settings
to the app store so a backend restart restores them. Invariants:

1. Without a store (VOLFIT_DB unset) the defaults endpoints report
   ``storeEnabled=False`` and POST is a 422 — nothing to persist to.
2. With a store, POST persists the *current* settings; a fresh app on the same
   DB (a simulated restart) boots with them instead of the code defaults.
3. DELETE clears the saved blob and reverts the live settings to code defaults.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


def _client(store_path=None) -> TestClient:
    return TestClient(create_app(reference_date=REF_DATE, store_path=store_path))


def test_no_store_disables_save():
    with _client() as c:
        status = c.get("/settings/defaults").json()
        assert status == {"storeEnabled": False, "hasSaved": False}
        # Saving is unavailable without a configured store.
        assert c.post("/settings/defaults").status_code == 422


def test_save_survives_restart(tmp_path):
    db = tmp_path / "app.sqlite"

    # First "session": change a Fit and an Options field, then save as default.
    with _client(db) as c:
        assert c.get("/settings/defaults").json() == {
            "storeEnabled": True,
            "hasSaved": False,
        }
        assert c.put("/settings/fit", json={"model": "svi", "nOrder": 5}).status_code == 200
        assert c.put("/settings/options", json={**_options(c), "ssr": 1.5}).status_code == 200
        assert c.post("/settings/defaults").json() == {
            "storeEnabled": True,
            "hasSaved": True,
        }

    # Second "session" on the same DB == a backend restart: the saved defaults
    # come back, not the code defaults (model "lqd" / ssr 2.0).
    with _client(db) as c:
        assert c.get("/settings/defaults").json()["hasSaved"] is True
        fit = c.get("/settings/fit").json()
        assert fit["model"] == "svi" and fit["nOrder"] == 5
        assert c.get("/settings/options").json()["ssr"] == 1.5


def test_reset_clears_and_reverts(tmp_path):
    db = tmp_path / "app.sqlite"
    with _client(db) as c:
        c.put("/settings/fit", json={"model": "svi"})
        c.post("/settings/defaults")

        reset = c.delete("/settings/defaults").json()
        assert reset["hasSaved"] is False
        # The reset response carries the reverted (code-default) settings...
        assert reset["fit"]["model"] == "lqd"
        assert reset["options"]["ssr"] == 2.0
        # ...and the live settings followed.
        assert c.get("/settings/fit").json()["model"] == "lqd"
        assert c.get("/settings/defaults").json()["hasSaved"] is False

    # A restart now boots on code defaults (the saved blob was cleared).
    with _client(db) as c:
        assert c.get("/settings/fit").json()["model"] == "lqd"


def _options(client: TestClient) -> dict:
    """Current OptionsSettings as a mutable dict (PUT requires the full model)."""
    return client.get("/settings/options").json()

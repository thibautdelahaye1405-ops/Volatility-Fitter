"""The Data Source light must see an account-side refusal raised by the CHAIN
LISTING, not only by a quote request (volfit.data.bloomberg ``_chain`` →
``_record``).

Live case 2026-09-10: the Terminal answered every ReferenceDataRequest with
``category=LIMIT; subcategory=WORKFLOW_REVIEW_NEEDED``; the restored universe
wore three yellow "no data" pills (the listing failed per ticker) while the
Bloomberg light stayed green "real-time (Terminal)" — only ``fetch_chain``
recorded refusals. Offline here with a blp stand-in that refuses ``bds``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from volfit.data.bloomberg import BloombergProvider

_REFUSAL = (
    "Request failed on //blp/refdata::ReferenceDataRequest - Bloomberg responseError: "
    "source=rsfrdsvc1; category=LIMIT; code=-4002; subcategory=WORKFLOW_REVIEW_NEEDED; "
    "message=Workflow review needed. [nid:21941]"
)


class RefusingBlp:
    """A connected Terminal whose reference requests are refused account-side;
    ``allow`` flips it back to answering (an empty chain is enough)."""

    def __init__(self) -> None:
        self.allow = False
        self.bds_calls = 0

    def is_connected(self) -> bool:
        return True

    def bds(self, security, field, **kwargs):
        self.bds_calls += 1
        if not self.allow:
            raise RuntimeError(_REFUSAL)
        return pd.DataFrame({"ticker": [], "field": [], "Security Description": []})

    def bdp(self, securities, fields, **_):
        raise RuntimeError(_REFUSAL)


def test_a_refused_chain_listing_reaches_the_light():
    blp = RefusingBlp()
    provider = BloombergProvider(["SX5E INDEX"], blp_module=blp)
    assert provider.feed_status()[0] != "red"  # nothing recorded yet
    with pytest.raises(RuntimeError):
        provider.available_expiries("SX5E INDEX")  # the universe-load path
    level, detail = provider.feed_status()
    assert level == "red"
    assert "workflow" in detail.lower(), detail
    # A listing that answers again clears the remembered refusal.
    blp.allow = True
    provider.refresh_chain_cache()
    assert provider.available_expiries("SX5E INDEX") == []
    assert provider.feed_status()[0] != "red"

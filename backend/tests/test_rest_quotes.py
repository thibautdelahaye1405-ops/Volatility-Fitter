"""REST quotes client guards (the live paths are covered by the capture smoke).

The shadowed-stub-key failure (a 4-char VOLFIT_MASSIVE_KEY 401ing every call) must
fail loudly at construction, not silently produce empty chains.
"""

from __future__ import annotations

import pytest

from backtest.rest_quotes import RestQuotesClient


def test_stub_key_rejected():
    with pytest.raises(ValueError):
        RestQuotesClient("abcd")  # the 4-char stub that shadowed the real key
    with pytest.raises(ValueError):
        RestQuotesClient("")


def test_real_length_key_constructs():
    client = RestQuotesClient("x" * 32, concurrency=10)
    assert client.concurrency == 10
    assert client.base_url.startswith("https://")

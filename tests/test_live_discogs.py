"""Read-only live check against api.discogs.com through the extension's own code.

Skipped unless DISCOGS_TOKEN_FILE names a file holding a Discogs personal user token.
Only GET requests are allowed (any other method fails before it is sent), at most
MAX_REQUESTS in total, with a pause before each one. The token is read from the file
inside the test and never printed; assertions check shapes and header values only.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

TOKEN_FILE = os.environ.get("DISCOGS_TOKEN_FILE", "")
MAX_REQUESTS = 12
PAUSE_SECONDS = 2.0
RELEASE_ID = 249504  # The release used in the Discogs documentation examples.

pytestmark = pytest.mark.skipif(not TOKEN_FILE, reason="DISCOGS_TOKEN_FILE is not set")


@pytest.fixture(scope="module")
def live(request) -> Any:
    from handlers import discogs_client
    from handlers.actions import ACTION_HANDLERS

    secrets = {"user_token": Path(TOKEN_FILE).read_text(encoding="utf-8").strip()}
    real_urlopen = discogs_client.urlopen
    sent: list[str] = []

    def _guarded(req: Any, timeout: int) -> Any:
        if req.get_method() != "GET":
            raise AssertionError("the live check sends GET requests only")
        if len(sent) >= MAX_REQUESTS:
            raise AssertionError("the live check request budget is spent")
        time.sleep(PAUSE_SECONDS)
        sent.append(req.get_method())
        return real_urlopen(req, timeout)

    setattr(discogs_client, "urlopen", _guarded)  # noqa: B010 - restored by the finalizer

    def _call(action_id: str, payload: dict[str, Any], username: str = "") -> dict[str, Any]:
        config: dict[str, Any] = {"mock_mode": False}
        if username:
            config["username"] = username
        target = {"connection": {"config": config, "secrets": secrets}}
        return ACTION_HANDLERS[action_id](
            {"action_id": action_id, "input": payload, "target": target}
        )

    request.addfinalizer(lambda: setattr(discogs_client, "urlopen", real_urlopen))
    identity = _call("discogs_identity", {})
    assert identity["ok"] is True
    username = identity["result"]["data"].get("username") or ""
    assert username

    def _account_call(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return _call(action_id, payload, username)

    _account_call.sent = sent  # type: ignore[attr-defined]
    _account_call.identity = identity  # type: ignore[attr-defined]
    return _account_call


def _assert_rate_limit(result: dict[str, Any]) -> None:
    rate_limit = result["result"]["rate_limit"]
    assert set(rate_limit) == {"limit", "used", "remaining"}
    assert all(isinstance(value, int) for value in rate_limit.values())


def test_identity_returns_rate_limit_headers(live) -> None:
    _assert_rate_limit(live.identity)


def test_fee_is_calculated_in_the_requested_currency(live) -> None:
    eur = live("discogs_calculate_marketplace_fee", {"price": "10.00", "currency": "EUR"})
    assert eur["ok"] is True
    assert eur["result"]["data"]["currency"] == "EUR"
    assert eur["result"]["path"] == "/marketplace/fee/10.00/EUR"
    _assert_rate_limit(eur)
    usd = live("discogs_calculate_marketplace_fee", {"price": "10.00"})
    assert usd["result"]["data"]["currency"] == "USD"


def test_community_rating_and_collection_reads(live) -> None:
    rating = live("discogs_get_community_release_rating", {"release_id": RELEASE_ID})
    assert rating["ok"] is True
    assert set(rating["result"]["data"]["rating"]) >= {"count", "average"}
    _assert_rate_limit(rating)
    value = live("discogs_get_collection_value", {})
    assert value["ok"] is True
    assert set(value["result"]["data"]) >= {"minimum", "median", "maximum"}
    by_release = live("discogs_get_collection_items_by_release", {"release_id": RELEASE_ID})
    assert by_release["ok"] is True
    assert "releases" in by_release["result"]["data"]


def test_inventory_reads(live) -> None:
    page = live("discogs_list_inventory", {"page": 1, "per_page": 5})
    assert page["ok"] is True
    pagination = page["result"]["data"]["pagination"]
    assert {"page", "pages", "per_page", "items"} <= set(pagination)
    assert isinstance(page["result"]["data"]["listings"], list)
    _assert_rate_limit(page)
    everything = live("discogs_list_all_inventory", {"per_page": 100})
    assert everything["ok"] is True
    result = everything["result"]
    assert result["total_items"] == pagination["items"]
    assert result["item_count"] == pagination["items"] or result["complete"] is False
    _assert_rate_limit(everything)
    uploads = live("discogs_list_inventory_uploads", {})
    assert uploads["ok"] is True
    assert "pagination" in uploads["result"]["data"]
    exports = live("discogs_get_inventory_exports", {})
    assert exports["ok"] is True
    assert "pagination" in exports["result"]["data"]
    assert len(live.sent) <= MAX_REQUESTS

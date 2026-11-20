"""Behaviour of the steps added or corrected against the Discogs reference (0.2.7)."""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

RATE_HEADERS = {
    "X-Discogs-Ratelimit": "60",
    "X-Discogs-Ratelimit-Used": "5",
    "X-Discogs-Ratelimit-Remaining": "55",
}
LIVE_CONNECTION = {"config": {"mock_mode": False, "username": "seller"}, "secrets": {}}
WRITE_CONNECTION = {
    "config": {"mock_mode": False, "username": "seller", "enable_write_actions": True},
    "secrets": {"user_token": "secret-token"},
}


class _Response:
    def __init__(self, body: Any, headers: dict[str, str] | None = None, status: int = 200):
        self.status = status
        self.headers = {**RATE_HEADERS, **(headers or {})}
        self._raw = b"" if body is None else json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, _size: int = -1) -> bytes:
        return self._raw


class _Recorder:
    """Fake transport: records each request and answers from a callable."""

    def __init__(self, answer):
        self.answer = answer
        self.requests: list[dict[str, Any]] = []
        self.raw: list[dict[str, Any]] = []

    def __call__(self, request, timeout: int):
        url = urlparse(request.full_url)
        record = {
            "method": request.get_method(),
            "path": url.path,
            "query": {key: values[0] for key, values in parse_qs(url.query).items()},
            "body": (
                json.loads(request.data)
                if request.data and "json" in (request.get_header("Content-type") or "")
                else None
            ),
        }
        self.requests.append(record)
        self.raw.append(
            {"raw": request.data or b"", "content_type": request.get_header("Content-type") or ""}
        )
        return self.answer(record)


def _run(monkeypatch, recorder: _Recorder, action_id: str, payload: dict, connection=None):
    from handlers import discogs_client
    from handlers.actions import ACTION_HANDLERS

    monkeypatch.setattr(discogs_client, "urlopen", recorder)
    action = {
        "action_id": action_id,
        "input": payload,
        "target": {"connection": connection or LIVE_CONNECTION},
    }
    return ACTION_HANDLERS[action_id](action)


def test_rate_limit_comes_from_the_documented_headers_and_falls_back_to_bare_names() -> None:
    from handlers.discogs_client import _rate_limit_from_headers

    assert _rate_limit_from_headers(RATE_HEADERS) == {"limit": 60, "used": 5, "remaining": 55}
    assert _rate_limit_from_headers(
        {
            "Discogs-Ratelimit": "25",
            "Discogs-Ratelimit-Used": "1",
            "Discogs-Ratelimit-Remaining": "24",
        }
    ) == {"limit": 25, "used": 1, "remaining": 24}
    assert _rate_limit_from_headers({}) == {"limit": None, "used": None, "remaining": None}


def test_rate_limit_is_returned_with_a_429_refusal(monkeypatch) -> None:
    def _refuse(record):
        raise HTTPError(
            "https://api.discogs.com" + record["path"],
            429,
            "Too Many Requests",
            {**RATE_HEADERS, "X-Discogs-Ratelimit-Remaining": "0"},  # type: ignore[arg-type]
            io.BytesIO(b"{}"),
        )

    result = _run(monkeypatch, _Recorder(_refuse), "discogs_get_release", {"release_id": 249504})
    assert result["ok"] is False
    assert result["error"] == "rate_limited"
    assert result["result"]["rate_limit"] == {"limit": 60, "used": 5, "remaining": 0}


def test_every_generic_step_returns_rate_limit(monkeypatch) -> None:
    recorder = _Recorder(lambda record: _Response({"rating": {"count": 1, "average": 4.0}}))
    result = _run(
        monkeypatch, recorder, "discogs_get_community_release_rating", {"release_id": 249504}
    )
    assert result["ok"] is True
    assert recorder.requests[0]["path"] == "/releases/249504/rating"
    assert result["result"]["rate_limit"] == {"limit": 60, "used": 5, "remaining": 55}


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({"price": "10.00", "currency": "eur"}, "/marketplace/fee/10.00/EUR"),
        ({"price": "10.00"}, "/marketplace/fee/10.00"),
    ],
)
def test_fee_currency_is_part_of_the_documented_path(monkeypatch, payload, path) -> None:
    recorder = _Recorder(lambda record: _Response({"value": 0.42, "currency": "EUR"}))
    result = _run(monkeypatch, recorder, "discogs_calculate_marketplace_fee", payload)
    assert result["ok"] is True
    assert recorder.requests == [{"method": "GET", "path": path, "query": {}, "body": None}]


def test_fee_rejects_an_undocumented_currency_before_any_request(monkeypatch) -> None:
    recorder = _Recorder(lambda record: _Response({}))
    result = _run(
        monkeypatch,
        recorder,
        "discogs_calculate_marketplace_fee",
        {"price": "10.00", "currency": "PLN"},
    )
    assert result["error"] == "invalid_payload"
    assert recorder.requests == []


@pytest.mark.parametrize(
    ("operation_id", "payload", "path", "query"),
    [
        (
            "discogs_list_inventory",
            {"status": "For Sale", "sort": "price", "sort_order": "asc", "page": 2, "per_page": 50},
            "/users/seller/inventory",
            {
                "status": "For Sale",
                "sort": "price",
                "sort_order": "asc",
                "page": "2",
                "per_page": "50",
            },
        ),
        ("discogs_list_inventory_uploads", {"page": 1}, "/inventory/upload", {"page": "1"}),
        ("discogs_get_inventory_upload", {"upload_id": 119615}, "/inventory/upload/119615", {}),
        ("discogs_get_list", {"list_id": "123"}, "/lists/123", {}),
        (
            "discogs_get_collection_items_by_release",
            {"release_id": 249504},
            "/users/seller/collection/releases/249504",
            {},
        ),
        ("discogs_get_collection_value", {}, "/users/seller/collection/value", {}),
    ],
)
def test_new_read_steps_call_the_documented_address(
    monkeypatch, operation_id, payload, path, query
) -> None:
    recorder = _Recorder(lambda record: _Response({"pagination": {}, "listings": [], "items": []}))
    connection = {
        "config": {"mock_mode": False, "username": "seller"},
        "secrets": {"user_token": "t"},
    }
    result = _run(monkeypatch, recorder, operation_id, payload, connection)
    assert result["ok"] is True, result
    assert recorder.requests == [{"method": "GET", "path": path, "query": query, "body": None}]


def test_list_inventory_returns_the_listings_as_items(monkeypatch) -> None:
    body = {
        "pagination": {"page": 1, "pages": 1, "per_page": 50, "items": 1},
        "listings": [{"id": 7, "status": "For Sale"}],
    }
    result = _run(monkeypatch, _Recorder(lambda r: _Response(body)), "discogs_list_inventory", {})
    assert result["items"] == [{"id": 7, "status": "For Sale"}]
    assert result["result"]["data"]["pagination"]["items"] == 1


@pytest.mark.parametrize(
    "operation_id",
    [
        "discogs_request_inventory_export",
        "discogs_edit_user_profile",
        "discogs_edit_collection_instance",
        "discogs_edit_wantlist_release",
    ],
)
def test_new_writes_are_guarded(monkeypatch, operation_id) -> None:
    recorder = _Recorder(lambda record: _Response({}))
    payload = {"release_id": 1, "folder_id": 1, "instance_id": 2, "confirm": True}
    disabled = _run(monkeypatch, recorder, operation_id, payload)
    assert disabled["error"] == "write_actions_disabled"
    unconfirmed = _run(
        monkeypatch, recorder, operation_id, {**payload, "confirm": False}, WRITE_CONNECTION
    )
    assert unconfirmed["error"] == "confirmation_required"
    assert recorder.requests == []


def test_inventory_export_is_accepted_not_applied(monkeypatch) -> None:
    recorder = _Recorder(
        lambda record: _Response(
            None, headers={"Location": "https://api.discogs.com/inventory/export/599632"}
        )
    )
    result = _run(
        monkeypatch,
        recorder,
        "discogs_request_inventory_export",
        {"confirm": True},
        WRITE_CONNECTION,
    )
    assert recorder.requests == [
        {"method": "POST", "path": "/inventory/export", "query": {}, "body": None}
    ]
    assert result["ok"] is True
    assert result["result"]["processing"] == "accepted"
    assert result["result"]["applied"] is False
    assert result["result"]["check"] == "discogs_get_inventory_export"
    assert result["result"]["export_id"] == 599632
    assert result["result"]["rate_limit"]["remaining"] == 55


UPLOAD_CSV = {
    "add": "release_id,price,media_condition\n123,1.50,Mint (M)\n",
    "change": "release_id,price\n123,2.00\n",
    "delete": "listing_id\n12345678\n",
}


@pytest.mark.parametrize("kind", ["add", "change", "delete"])
def test_inventory_uploads_point_to_their_upload_record(monkeypatch, kind) -> None:
    recorder = _Recorder(
        lambda record: _Response(
            None, headers={"Location": "https://api.discogs.com/inventory/upload/599632"}
        )
    )
    result = _run(
        monkeypatch,
        recorder,
        f"discogs_inventory_upload_{kind}",
        {"csv": UPLOAD_CSV[kind], "confirm": True},
        WRITE_CONNECTION,
    )
    assert recorder.requests[0]["path"] == f"/inventory/upload/{kind}"
    assert result["result"]["processing"] == "accepted"
    assert result["result"]["check"] == "discogs_get_inventory_upload"
    assert result["result"]["upload_id"] == 599632


def test_edit_collection_instance_moves_with_the_body_folder(monkeypatch) -> None:
    recorder = _Recorder(lambda record: _Response(None, status=204))
    result = _run(
        monkeypatch,
        recorder,
        "discogs_edit_collection_instance",
        {
            "folder_id": 1,
            "release_id": 249504,
            "instance_id": 3,
            "new_folder_id": 4,
            "rating": 5,
            "confirm": True,
        },
        WRITE_CONNECTION,
    )
    assert result["ok"] is True
    assert recorder.requests == [
        {
            "method": "POST",
            "path": "/users/seller/collection/folders/1/releases/249504/instances/3",
            "query": {},
            "body": {"rating": 5, "folder_id": 4},
        }
    ]


def test_edit_wantlist_and_profile_post_their_documented_fields(monkeypatch) -> None:
    recorder = _Recorder(lambda record: _Response({"id": 1}))
    _run(
        monkeypatch,
        recorder,
        "discogs_edit_wantlist_release",
        {"release_id": 249504, "notes": "First press", "rating": 4, "confirm": True},
        WRITE_CONNECTION,
    )
    _run(
        monkeypatch,
        recorder,
        "discogs_edit_user_profile",
        {"location": "Vilnius", "curr_abbr": "eur", "confirm": True},
        WRITE_CONNECTION,
    )
    assert recorder.requests == [
        {
            "method": "POST",
            "path": "/users/seller/wants/249504",
            "query": {},
            "body": {"notes": "First press", "rating": 4},
        },
        {
            "method": "POST",
            "path": "/users/seller",
            "query": {},
            "body": {"location": "Vilnius", "curr_abbr": "EUR"},
        },
    ]
    refused = _run(
        monkeypatch,
        recorder,
        "discogs_edit_user_profile",
        {"curr_abbr": "XYZ", "confirm": True},
        WRITE_CONNECTION,
    )
    assert refused["error"] == "invalid_payload"
    assert len(recorder.requests) == 2


def _inventory_server(totals: list[int] | int, listing_offset: int = 0):
    """Answer inventory pages; ``totals`` may change per request to simulate edits."""

    calls = {"n": 0}

    def _answer(record):
        page = int(record["query"]["page"])
        per_page = int(record["query"]["per_page"])
        total = totals if isinstance(totals, int) else totals[min(calls["n"], len(totals) - 1)]
        calls["n"] += 1
        first = (page - 1) * per_page
        listings = [
            {"id": listing_offset + index} for index in range(first, min(total, first + per_page))
        ]
        return _Response(
            {
                "pagination": {
                    "page": page,
                    "pages": max(1, -(-total // per_page)),
                    "per_page": per_page,
                    "items": total,
                    "urls": {},
                },
                "listings": listings,
            }
        )

    return _answer


def test_list_all_inventory_reads_every_page_exactly_once(monkeypatch) -> None:
    recorder = _Recorder(_inventory_server(5))
    result = _run(
        monkeypatch, recorder, "discogs_list_all_inventory", {"per_page": 2, "status": "For Sale"}
    )["result"]
    assert [item["id"] for item in result["listings"]] == [0, 1, 2, 3, 4]
    assert [r["query"]["page"] for r in recorder.requests] == ["1", "2", "3"]
    assert all(r["query"]["status"] == "For Sale" for r in recorder.requests)
    assert result["complete"] is True
    assert result["next_page"] is None
    assert result["total_items"] == 5
    assert result["warnings"] == []
    assert result["rate_limit"] == {"limit": 60, "used": 5, "remaining": 55}


def test_list_all_inventory_defaults_to_the_documented_maximum_page_size(monkeypatch) -> None:
    recorder = _Recorder(_inventory_server(0))
    result = _run(monkeypatch, recorder, "discogs_list_all_inventory", {})["result"]
    assert recorder.requests[0]["query"]["per_page"] == "100"
    assert result["complete"] is True
    assert result["listings"] == []
    refused = _run(monkeypatch, recorder, "discogs_list_all_inventory", {"per_page": 101})
    assert refused["error"] == "invalid_payload"


def test_list_all_inventory_continues_exactly_from_next_page(monkeypatch) -> None:
    recorder = _Recorder(_inventory_server(5))
    first = _run(
        monkeypatch, recorder, "discogs_list_all_inventory", {"per_page": 2, "max_items": 3}
    )["result"]
    assert [item["id"] for item in first["listings"]] == [0, 1]
    assert first["complete"] is False
    assert first["stop_reason"] == "max_items"
    assert first["next_page"] == 2
    rest = _run(
        monkeypatch,
        recorder,
        "discogs_list_all_inventory",
        {"per_page": 2, "page": first["next_page"]},
    )["result"]
    assert [item["id"] for item in rest["listings"]] == [2, 3, 4]
    assert rest["complete"] is True


def test_list_all_inventory_stops_on_the_time_budget(monkeypatch) -> None:
    from handlers import actions

    ticks = iter([0.0] + [100.0] * 10)
    monkeypatch.setattr(actions.time, "monotonic", lambda: next(ticks))
    recorder = _Recorder(_inventory_server(5))
    result = _run(
        monkeypatch,
        recorder,
        "discogs_list_all_inventory",
        {"per_page": 2, "time_budget_seconds": 5},
    )["result"]
    assert [item["id"] for item in result["listings"]] == [0, 1]
    assert result["complete"] is False
    assert result["stop_reason"] == "time_budget"
    assert result["next_page"] == 2


def test_list_all_inventory_flags_a_total_that_changes_while_reading(monkeypatch) -> None:
    recorder = _Recorder(_inventory_server([5, 6]))
    result = _run(monkeypatch, recorder, "discogs_list_all_inventory", {"per_page": 2})["result"]
    assert result["complete"] is False
    assert result["warnings"] == ["inventory_changed_during_read"]
    assert result["next_page"] is None
    assert [item["id"] for item in result["listings"]] == [0, 1]


def test_list_all_inventory_refuses_a_page_that_does_not_match_its_request(monkeypatch) -> None:
    def _wrong_page(record):
        return _Response(
            {
                "pagination": {"page": 1, "pages": 3, "per_page": 50, "items": 5},
                "listings": [{"id": 1}],
            }
        )

    result = _run(
        monkeypatch, _Recorder(_wrong_page), "discogs_list_all_inventory", {"per_page": 2}
    )["result"]
    assert result["complete"] is False
    assert result["warnings"] == ["pagination_mismatch"]
    assert result["listings"] == []


def test_list_all_inventory_refuses_repeated_listings(monkeypatch) -> None:
    def _repeat(record):
        page = int(record["query"]["page"])
        return _Response(
            {
                "pagination": {"page": page, "pages": 2, "per_page": 2, "items": 4},
                "listings": [{"id": 1}, {"id": 2}],
            }
        )

    result = _run(monkeypatch, _Recorder(_repeat), "discogs_list_all_inventory", {"per_page": 2})[
        "result"
    ]
    assert result["complete"] is False
    assert result["warnings"] == ["inconsistent_page"]
    assert [item["id"] for item in result["listings"]] == [1, 2]


def test_list_all_inventory_runs_in_mock_mode() -> None:
    from handlers.actions import ACTION_HANDLERS

    result = ACTION_HANDLERS["discogs_list_all_inventory"](
        {
            "action_id": "discogs_list_all_inventory",
            "input": {"username": "demo", "per_page": 2, "connection_config": {"mock_mode": True}},
        }
    )["result"]
    assert result["complete"] is True
    assert result["item_count"] == 3


# -- inventory uploads are the CSV file Discogs documents ----------------------------------


def _multipart_parts(sent: dict[str, Any]) -> list[dict[str, Any]]:
    """The parts of a recorded multipart/form-data request, split on its boundary."""
    kind, _, params = sent["content_type"].partition(";")
    assert kind.strip() == "multipart/form-data"
    boundary = params.split("boundary=", 1)[1].strip().encode("ascii")
    raw = sent["raw"]
    assert raw.endswith(b"\r\n--" + boundary + b"--\r\n")
    parts = []
    for chunk in raw.split(b"--" + boundary)[1:-1]:
        assert chunk.startswith(b"\r\n") and chunk.endswith(b"\r\n")
        head, _, content = chunk[2:-2].partition(b"\r\n\r\n")
        headers = dict(line.split(": ", 1) for line in head.decode("ascii").split("\r\n") if line)
        disposition = headers["Content-Disposition"]
        name = re.search(r' name="([^"]*)"', disposition)
        filename = re.search(r'filename="([^"]*)"', disposition)
        assert name is not None and filename is not None
        parts.append(
            {
                "name": name.group(1),
                "filename": filename.group(1),
                "content_type": headers["Content-Type"],
                "content": content,
            }
        )
    return parts


def _upload_answer(record: dict[str, Any]) -> _Response:
    return _Response(None, headers={"Location": "https://api.discogs.com/inventory/upload/599632"})


@pytest.mark.parametrize("kind", ["add", "change", "delete"])
def test_an_upload_is_sent_as_a_multipart_file_named_upload(monkeypatch, kind) -> None:
    recorder = _Recorder(_upload_answer)
    result = _run(
        monkeypatch,
        recorder,
        f"discogs_inventory_upload_{kind}",
        {"csv": UPLOAD_CSV[kind], "confirm": True},
        WRITE_CONNECTION,
    )
    assert result["ok"] is True, result
    assert recorder.requests[0]["method"] == "POST"
    sent = recorder.raw[0]
    parts = _multipart_parts(sent)
    assert [(p["name"], p["filename"], p["content_type"]) for p in parts] == [
        ("upload", "inventory.csv", "text/csv")
    ]
    assert parts[0]["content"] == UPLOAD_CSV[kind].encode("utf-8")
    assert b'"items"' not in sent["raw"] and b'"csv"' not in sent["raw"]


def test_items_become_the_documented_csv_with_exact_prices(monkeypatch) -> None:
    recorder = _Recorder(_upload_answer)
    items = [
        {"release_id": 123, "price": 1.5, "media_condition": "Mint (M)", "comments": "a, b"},
        {
            "release_id": "456",
            "price": "2.50",
            "media_condition": "Near Mint (NM or M-)",
            "accept_offer": "Y",
            "weight": 230,
        },
        {"release_id": 789, "price": 0.1, "media_condition": "Good (G)"},
    ]
    result = _run(
        monkeypatch,
        recorder,
        "discogs_inventory_upload_add",
        {"items": items, "confirm": True},
        WRITE_CONNECTION,
    )
    assert result["ok"] is True, result
    content = _multipart_parts(recorder.raw[0])[0]["content"].decode("utf-8")
    assert content == (
        "release_id,price,media_condition,comments,accept_offer,weight\r\n"
        '123,1.5,Mint (M),"a, b",,\r\n'
        "456,2.50,Near Mint (NM or M-),,Y,230\r\n"
        "789,0.1,Good (G),,,\r\n"
    )


def test_items_for_delete_and_change_use_their_own_columns(monkeypatch) -> None:
    recorder = _Recorder(_upload_answer)
    _run(
        monkeypatch,
        recorder,
        "discogs_inventory_upload_delete",
        {"items": [{"listing_id": 12345678}, {"listing_id": "98765432"}], "confirm": True},
        WRITE_CONNECTION,
    )
    _run(
        monkeypatch,
        recorder,
        "discogs_inventory_upload_change",
        {"items": [{"release_id": 123, "price": "3.00"}], "confirm": True},
        WRITE_CONNECTION,
    )
    contents = [_multipart_parts(r)[0]["content"].decode("utf-8") for r in recorder.raw]
    assert contents == [
        "listing_id\r\n12345678\r\n98765432\r\n",
        "release_id,price\r\n123,3.00\r\n",
    ]


@pytest.mark.parametrize(
    ("kind", "payload", "said"),
    [
        ("add", {"csv": UPLOAD_CSV["add"], "file": "artifact-1"}, "exactly one of"),
        ("add", {"csv": UPLOAD_CSV["add"], "items": [{"release_id": 1}]}, "exactly one of"),
        ("add", {}, "exactly one of"),
        (
            "add",
            {"items": [{"release_id": 1, "price": 1, "media_condition": "Mint (M)", "color": "x"}]},
            "does not take for add: color",
        ),
        ("delete", {"items": [{"listing_id": 1, "release_id": 2}]}, "does not take for delete"),
        ("add", {"csv": "release_id,price,media_condition,color\n1,1,Mint (M),x\n"}, "color"),
        ("delete", {"csv": "release_id\n1\n"}, "does not take for delete: release_id"),
        ("add", {"items": [{"release_id": 1, "price": 1}]}, "missing: media_condition"),
        ("change", {"items": [{"release_id": 1}]}, "at least one of"),
        ("add", {"items": [{"release_id": 1, "price": 1, "media_condition": "Shiny"}]}, "media"),
        (
            "add",
            {"items": [{"release_id": 1, "price": "x", "media_condition": "Mint (M)"}]},
            "price",
        ),
        (
            "add",
            {"items": [{"release_id": 1.5, "price": 1, "media_condition": "Mint (M)"}]},
            "whole",
        ),
        ("delete", {"items": [{"listing_id": 1}], "file": "a"}, "exactly one of"),
    ],
)
def test_an_upload_is_refused_before_anything_is_sent(monkeypatch, kind, payload, said) -> None:
    recorder = _Recorder(_upload_answer)
    result = _run(
        monkeypatch,
        recorder,
        f"discogs_inventory_upload_{kind}",
        {**payload, "confirm": True},
        WRITE_CONNECTION,
    )
    assert result["ok"] is False and result["error"] == "invalid_payload", result
    assert said in json.dumps(result)
    assert recorder.requests == []


def test_an_upload_from_a_workflow_file_reads_the_granted_file(monkeypatch) -> None:
    from handlers import actions

    seen: dict[str, Any] = {}

    def _reader(payload, *, artifact_id="", binding_key="", timeout_seconds=30.0):
        seen["artifact_id"] = artifact_id
        seen["payload"] = payload
        return UPLOAD_CSV["delete"].encode("utf-8")

    monkeypatch.setattr(actions, "read_artifact_bytes", _reader)
    recorder = _Recorder(_upload_answer)
    grant = {"inputs": [{"artifact_id": "artifact-7", "field": "file"}]}
    from handlers import discogs_client

    monkeypatch.setattr(discogs_client, "urlopen", recorder)
    action = {
        "action_id": "discogs_inventory_upload_delete",
        "input": {"file": "artifact-7", "confirm": True},
        "target": {"connection": WRITE_CONNECTION},
        "artifacts": grant,
    }
    result = actions.ACTION_HANDLERS["discogs_inventory_upload_delete"](action)
    assert result["ok"] is True, result
    assert seen == {"artifact_id": "artifact-7", "payload": {"artifacts": grant}}
    assert _multipart_parts(recorder.raw[0])[0]["content"] == b"listing_id\n12345678\n"


def test_the_router_hands_the_file_grant_to_the_action(monkeypatch) -> None:
    from handlers import router

    seen: dict[str, Any] = {}
    monkeypatch.setitem(
        router.ACTION_HANDLERS, "discogs_inventory_upload_add", lambda a: seen.update(a) or {}
    )
    monkeypatch.setattr(router, "runtime_context_from_payload", lambda payload: None)
    grant = {"inputs": [{"artifact_id": "artifact-1"}]}
    router.handle_request(
        {
            "mode": "action",
            "action": {"action_id": "discogs_inventory_upload_add"},
            "artifacts": grant,
        }
    )
    assert seen["artifacts"] == grant

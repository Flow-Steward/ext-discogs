"""Every documented Discogs method and path is a step of this extension, or excluded with a reason.

The reference is tests/reference/discogs_api_endpoints.json, extracted with
scripts/extract_api_reference.py from a saved copy of https://www.discogs.com/developers
(web-archive snapshot of 2026-11-06, SHA-256 pinned below).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

REFERENCE = BUNDLE_ROOT / "tests" / "reference" / "discogs_api_endpoints.json"
SNAPSHOT_SHA256 = "3a0979581229a4d44cac287305ff91f8323836ce337c8d5a0961e5445669859a"

# Documented endpoints that are deliberately not steps.
EXCLUDED = {
    ("GET", "/oauth/request_token"): (
        "OAuth 1.0a login procedure (request token); the extension authenticates with a "
        "personal user token instead."
    ),
    ("POST", "/oauth/access_token"): (
        "OAuth 1.0a login procedure (access token); the extension authenticates with a "
        "personal user token instead."
    ),
}

# Steps whose address is not a single static template of DISCOGS_API_OPERATIONS.
EXTRA_STEP_PATHS = {
    # With a currency the fee step appends it to the path (documented "Fee with currency").
    ("GET", "/marketplace/fee/{price}/{currency}"): "discogs_calculate_marketplace_fee",
    # The whole-inventory step reads the documented inventory pages one after another.
    ("GET", "/users/{username}/inventory"): "discogs_list_all_inventory",
}

# Steps that exist in the extension but whose address the reference does not document.
UNDOCUMENTED_STEPS = {
    "discogs_get_wantlist_release": (
        "GET /users/{username}/wants/{release_id} predates this reference; the page documents "
        "only PUT, POST and DELETE on that address. Kept unchanged for existing workflows."
    ),
    "discogs_get_collection_release": (
        "GET /users/{username}/collection/folders/{folder_id}/releases/{release_id} predates "
        "this reference; the page documents only POST on that address and reads copies of a "
        "release through discogs_get_collection_items_by_release. Kept unchanged for existing "
        "workflows."
    ),
}


def _reference() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def _key(method: str, path: str) -> tuple[str, str]:
    return method.upper(), re.sub(r"\{[^}]+\}", "{}", path)


def _step_paths() -> dict[tuple[str, str], set[str]]:
    from handlers.actions import DISCOGS_API_OPERATIONS

    mapping: dict[tuple[str, str], set[str]] = {}
    for operation_id, spec in DISCOGS_API_OPERATIONS.items():
        mapping.setdefault(_key(spec["method"], spec["path"]), set()).add(operation_id)
    for (method, path), operation_id in EXTRA_STEP_PATHS.items():
        mapping.setdefault(_key(method, path), set()).add(operation_id)
    return mapping


def _manifest_operations() -> dict[str, dict]:
    data = yaml.safe_load((BUNDLE_ROOT / "contracts/operation_manifest.yaml").read_text())
    return {item["operation_id"]: item for item in data["operations"]}


def test_reference_is_the_pinned_snapshot() -> None:
    reference = _reference()
    assert reference["snapshot_sha256"] == SNAPSHOT_SHA256
    assert reference["source_url"] == "https://www.discogs.com/developers"
    assert len(reference["endpoints"]) == 62


def test_every_documented_endpoint_is_a_step_or_excluded_with_a_reason() -> None:
    steps = _step_paths()
    manifest = _manifest_operations()
    uncovered = []
    for endpoint in _reference()["endpoints"]:
        method, path = endpoint["method"], endpoint["path"]
        if (method, path) in EXCLUDED:
            assert EXCLUDED[(method, path)].strip()
            continue
        operation_ids = steps.get(_key(method, path), set())
        if not operation_ids or not operation_ids <= set(manifest):
            uncovered.append(f"{method} {path}")
    assert uncovered == []


def test_exclusions_and_undocumented_steps_are_current() -> None:
    documented = {_key(item["method"], item["path"]) for item in _reference()["endpoints"]}
    assert {_key(*key) for key in EXCLUDED} <= documented
    assert {_key(*key) for key in EXTRA_STEP_PATHS} <= documented

    from handlers.actions import DISCOGS_API_OPERATIONS

    undocumented = {
        operation_id
        for operation_id, spec in DISCOGS_API_OPERATIONS.items()
        if _key(spec["method"], spec["path"]) not in documented
    }
    assert undocumented == set(UNDOCUMENTED_STEPS)


def test_every_step_is_declared_handled_and_has_a_form() -> None:
    from handlers.actions import ACTION_HANDLERS, DISCOGS_API_OPERATIONS

    manifest = _manifest_operations()
    forms = {
        item["operation_id"]
        for item in yaml.safe_load((BUNDLE_ROOT / "contracts/step_ui_manifest.yaml").read_text())[
            "forms"
        ]
    }
    actions = {
        item["action_id"]
        for item in yaml.safe_load((BUNDLE_ROOT / "ui/actions/actions.yaml").read_text())["actions"]
    }
    steps = set(DISCOGS_API_OPERATIONS) | {"discogs_list_all_inventory"}
    assert set(manifest) == steps
    assert forms == steps
    assert steps <= actions
    assert steps <= set(ACTION_HANDLERS)


def test_every_step_declares_rate_limit_as_an_output() -> None:
    actions = {
        item["action_id"]: item
        for item in yaml.safe_load((BUNDLE_ROOT / "ui/actions/actions.yaml").read_text())["actions"]
    }
    for operation_id, operation in _manifest_operations().items():
        outputs = {item["name"]: item for item in operation["outputs"]}
        assert "result.rate_limit" in outputs, operation_id
        assert "limit, used and remaining" in outputs["result.rate_limit"]["description"]
        assert "result.rate_limit" in operation["result_fields"], operation_id
        assert "result.rate_limit" in actions[operation_id]["result_fields"], operation_id


def test_writes_are_actions_that_require_confirmation() -> None:
    from handlers.actions import DISCOGS_API_OPERATIONS

    manifest = _manifest_operations()
    for operation_id, spec in DISCOGS_API_OPERATIONS.items():
        is_write = spec["method"] != "GET"
        assert bool(spec.get("write")) is is_write, operation_id
        operation = manifest[operation_id]
        assert (operation["operation_kind"] == "action") is is_write, operation_id
        confirm = [item for item in operation["inputs"] if item["name"] == "confirm"]
        assert bool(confirm) is is_write, operation_id


def test_runtime_constants_match_the_reference() -> None:
    from handlers import discogs_client
    from handlers.actions import DOCUMENTED_CURRENCIES, INVENTORY_MAX_PER_PAGE

    reference = _reference()
    assert reference["rate_limit_headers"] == [
        "X-Discogs-Ratelimit",
        "X-Discogs-Ratelimit-Used",
        "X-Discogs-Ratelimit-Remaining",
    ]
    headers = {name: str(index + 1) for index, name in enumerate(reference["rate_limit_headers"])}
    assert discogs_client._rate_limit_from_headers(headers) == {
        "limit": 1,
        "used": 2,
        "remaining": 3,
    }
    assert reference["pagination_max_per_page"] == INVENTORY_MAX_PER_PAGE
    fee = next(
        item
        for item in reference["endpoints"]
        if item["path"] == "/marketplace/fee/{price}/{currency}"
    )
    currency = next(item for item in fee["parameters"] if item["name"] == "currency")
    assert tuple(currency["choices"]) == DOCUMENTED_CURRENCIES


def test_extractor_reads_the_documented_panel_layout() -> None:
    sys.path.insert(0, str(BUNDLE_ROOT / "scripts"))
    try:
        from extract_api_reference import extract
    finally:
        sys.path.remove(str(BUNDLE_ROOT / "scripts"))

    page = (
        b"<p>change the number of items per page (up to 100), use</p>"
        b"<p>X-Discogs-Ratelimit: total</p>"
        b'<section class="panel panel-success" id="x-post"><div class="panel-heading">'
        b'<span class="sr-only-action-name">Edit Thing</span>'
        b'<a class="btn btn-xs btn-success" href="#">POST</a>'
        b'<div class="overflow-hidden"> <code>/things/{thing_id}{?page,per_page}</code> </div>'
        b"</div><dl><dt>thing_id</dt> <dd> <code>integer</code>"
        b'<span class="required">(required)</span></dd></dl>'
        b"<strong> Response &nbsp; <code>204</code></strong></section>"
    )
    facts = extract(page)
    assert facts["rate_limit_headers"] == ["X-Discogs-Ratelimit"]
    assert facts["pagination_max_per_page"] == 100
    assert facts["endpoints"] == [
        {
            "section": "x-post",
            "action": "Edit Thing",
            "method": "POST",
            "path": "/things/{thing_id}",
            "query": ["page", "per_page"],
            "parameters": [
                {"name": "thing_id", "type": "integer", "required": True, "choices": []}
            ],
            "responses": ["204"],
        }
    ]

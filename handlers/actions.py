"""Action handlers for the Discogs API extension."""

from __future__ import annotations

import json
from typing import Any

from handlers.common import (
    action_input,
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_text,
    connection_config,
    connection_secrets,
    default_settings,
    fail,
    ok,
    redacted_secret_refs,
)
from handlers.discogs_client import DiscogsClient
from handlers.queries import (
    _provider_error,
    _provider_error_details,
    _normalize_search_item,
    normalize_release,
)


DISCOGS_API_OPERATIONS: dict[str, dict[str, Any]] = {
    "discogs_identity": {"method": "GET", "path": "/oauth/identity", "auth": True},
    "discogs_search_database": {
        "method": "GET",
        "path": "/database/search",
        "params": [
            "query",
            "type",
            "artist",
            "release_title",
            "label",
            "year",
            "barcode",
            "catno",
            "page",
            "per_page",
        ],
    },
    "discogs_get_release": {"method": "GET", "path": "/releases/{release_id}", "required": ["release_id"]},
    "discogs_get_release_rating": {"method": "GET", "path": "/releases/{release_id}/rating/{username}", "required": ["release_id", "username"], "auth": True},
    "discogs_update_release_rating": {"method": "PUT", "path": "/releases/{release_id}/rating/{username}", "required": ["release_id", "username"], "write": True, "body_fields": ["rating"]},
    "discogs_delete_release_rating": {"method": "DELETE", "path": "/releases/{release_id}/rating/{username}", "required": ["release_id", "username"], "write": True},
    "discogs_get_release_stats": {"method": "GET", "path": "/releases/{release_id}/stats", "required": ["release_id"]},
    "discogs_get_master": {"method": "GET", "path": "/masters/{master_id}", "required": ["master_id"]},
    "discogs_get_master_versions": {"method": "GET", "path": "/masters/{master_id}/versions", "required": ["master_id"], "params": ["page", "per_page", "format", "label", "released", "country", "sort", "sort_order"]},
    "discogs_get_artist": {"method": "GET", "path": "/artists/{artist_id}", "required": ["artist_id"]},
    "discogs_get_artist_releases": {"method": "GET", "path": "/artists/{artist_id}/releases", "required": ["artist_id"], "params": ["page", "per_page", "sort", "sort_order"]},
    "discogs_get_label": {"method": "GET", "path": "/labels/{label_id}", "required": ["label_id"]},
    "discogs_get_label_releases": {"method": "GET", "path": "/labels/{label_id}/releases", "required": ["label_id"], "params": ["page", "per_page"]},
    "discogs_get_marketplace_listing": {"method": "GET", "path": "/marketplace/listings/{listing_id}", "required": ["listing_id"]},
    "discogs_create_marketplace_listing": {"method": "POST", "path": "/marketplace/listings", "write": True, "body_fields": ["release_id", "condition", "sleeve_condition", "price", "status", "comments", "allow_offers", "external_id", "location", "weight", "format_quantity"]},
    "discogs_update_marketplace_listing": {"method": "POST", "path": "/marketplace/listings/{listing_id}", "required": ["listing_id"], "write": True, "body_fields": ["release_id", "condition", "sleeve_condition", "price", "status", "comments", "allow_offers", "external_id", "location", "weight", "format_quantity"]},
    "discogs_delete_marketplace_listing": {"method": "DELETE", "path": "/marketplace/listings/{listing_id}", "required": ["listing_id"], "write": True},
    "discogs_get_marketplace_stats": {"method": "GET", "path": "/marketplace/stats/{release_id}", "required": ["release_id"]},
    "discogs_get_price_suggestions": {"method": "GET", "path": "/marketplace/price_suggestions/{release_id}", "required": ["release_id"], "auth": True},
    "discogs_calculate_marketplace_fee": {"method": "GET", "path": "/marketplace/fee/{price}", "required": ["price"], "params": ["currency"]},
    "discogs_list_orders": {"method": "GET", "path": "/marketplace/orders", "auth": True, "params": ["status", "created_after", "created_before", "archived", "sort", "sort_order", "page", "per_page"]},
    "discogs_get_order": {"method": "GET", "path": "/marketplace/orders/{order_id}", "required": ["order_id"], "auth": True},
    "discogs_update_order": {"method": "POST", "path": "/marketplace/orders/{order_id}", "required": ["order_id"], "write": True, "body_fields": ["status", "shipping", "archived"]},
    "discogs_list_order_messages": {"method": "GET", "path": "/marketplace/orders/{order_id}/messages", "required": ["order_id"], "auth": True},
    "discogs_add_order_message": {"method": "POST", "path": "/marketplace/orders/{order_id}/messages", "required": ["order_id"], "write": True, "body_fields": ["message", "status"]},
    "discogs_get_user_profile": {"method": "GET", "path": "/users/{username}", "required": ["username"]},
    "discogs_get_user_submissions": {"method": "GET", "path": "/users/{username}/submissions", "required": ["username"], "params": ["page", "per_page"]},
    "discogs_get_user_contributions": {"method": "GET", "path": "/users/{username}/contributions", "required": ["username"], "params": ["page", "per_page", "sort", "sort_order"]},
    "discogs_get_user_lists": {"method": "GET", "path": "/users/{username}/lists", "required": ["username"], "params": ["page", "per_page"]},
    "discogs_get_collection_folders": {"method": "GET", "path": "/users/{username}/collection/folders", "required": ["username"], "auth": True},
    "discogs_create_collection_folder": {"method": "POST", "path": "/users/{username}/collection/folders", "required": ["username"], "write": True, "body_fields": ["name"]},
    "discogs_get_collection_folder": {"method": "GET", "path": "/users/{username}/collection/folders/{folder_id}", "required": ["username", "folder_id"], "auth": True},
    "discogs_update_collection_folder": {"method": "POST", "path": "/users/{username}/collection/folders/{folder_id}", "required": ["username", "folder_id"], "write": True, "body_fields": ["name"]},
    "discogs_delete_collection_folder": {"method": "DELETE", "path": "/users/{username}/collection/folders/{folder_id}", "required": ["username", "folder_id"], "write": True},
    "discogs_get_collection_releases": {"method": "GET", "path": "/users/{username}/collection/folders/{folder_id}/releases", "required": ["username", "folder_id"], "auth": True, "params": ["page", "per_page", "sort", "sort_order"]},
    "discogs_get_collection_release": {"method": "GET", "path": "/users/{username}/collection/folders/{folder_id}/releases/{release_id}", "required": ["username", "folder_id", "release_id"], "auth": True},
    "discogs_add_collection_release": {"method": "POST", "path": "/users/{username}/collection/folders/{folder_id}/releases/{release_id}", "required": ["username", "folder_id", "release_id"], "write": True, "body_fields": ["notes", "rating"]},
    "discogs_delete_collection_instance": {"method": "DELETE", "path": "/users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}", "required": ["username", "folder_id", "release_id", "instance_id"], "write": True},
    "discogs_get_collection_fields": {"method": "GET", "path": "/users/{username}/collection/fields", "required": ["username"], "auth": True},
    "discogs_edit_collection_field_value": {"method": "POST", "path": "/users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}/fields/{field_id}", "required": ["username", "folder_id", "release_id", "instance_id", "field_id"], "write": True, "body_fields": ["value"]},
    "discogs_get_wantlist": {"method": "GET", "path": "/users/{username}/wants", "required": ["username"], "auth": True, "params": ["page", "per_page"]},
    "discogs_get_wantlist_release": {"method": "GET", "path": "/users/{username}/wants/{release_id}", "required": ["username", "release_id"], "auth": True},
    "discogs_add_wantlist_release": {"method": "PUT", "path": "/users/{username}/wants/{release_id}", "required": ["username", "release_id"], "write": True, "body_fields": ["notes", "rating"]},
    "discogs_delete_wantlist_release": {"method": "DELETE", "path": "/users/{username}/wants/{release_id}", "required": ["username", "release_id"], "write": True},
    "discogs_get_inventory_exports": {"method": "GET", "path": "/inventory/export", "auth": True},
    "discogs_get_inventory_export": {"method": "GET", "path": "/inventory/export/{export_id}", "required": ["export_id"], "auth": True},
    "discogs_download_inventory_export": {"method": "GET", "path": "/inventory/export/{export_id}/download", "required": ["export_id"], "auth": True},
    "discogs_inventory_upload_add": {"method": "POST", "path": "/inventory/upload/add", "write": True, "body_fields": ["items", "csv"]},
    "discogs_inventory_upload_change": {"method": "POST", "path": "/inventory/upload/change", "write": True, "body_fields": ["items", "csv"]},
    "discogs_inventory_upload_delete": {"method": "POST", "path": "/inventory/upload/delete", "write": True, "body_fields": ["items", "csv"]},
}


def _client_for_action(action: dict[str, Any]) -> DiscogsClient:
    payload = action_input(action)
    config = default_settings()
    config.update(as_dict(payload.get("connection_config") or payload.get("config")))
    config.update(connection_config(action))
    secrets = as_dict(payload.get("secrets"))
    secrets.update(connection_secrets(action))
    return DiscogsClient.from_payload(config, secrets)


def _require_write_ready(client: DiscogsClient, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not client.config.enable_write_actions:
        return fail("write_actions_disabled", "Discogs write actions are disabled in project config.")
    if not client.config.token:
        return fail("authentication_required", "Discogs token is required.")
    if not as_bool(payload.get("confirm"), False):
        return fail("confirmation_required", "confirm=true is required for Discogs write actions.")
    return None


def _filled_path(template: str, payload: dict[str, Any], client: DiscogsClient) -> tuple[str, dict[str, Any] | None]:
    values = dict(payload)
    if "username" not in values and client.config.username:
        values["username"] = client.config.username
    missing = []
    path = template
    for key in ("username", "release_id", "master_id", "artist_id", "label_id", "listing_id", "order_id", "folder_id", "instance_id", "field_id", "export_id", "price"):
        token = "{" + key + "}"
        if token not in path:
            continue
        value = as_text(values.get(key))
        if not value:
            missing.append(key)
            continue
        path = path.replace(token, value)
    if missing:
        return "", fail("invalid_payload", f"Missing required field(s): {', '.join(missing)}")
    return path, None


def _body_from_payload(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    if isinstance(payload.get("body"), dict):
        return as_dict(payload.get("body"))
    return {field: payload[field] for field in fields if field in payload}


def _params_from_payload(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    default_fields = ["page", "per_page"]
    names = fields or default_fields
    return {field: payload[field] for field in names if payload.get(field) not in (None, "", [], {})}


def execute_discogs_api_operation(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    action_id = as_text(action.get("action_id"))
    operation_id = as_text(payload.get("operation_id") or action_id)
    spec = DISCOGS_API_OPERATIONS.get(operation_id)
    if not spec:
        return fail("invalid_payload", f"unsupported_discogs_operation:{operation_id}")
    client = _client_for_action(action)
    if spec.get("auth") and not client.config.token:
        return fail("authentication_required", "Discogs token is required.")
    if spec.get("write"):
        blocked = _require_write_ready(client, payload)
        if blocked:
            return blocked
    for field in as_list(spec.get("required")):
        if field == "username" and client.config.username and not payload.get("username"):
            continue
        if payload.get(field) in (None, ""):
            return fail("invalid_payload", f"{field} is required.")
    path, error = _filled_path(as_text(spec.get("path")), payload, client)
    if error:
        return error
    method = as_text(spec.get("method"), "GET").upper()
    params = _params_from_payload(payload, as_list(spec.get("params"))) if method == "GET" else {}
    if operation_id == "discogs_search_database" and "query" in params:
        params["q"] = params.pop("query")
    body = _body_from_payload(payload, as_list(spec.get("body_fields"))) if method != "GET" else None
    response = client.request_api(method, path, params=params, body=body)
    if not response.get("ok"):
        return _provider_error(response)
    data = as_dict(response.get("body"))
    items = as_list(data.get("results"))
    if operation_id == "discogs_search_database":
        data["result_count"] = len(items)
        data["results_json"] = json.dumps(items, ensure_ascii=False, indent=2)
    result = {
        "operation_id": operation_id,
        "method": method,
        "path": path,
        "provider_status": response.get("status_code"),
        "data": data,
        "rate_limit": response.get("rate_limit"),
    }
    return ok(result, items=items, summary={"operation_id": operation_id, "status": response.get("status_code")})


def save_connection_settings(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    values = as_dict(payload.get("values")) or payload
    settings = default_settings()
    for key in settings:
        if key in values:
            settings[key] = values[key]
    settings["allowed_hosts"] = sorted(
        {
            as_text(item).lower()
            for item in (values.get("allowed_hosts") or settings["allowed_hosts"])
            if as_text(item)
        }
        or {"api.discogs.com"}
    )
    settings["mock_mode"] = as_bool(settings.get("mock_mode"), False)
    settings["enable_write_actions"] = as_bool(settings.get("enable_write_actions"), False)
    return ok(
        {"status": "saved", "saved_config": settings},
        reload=["connection_status", "provider_health", "rate_limit_panel"],
        summary={"status": "saved", "mock_mode": settings["mock_mode"]},
    )


def save_secrets(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    return ok(
        {"status": "saved", "secret_refs": redacted_secret_refs(payload)},
        reload=["connection_status", "provider_health"],
        summary={"status": "saved", "secret_values": "redacted"},
    )


def test_discogs_connection(action: dict[str, Any]) -> dict[str, Any]:
    client = _client_for_action(action)
    request_path = "/oauth/identity"
    response = client.test_connection()
    if not response.get("ok"):
        error, message, provider_status = _provider_error_details(response)
        return ok(
            {
                "status": "failed",
                "message": message,
                "error_code": error,
                "auth_mode": "token",
                "authenticated": bool(client.config.token),
                "endpoint": request_path,
                "http_status": provider_status,
                "rate_limit": as_dict(response.get("rate_limit")),
            },
            reload=["connection_status", "provider_health", "rate_limit_panel"],
            summary={
                "connection": "Failed",
                "reason": message,
                "error": error,
            },
            errors=[{"code": error, "message": message}],
        )
    body = as_dict(response.get("body"))
    authenticated = bool(client.config.token)
    return ok(
        {
            "status": "success",
            "message": "Connected to Discogs.",
            "auth_mode": "token",
            "authenticated": authenticated,
            "username": body.get("username"),
            "endpoint": request_path,
            "http_status": response.get("status_code"),
            "rate_limit": response.get("rate_limit"),
        },
        reload=["connection_status", "provider_health", "rate_limit_panel"],
        summary={
            "connection": "Success",
            "http_status": response.get("status_code"),
            "auth_mode": "token",
            "username": body.get("username") or "n/a",
        },
    )


def enrich_release_metadata(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    row_target = as_dict(action.get("target"))
    release_id = as_int(payload.get("release_id") or row_target.get("id") or row_target.get("release_id"), 0)
    if release_id <= 0:
        return fail("invalid_payload", "release_id is required.")
    client = _client_for_action(action)
    response = client.get_release(release_id)
    if not response.get("ok"):
        return _provider_error(response)
    result = normalize_release(as_dict(response.get("body")), include_raw=as_bool(payload.get("include_raw"), False))
    if as_bool(payload.get("include_marketplace"), False):
        stats = client.get_marketplace_stats(release_id)
        if stats.get("ok"):
            result["marketplace"] = as_dict(stats.get("body"))
        else:
            result["marketplace_error"] = stats.get("error")
    return ok(result, summary={"release_id": release_id, "title": result.get("title")})


def search_discogs_database(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    search_text = as_text(payload.get("query") or payload.get("q"))
    if not search_text and not any(payload.get(key) for key in ("artist", "release_title", "barcode")):
        return fail("invalid_payload", "query, artist, release_title, or barcode is required.")
    client = _client_for_action(action)
    response = client.search_database(
        {
            "q": search_text,
            "type": payload.get("type"),
            "artist": payload.get("artist"),
            "release_title": payload.get("release_title"),
            "barcode": payload.get("barcode"),
            "page": payload.get("page"),
            "per_page": payload.get("per_page"),
        }
    )
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    return ok(
        {
            "items": [_normalize_search_item(item) for item in body.get("results", []) if isinstance(item, dict)],
            "pagination": as_dict(body.get("pagination")),
        },
        summary={"count": len(body.get("results", []) if isinstance(body.get("results"), list) else [])},
    )


def compare_release_to_query(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    release_id = as_int(payload.get("release_id"), 0)
    query = as_dict(payload.get("query"))
    if release_id <= 0 or not query:
        return fail("invalid_payload", "release_id and query are required.")
    release_response = _client_for_action(action).get_release(release_id)
    if not release_response.get("ok"):
        return _provider_error(release_response)
    release = normalize_release(as_dict(release_response.get("body")))
    matched: list[str] = []
    score = 0
    title = as_text(query.get("title") or query.get("release_title")).lower()
    if title and title in as_text(release.get("title")).lower():
        matched.append("title")
        score += 40
    artist = as_text(query.get("artist")).lower()
    if artist and any(artist in as_text(item.get("name")).lower() for item in release.get("artists", [])):
        matched.append("artist")
        score += 35
    if query.get("year") and str(query.get("year")) == str(release.get("year")):
        matched.append("year")
        score += 15
    barcode = as_text(query.get("barcode"))
    if barcode and any(barcode == as_text(item.get("value")) for item in release.get("identifiers", [])):
        matched.append("barcode")
        score += 10
    return ok(
        {"release_id": release_id, "score": min(100, score), "matched_fields": matched, "warnings": [] if matched else ["no_strong_matches"], "release": release},
        summary={"score": min(100, score), "matched": len(matched)},
    )


def lookup_database_entity(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    entity_type = as_text(payload.get("entity_type")).lower()
    entity_id = as_int(payload.get("entity_id") or payload.get("id"), 0)
    if entity_id <= 0 or entity_type not in {"master", "artist", "label"}:
        return fail("invalid_payload", "entity_type must be master, artist, or label and entity_id is required.")
    client = _client_for_action(action)
    if entity_type == "master":
        response = client.get_master(entity_id)
    elif entity_type == "artist":
        response = client.get_artist(entity_id)
    else:
        response = client.get_label(entity_id)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    body["entity_type"] = entity_type
    body["entity_id"] = entity_id
    return ok(body, summary={"entity_type": entity_type, "entity_id": entity_id})


def marketplace_stats(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    release_id = as_int(payload.get("release_id") or payload.get("id"), 0)
    if release_id <= 0:
        return fail("invalid_payload", "release_id is required.")
    response = _client_for_action(action).get_marketplace_stats(release_id)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    body["release_id"] = body.get("release_id", release_id)
    body["rate_limit"] = response.get("rate_limit")
    return ok(body, summary={"release_id": release_id, "num_for_sale": body.get("num_for_sale")})


def collection_release_status(action: dict[str, Any]) -> dict[str, Any]:
    from handlers.queries import collection_release_status as query_collection_release_status

    payload = action_input(action)
    return query_collection_release_status({"params": payload, "target": action.get("target")})


def add_release_to_wantlist(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    client = _client_for_action(action)
    blocked = _require_write_ready(client, payload)
    if blocked:
        return blocked
    username = as_text(payload.get("username"), client.config.username)
    release_id = as_int(payload.get("release_id"), 0)
    if not username or release_id <= 0:
        return fail("invalid_payload", "username and release_id are required.")
    body = {key: payload[key] for key in ("notes", "rating") if key in payload}
    response = client.add_wantlist_release(username, release_id, body)
    if not response.get("ok"):
        return _provider_error(response)
    return ok({"release_id": release_id, "added": True, "provider_status": response.get("status_code")}, summary={"added": True})


def remove_release_from_wantlist(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    client = _client_for_action(action)
    blocked = _require_write_ready(client, payload)
    if blocked:
        return blocked
    username = as_text(payload.get("username"), client.config.username)
    release_id = as_int(payload.get("release_id"), 0)
    if not username or release_id <= 0:
        return fail("invalid_payload", "username and release_id are required.")
    response = client.remove_wantlist_release(username, release_id)
    if not response.get("ok"):
        return _provider_error(response)
    return ok({"release_id": release_id, "removed": True, "provider_status": response.get("status_code")}, summary={"removed": True})


def add_release_to_collection_folder(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    client = _client_for_action(action)
    blocked = _require_write_ready(client, payload)
    if blocked:
        return blocked
    username = as_text(payload.get("username"), client.config.username)
    folder_id = as_int(payload.get("folder_id"), 1)
    release_id = as_int(payload.get("release_id"), 0)
    if not username or release_id <= 0:
        return fail("invalid_payload", "username and release_id are required.")
    body = {key: payload[key] for key in ("notes", "rating") if key in payload}
    response = client.add_collection_release(username, folder_id, release_id, body)
    if not response.get("ok"):
        return _provider_error(response)
    return ok({"release_id": release_id, "folder_id": folder_id, "added": True, "provider_status": response.get("status_code")}, summary={"added": True})


def delete_collection_instance(action: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(action)
    client = _client_for_action(action)
    blocked = _require_write_ready(client, payload)
    if blocked:
        return blocked
    username = as_text(payload.get("username"), client.config.username)
    folder_id = as_int(payload.get("folder_id"), 1)
    release_id = as_int(payload.get("release_id"), 0)
    instance_id = as_int(payload.get("instance_id"), 0)
    if not username or release_id <= 0 or instance_id <= 0:
        return fail("invalid_payload", "username, release_id, and instance_id are required.")
    response = client.delete_collection_instance(username, folder_id, release_id, instance_id)
    if not response.get("ok"):
        return _provider_error(response)
    return ok({"release_id": release_id, "folder_id": folder_id, "instance_id": instance_id, "deleted": True, "provider_status": response.get("status_code")}, summary={"deleted": True})


ACTION_HANDLERS = {
    "save_connection_settings": save_connection_settings,
    "save_secrets": save_secrets,
    "test_discogs_connection": test_discogs_connection,
    "search_discogs_database": search_discogs_database,
    "enrich_release_metadata": enrich_release_metadata,
    "compare_release_to_query": compare_release_to_query,
    "lookup_database_entity": lookup_database_entity,
    "marketplace_stats": marketplace_stats,
    "collection_release_status": collection_release_status,
    "add_release_to_wantlist": add_release_to_wantlist,
    "remove_release_from_wantlist": remove_release_from_wantlist,
    "add_release_to_collection_folder": add_release_to_collection_folder,
    "delete_collection_instance": delete_collection_instance,
}

for _operation_id in DISCOGS_API_OPERATIONS:
    ACTION_HANDLERS.setdefault(_operation_id, execute_discogs_api_operation)

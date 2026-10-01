"""Query handlers for the Discogs API extension."""

from __future__ import annotations

from typing import Any

from handlers.common import (
    action_input,
    as_dict,
    as_int,
    as_text,
    connection_config,
    connection_secrets,
    default_settings,
    fail,
    ok,
)
from handlers.discogs_client import DiscogsClient


def _client_for_query(query: dict[str, Any]) -> DiscogsClient:
    params = as_dict(query.get("params"))
    config = default_settings()
    config.update(as_dict(params.get("config") or params.get("connection_config")))
    config.update(connection_config(query))
    secrets = as_dict(params.get("secrets"))
    secrets.update(connection_secrets(query))
    return DiscogsClient.from_payload(config, secrets)


def _provider_error_details(response: dict[str, Any]) -> tuple[str, str, int | None]:
    error = as_text(response.get("error"), "provider_request_failed")
    provider_status = response.get("provider_status")
    if error in {"authentication_required", "permission_denied"} or provider_status in {401, 403}:
        message = "Failed to connect. Check your Discogs user token."
    elif error == "rate_limited" or provider_status == 429:
        message = "Discogs rate limit reached. Try again later."
    elif error == "external_request_blocked":
        message = as_text(response.get("message"), "Request blocked by connection safety settings.")
    elif error == "provider_not_found":
        message = "Discogs endpoint was not found. Check the configured base URL."
    else:
        message = as_text(response.get("message"), "Failed to connect to Discogs. Check network access and connection settings.")
    return error, message, provider_status


def _provider_error(response: dict[str, Any]) -> dict[str, Any]:
    error, message, provider_status = _provider_error_details(response)
    return fail(
        error,
        message,
        provider_status=provider_status,
        result={"rate_limit": as_dict(response.get("rate_limit"))},
    )


def _normalize_search_item(item: dict[str, Any]) -> dict[str, Any]:
    uri = as_text(item.get("uri"))
    if uri.startswith("/"):
        uri = f"https://www.discogs.com{uri}"
    return {
        "id": item.get("id"),
        "type": as_text(item.get("type")),
        "title": as_text(item.get("title")),
        "year": item.get("year"),
        "country": as_text(item.get("country")),
        "format": item.get("format") or [],
        "label": item.get("label") or [],
        "catno": as_text(item.get("catno")),
        "uri": uri,
        "resource_url": as_text(item.get("resource_url")),
    }


def normalize_release(payload: dict[str, Any], *, include_raw: bool = False) -> dict[str, Any]:
    normalized = {
        "release_id": payload.get("id"),
        "title": as_text(payload.get("title")),
        "artists": payload.get("artists") or [],
        "labels": payload.get("labels") or [],
        "formats": payload.get("formats") or [],
        "tracklist": payload.get("tracklist") or [],
        "identifiers": payload.get("identifiers") or [],
        "country": as_text(payload.get("country")),
        "year": payload.get("year"),
        "master_id": payload.get("master_id"),
        "uri": as_text(payload.get("uri")),
    }
    if include_raw:
        normalized["raw"] = payload
    return normalized


def provider_health(query: dict[str, Any]) -> dict[str, Any]:
    client = _client_for_query(query)
    result = {
        "status": "healthy",
        "provider": "discogs",
        "runtime": "local_subprocess",
        "mode": "mock" if client.config.mock_mode else "live",
        "authenticated": bool(client.config.token),
        "token_source": client.config.token_source,
        "base_url": client.config.base_url,
        "username": client.config.username,
        "rate_limit": {"limit": None, "used": None, "remaining": None},
        "checks": [
            {"name": "Subprocess runtime", "status": "healthy", "detail": "main.py handles query/action envelopes"},
            {"name": "Request mode", "status": "healthy", "detail": "mock" if client.config.mock_mode else "live"},
            {"name": "Write actions", "status": "warning" if client.config.enable_write_actions else "healthy", "detail": "enabled" if client.config.enable_write_actions else "disabled"},
        ],
    }
    return ok(result, summary={"status": result["status"], "authenticated": result["authenticated"]})


def load_connection_settings(query: dict[str, Any]) -> dict[str, Any]:
    _ = query
    return ok({"settings": default_settings()}, summary={"status": "loaded"})


def connection_status(query: dict[str, Any]) -> dict[str, Any]:
    client = _client_for_query(query)
    return ok(
        {
            "configured": bool(client.config.base_url and client.config.user_agent),
            "auth_mode": "token" if client.config.token else "anonymous",
            "token_source": client.config.token_source or "missing",
            "username": client.config.username,
            "base_url": client.config.base_url,
            "mock_mode": client.config.mock_mode,
            "write_actions": client.config.enable_write_actions,
            "secrets": {"user_token": f"<{client.config.token_source}>" if client.config.token else "<missing>"},
        },
        summary={"auth_mode": "token" if client.config.token else "anonymous"},
    )


def test_discogs_connection(query: dict[str, Any]) -> dict[str, Any]:
    client = _client_for_query(query)
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
                "token_source": client.config.token_source or "missing",
                "endpoint": request_path,
                "http_status": provider_status,
                "rate_limit": as_dict(response.get("rate_limit")),
            },
            summary={
                "connection": "Failed",
                "reason": message,
                "error": error,
            },
            rate_limit=response.get("rate_limit"),
        )
    body = as_dict(response.get("body"))
    authenticated = bool(client.config.token)
    result = {
        "status": "success",
        "message": "Connected to Discogs.",
        "auth_mode": "token",
        "authenticated": authenticated,
        "token_source": client.config.token_source,
        "username": body.get("username") or client.config.username,
        "endpoint": request_path,
        "http_status": response.get("status_code"),
        "rate_limit": response.get("rate_limit"),
    }
    return ok(
        result,
        summary={
            "connection": "Success",
            "http_status": response.get("status_code"),
            "auth_mode": "token",
            "token_source": client.config.token_source or "unknown",
            "username": result["username"] or "n/a",
        },
        rate_limit=response.get("rate_limit"),
    )


def discogs_search(query: dict[str, Any]) -> dict[str, Any]:
    params = as_dict(query.get("params"))
    client = _client_for_query(query)
    search_params = {
        "q": params.get("query") or params.get("q"),
        "type": params.get("type"),
        "artist": params.get("artist"),
        "release_title": params.get("release_title"),
        "label": params.get("label"),
        "year": params.get("year"),
        "barcode": params.get("barcode"),
        "catno": params.get("catno"),
        "page": as_int(params.get("page"), 1),
        "per_page": as_int(params.get("per_page"), client.config.default_page_size),
    }
    response = client.search_database(search_params)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    items = [_normalize_search_item(as_dict(item)) for item in body.get("results") or []]
    pagination = as_dict(body.get("pagination"))
    return ok(
        {"items": items, "pagination": pagination, "rate_limit": response.get("rate_limit")},
        items=items,
        summary={"total": pagination.get("items", len(items)), "returned": len(items)},
        pagination=pagination,
        rate_limit=response.get("rate_limit"),
    )


def release_details(query: dict[str, Any]) -> dict[str, Any]:
    params = as_dict(query.get("params"))
    release_id = as_int(params.get("release_id") or params.get("id"), 0)
    if release_id <= 0:
        return fail("invalid_payload", "release_id is required.")
    client = _client_for_query(query)
    response = client.get_release(release_id)
    if not response.get("ok"):
        return _provider_error(response)
    result = normalize_release(as_dict(response.get("body")), include_raw=bool(params.get("include_raw")))
    result["rate_limit"] = response.get("rate_limit")
    return ok(result, summary={"release_id": release_id, "title": result.get("title")})


def master_details(query: dict[str, Any]) -> dict[str, Any]:
    params = as_dict(query.get("params"))
    master_id = as_int(params.get("master_id") or params.get("id"), 0)
    if master_id <= 0:
        return fail("invalid_payload", "master_id is required.")
    client = _client_for_query(query)
    response = client.get_master(master_id)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    return ok(
        {
            "master_id": body.get("id"),
            "title": body.get("title"),
            "main_release": body.get("main_release"),
            "artists": body.get("artists") or [],
            "year": body.get("year"),
            "versions_url": body.get("versions_url"),
            "rate_limit": response.get("rate_limit"),
        }
    )


def master_versions(query: dict[str, Any]) -> dict[str, Any]:
    params = as_dict(query.get("params"))
    master_id = as_int(params.get("master_id") or params.get("id"), 0)
    if master_id <= 0:
        return fail("invalid_payload", "master_id is required.")
    client = _client_for_query(query)
    response = client.get_master_versions(master_id, as_int(params.get("page"), 1), as_int(params.get("per_page"), 25))
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    items = [as_dict(item) for item in body.get("versions") or []]
    return ok({"items": items, "pagination": body.get("pagination") or {}}, items=items, pagination=body.get("pagination") or {})


def artist_details(query: dict[str, Any]) -> dict[str, Any]:
    artist_id = as_int(as_dict(query.get("params")).get("artist_id") or as_dict(query.get("params")).get("id"), 0)
    if artist_id <= 0:
        return fail("invalid_payload", "artist_id is required.")
    response = _client_for_query(query).get_artist(artist_id)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    return ok({"artist_id": body.get("id"), "name": body.get("name"), "profile": body.get("profile"), "aliases": body.get("aliases") or [], "members": body.get("members") or [], "urls": body.get("urls") or []})


def label_details(query: dict[str, Any]) -> dict[str, Any]:
    label_id = as_int(as_dict(query.get("params")).get("label_id") or as_dict(query.get("params")).get("id"), 0)
    if label_id <= 0:
        return fail("invalid_payload", "label_id is required.")
    response = _client_for_query(query).get_label(label_id)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    return ok({"label_id": body.get("id"), "name": body.get("name"), "profile": body.get("profile"), "urls": body.get("urls") or []})


def marketplace_stats(query: dict[str, Any]) -> dict[str, Any]:
    release_id = as_int(as_dict(query.get("params")).get("release_id") or as_dict(query.get("params")).get("id"), 0)
    if release_id <= 0:
        return fail("invalid_payload", "release_id is required.")
    response = _client_for_query(query).get_marketplace_stats(release_id)
    if not response.get("ok"):
        return _provider_error(response)
    body = as_dict(response.get("body"))
    return ok({"release_id": body.get("release_id", release_id), "lowest_price": body.get("lowest_price"), "num_for_sale": body.get("num_for_sale"), "blocked_from_sale": body.get("blocked_from_sale"), "rate_limit": response.get("rate_limit")})


def collection_folders(query: dict[str, Any]) -> dict[str, Any]:
    client = _client_for_query(query)
    username = as_text(as_dict(query.get("params")).get("username"), client.config.username)
    if not client.config.token:
        return fail("authentication_required", "Discogs token is required.")
    if not username:
        return fail("invalid_payload", "username is required.")
    response = client.get_collection_folders(username)
    if not response.get("ok"):
        return _provider_error(response)
    items = [as_dict(item) for item in as_dict(response.get("body")).get("folders") or []]
    return ok({"items": items}, items=items, summary={"total": len(items)})


def collection_release_status(query: dict[str, Any]) -> dict[str, Any]:
    params = as_dict(query.get("params"))
    client = _client_for_query(query)
    username = as_text(params.get("username"), client.config.username)
    folder_id = as_int(params.get("folder_id"), 0)
    release_id = as_int(params.get("release_id"), 0)
    if not client.config.token:
        return fail("authentication_required", "Discogs token is required.")
    if not username or release_id <= 0:
        return fail("invalid_payload", "username and release_id are required.")
    response = client.get_collection_release(username, folder_id, release_id)
    if not response.get("ok"):
        return _provider_error(response)
    releases = [as_dict(item) for item in as_dict(response.get("body")).get("releases") or []]
    return ok({"release_id": release_id, "in_collection": bool(releases), "folder_ids": sorted({item.get("folder_id", folder_id) for item in releases}), "items": releases}, items=releases)


def wantlist_status(query: dict[str, Any]) -> dict[str, Any]:
    params = as_dict(query.get("params"))
    client = _client_for_query(query)
    username = as_text(params.get("username"), client.config.username)
    release_id = as_int(params.get("release_id"), 0)
    if not client.config.token:
        return fail("authentication_required", "Discogs token is required.")
    if not username or release_id <= 0:
        return fail("invalid_payload", "username and release_id are required.")
    response = client.get_wantlist_release(username, release_id)
    if not response.get("ok"):
        if response.get("error") == "provider_not_found":
            return ok({"release_id": release_id, "in_wantlist": False})
        return _provider_error(response)
    return ok({"release_id": release_id, "in_wantlist": True})


QUERY_HANDLERS = {
    "provider_health": provider_health,
    "load_connection_settings": load_connection_settings,
    "connection_status": connection_status,
    "test_discogs_connection": test_discogs_connection,
    "discogs_search": discogs_search,
    "release_details": release_details,
    "master_details": master_details,
    "master_versions": master_versions,
    "artist_details": artist_details,
    "label_details": label_details,
    "marketplace_stats": marketplace_stats,
    "collection_folders": collection_folders,
    "collection_release_status": collection_release_status,
    "wantlist_status": wantlist_status,
}

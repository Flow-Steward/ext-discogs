"""Request router for the Discogs API extension."""

from __future__ import annotations

from handlers.actions import ACTION_HANDLERS
from handlers.common import as_dict, as_text, fail
from handlers.queries import QUERY_HANDLERS


def _resolve_mode(request_payload: dict) -> str:
    mode = as_text(request_payload.get("mode")).lower()
    if mode:
        return mode
    if isinstance(request_payload.get("query"), dict):
        return "query"
    if isinstance(request_payload.get("action"), dict):
        return "action"
    return ""


def handle_request(request_payload: dict) -> dict:
    mode = _resolve_mode(request_payload)
    if mode == "query":
        query = as_dict(request_payload.get("query"))
        query["runtime_context"] = as_dict(request_payload.get("runtime_context"))
        query_id = as_text(query.get("query_id") or request_payload.get("query_id"))
        handler = QUERY_HANDLERS.get(query_id)
        if handler is None:
            return fail("invalid_payload", f"unknown_query:{query_id}")
        return handler(query)

    if mode == "action":
        action = as_dict(request_payload.get("action"))
        action["runtime_context"] = as_dict(request_payload.get("runtime_context"))
        action_id = as_text(action.get("action_id") or request_payload.get("action_id"))
        handler = ACTION_HANDLERS.get(action_id)
        if handler is None:
            return fail("invalid_payload", f"unknown_action:{action_id}")
        return handler(action)

    return fail("invalid_payload", f"unsupported_request:{mode}")

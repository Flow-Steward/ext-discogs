"""Shared helpers for the Discogs API extension."""

from __future__ import annotations

from typing import Any

DEFAULT_BASE_URL = "https://api.discogs.com"
DEFAULT_ALLOWED_HOST = "api.discogs.com"
DEFAULT_USER_AGENT = "FlowStewardDiscogsExtension/0.1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, as_int(value, default)))


def ok(
    result: dict[str, Any] | None = None,
    *,
    items: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
    reload: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "result": result or {},
        "items": items or [],
        "summary": summary or {},
        "commands": [],
        "events": [],
        "reload": reload or [],
        "errors": [],
    }
    payload.update(extra)
    return payload


def fail(
    code: str,
    message: str = "",
    *,
    status: int = 2,
    provider_status: int | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_code = as_text(code, "internal_error")
    normalized_message = as_text(message, normalized_code)
    error: dict[str, Any] = {"code": normalized_code, "message": normalized_message}
    if provider_status is not None:
        error["provider_status"] = provider_status
    return {
        "ok": False,
        "error": normalized_code,
        "status": status,
        "result": result or {},
        "items": [],
        "summary": {},
        "commands": [],
        "events": [],
        "reload": [],
        "errors": [error],
    }


def action_input(action: dict[str, Any]) -> dict[str, Any]:
    payload = as_dict(action.get("input"))
    nested = as_dict(payload.get("payload"))
    return nested or payload


def operation_context(operation: dict[str, Any]) -> dict[str, Any]:
    return as_dict(operation.get("context"))


def runtime_connection(operation: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(operation.get("target")).get("connection"))


def connection_config(operation: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(operation) if "action_id" in operation else as_dict(operation.get("params"))
    config = dict(as_dict(payload.get("connection_config") or payload.get("config")))
    config.update(as_dict(runtime_connection(operation).get("config")))
    return config


def connection_secrets(operation: dict[str, Any]) -> dict[str, Any]:
    payload = action_input(operation) if "action_id" in operation else as_dict(operation.get("params"))
    secrets = dict(as_dict(payload.get("secrets")))
    secrets.update(as_dict(runtime_connection(operation).get("secrets")))
    return secrets


def redacted_secret_refs(payload: dict[str, Any]) -> dict[str, str]:
    refs = as_dict(payload.get("secret_refs") or payload.get("secrets"))
    values = as_dict(refs.get("refs")) or refs
    redacted: dict[str, str] = {}
    for key, value in values.items():
        if value in (None, ""):
            continue
        redacted[str(key)] = "<stored>"
    return redacted


def default_settings() -> dict[str, Any]:
    return {
        "base_url": DEFAULT_BASE_URL,
        "allowed_hosts": [DEFAULT_ALLOWED_HOST],
        "username": "",
        "user_agent": DEFAULT_USER_AGENT,
        "default_currency": "USD",
        "default_page_size": 25,
        "mock_mode": False,
        "enable_write_actions": False,
    }

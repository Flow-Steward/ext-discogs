"""Small safe Discogs API client used by the extension runtime."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from handlers.common import (
    DEFAULT_ALLOWED_HOST,
    DEFAULT_BASE_URL,
    DEFAULT_USER_AGENT,
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_text,
    clamp_int,
)

MAX_RESPONSE_BYTES = 1024 * 1024
TOKEN_ENV_NAMES = ("DISCOGS_USER_TOKEN", "DISCOGS_API_TOKEN", "DISCOGS_TOKEN")


class _RejectRedirectHandler(HTTPRedirectHandler):
    """Keep credentials on the already validated request URL only."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_NO_REDIRECT_OPENER = build_opener(_RejectRedirectHandler())


def urlopen(request: Request, timeout: int):
    """Open one validated URL without following provider redirects."""

    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


@dataclass(frozen=True)
class DiscogsClientConfig:
    base_url: str = DEFAULT_BASE_URL
    allowed_hosts: tuple[str, ...] = (DEFAULT_ALLOWED_HOST,)
    user_agent: str = DEFAULT_USER_AGENT
    token: str = ""
    token_source: str = ""
    username: str = ""
    mock_mode: bool = False
    enable_write_actions: bool = False
    default_page_size: int = 25


class DiscogsClient:
    def __init__(self, config: DiscogsClientConfig):
        self.config = config

    @classmethod
    def from_payload(cls, config: dict[str, Any], secrets: dict[str, Any] | None = None) -> "DiscogsClient":
        merged = dict(config)
        secrets = secrets or {}
        token = as_text(secrets.get("user_token") or merged.get("user_token"))
        token_source = "connection" if token else ""
        if not token:
            for env_name in TOKEN_ENV_NAMES:
                token = as_text(os.getenv(env_name))
                if token:
                    token_source = f"env:{env_name}"
                    break
        allowed_hosts = {
            as_text(item).lower()
            for item in as_list(merged.get("allowed_hosts"))
            if as_text(item)
        } or {DEFAULT_ALLOWED_HOST}
        return cls(
            DiscogsClientConfig(
                base_url=as_text(merged.get("base_url"), DEFAULT_BASE_URL).rstrip("/"),
                allowed_hosts=tuple(sorted(allowed_hosts)),
                user_agent=as_text(merged.get("user_agent"), DEFAULT_USER_AGENT),
                token=token,
                token_source=token_source,
                username=as_text(merged.get("username")),
                mock_mode=as_bool(merged.get("mock_mode"), False),
                enable_write_actions=as_bool(merged.get("enable_write_actions"), False),
                default_page_size=clamp_int(
                    merged.get("default_page_size"), default=25, minimum=1, maximum=100
                ),
            )
        )

    def request_summary(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._build_url(path, params or {})
        return {
            "method": "GET",
            "url": url,
            "allowed_hosts": list(self.config.allowed_hosts),
            "authorization": "token" if self.config.token else "none",
            "mock_mode": self.config.mock_mode,
        }

    def _build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        base = self.config.base_url.rstrip("/") + "/"
        rel = path.lstrip("/")
        url = urljoin(base, rel)
        clean_params = {
            key: value
            for key, value in (params or {}).items()
            if value not in (None, "", [], {})
        }
        if clean_params:
            url = f"{url}?{urlencode(clean_params, doseq=True)}"
        return url

    def validate_url(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False, "Discogs API requests must use HTTPS."
        if parsed.username or parsed.password:
            return False, "Discogs API request URLs must not include credentials."
        host = as_text(parsed.hostname).lower()
        if host not in self.config.allowed_hosts:
            return False, f"Host '{host}' is not in allowed_hosts."
        return True, ""

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
        }
        if self.config.token:
            headers["Authorization"] = f"Discogs token={self.config.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        force_live: bool = False,
    ) -> dict[str, Any]:
        url = self._build_url(path, params)
        allowed, reason = self.validate_url(url)
        if not allowed:
            return {"ok": False, "error": "external_request_blocked", "message": reason}
        if self.config.mock_mode and not force_live:
            return self._mock_response(method, path, params or {}, body or {})
        data = None
        headers = self._headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310 - URL is validated above.
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    return {"ok": False, "error": "provider_response_too_large"}
                payload = _decode_json(raw)
                return {
                    "ok": True,
                    "status_code": int(getattr(response, "status", 200)),
                    "body": payload,
                    "rate_limit": _rate_limit_from_headers(response.headers),
                }
        except HTTPError as exc:
            return {
                "ok": False,
                "error": _error_code_for_status(exc.code),
                "provider_status": exc.code,
                "rate_limit": _rate_limit_from_headers(exc.headers),
            }
        except (OSError, URLError, TimeoutError) as exc:
            return {"ok": False, "error": "provider_request_failed", "message": str(exc)[:200]}

    def request_api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(method.upper(), path, params=params, body=body)

    def test_connection(self) -> dict[str, Any]:
        if not self.config.token:
            return {
                "ok": False,
                "error": "authentication_required",
                "message": "Discogs user token is required to test authenticated connection.",
            }
        return self._request("GET", "/oauth/identity", force_live=True)

    def _mock_response(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        _ = body
        path = "/" + path.strip("/")
        rate_limit = {"limit": 60, "used": 1, "remaining": 59}
        if path == "/":
            return {"ok": True, "status_code": 200, "body": {"hello": "discogs"}, "rate_limit": rate_limit}
        if path == "/oauth/identity":
            return {
                "ok": True,
                "status_code": 200,
                "body": {"username": self.config.username or "flowsteward-demo"},
                "rate_limit": rate_limit,
            }
        if path == "/database/search":
            entity_type = as_text(params.get("type"), "release")
            return {
                "ok": True,
                "status_code": 200,
                "body": {
                    "pagination": {"page": as_int(params.get("page"), 1), "per_page": as_int(params.get("per_page"), 25), "items": 1, "pages": 1},
                    "results": [
                        {
                            "id": 249504,
                            "type": entity_type,
                            "title": "Daft Punk - Discovery",
                            "year": 2001,
                            "country": "France",
                            "format": ["CD", "Album"],
                            "label": ["Virgin"],
                            "catno": "7243 8 49606 2 9",
                            "uri": "/Daft-Punk-Discovery/release/249504",
                            "resource_url": f"{self.config.base_url}/releases/249504",
                        }
                    ],
                },
                "rate_limit": rate_limit,
            }
        if path == "/releases/249504" or path.startswith("/releases/"):
            release_id = as_int(path.rsplit("/", 1)[-1], 249504)
            return {"ok": True, "status_code": 200, "body": _mock_release(release_id), "rate_limit": rate_limit}
        if path == "/masters/1000" or path.startswith("/masters/"):
            master_id = as_int(path.rsplit("/", 1)[-1], 1000)
            return {
                "ok": True,
                "status_code": 200,
                "body": {"id": master_id, "title": "Discovery", "main_release": 249504, "artists": [{"id": 1289, "name": "Daft Punk"}], "year": 2001, "versions_url": f"{self.config.base_url}/masters/{master_id}/versions"},
                "rate_limit": rate_limit,
            }
        if "/versions" in path:
            return {
                "ok": True,
                "status_code": 200,
                "body": {"pagination": {"page": 1, "per_page": 25, "items": 1, "pages": 1}, "versions": [{"id": 249504, "title": "Discovery", "format": "CD, Album", "label": "Virgin", "country": "France", "year": 2001}]},
                "rate_limit": rate_limit,
            }
        if path.startswith("/artists/"):
            artist_id = as_int(path.rsplit("/", 1)[-1], 1289)
            return {"ok": True, "status_code": 200, "body": {"id": artist_id, "name": "Daft Punk", "profile": "French electronic music duo.", "aliases": [], "members": [], "urls": ["https://www.discogs.com/artist/1289-Daft-Punk"]}, "rate_limit": rate_limit}
        if path.startswith("/labels/"):
            label_id = as_int(path.rsplit("/", 1)[-1], 123)
            return {"ok": True, "status_code": 200, "body": {"id": label_id, "name": "Virgin", "profile": "Record label.", "urls": ["https://www.discogs.com/label/123"]}, "rate_limit": rate_limit}
        if path.endswith("/marketplace/stats") or "/marketplace/stats" in path:
            release_id = as_int(path.split("/")[2], 249504)
            return {"ok": True, "status_code": 200, "body": {"release_id": release_id, "lowest_price": 12.34, "num_for_sale": 42, "blocked_from_sale": False}, "rate_limit": rate_limit}
        if "/collection/folders" in path and "/releases/" not in path:
            return {"ok": True, "status_code": 200, "body": {"folders": [{"id": 0, "name": "All", "count": 12}, {"id": 1, "name": "Uncategorized", "count": 3}]}, "rate_limit": rate_limit}
        if "/collection/folders/" in path and "/releases/" in path:
            return {"ok": True, "status_code": 200, "body": {"releases": [{"id": 249504, "instance_id": 77, "folder_id": 1}]}, "rate_limit": rate_limit}
        if "/wants/" in path:
            return {"ok": True, "status_code": 200, "body": {"id": as_int(path.rsplit("/", 1)[-1], 249504), "notes": ""}, "rate_limit": rate_limit}
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "mocked": True,
                "method": method.upper(),
                "path": path,
                "params": params,
            },
            "rate_limit": rate_limit,
        }

    def api_root(self) -> dict[str, Any]:
        return self._request("GET", "/")

    def identity(self) -> dict[str, Any]:
        return self._request("GET", "/oauth/identity")

    def search_database(self, params: dict[str, Any]) -> dict[str, Any]:
        clean = dict(params)
        clean["page"] = max(1, as_int(clean.get("page"), 1))
        clean["per_page"] = max(1, min(100, as_int(clean.get("per_page"), self.config.default_page_size)))
        return self._request("GET", "/database/search", params=clean)

    def get_release(self, release_id: int) -> dict[str, Any]:
        return self._request("GET", f"/releases/{release_id}")

    def get_master(self, master_id: int) -> dict[str, Any]:
        return self._request("GET", f"/masters/{master_id}")

    def get_master_versions(self, master_id: int, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        return self._request("GET", f"/masters/{master_id}/versions", params={"page": page, "per_page": per_page})

    def get_artist(self, artist_id: int) -> dict[str, Any]:
        return self._request("GET", f"/artists/{artist_id}")

    def get_label(self, label_id: int) -> dict[str, Any]:
        return self._request("GET", f"/labels/{label_id}")

    def get_marketplace_stats(self, release_id: int) -> dict[str, Any]:
        return self._request("GET", f"/marketplace/stats/{release_id}")

    def get_collection_folders(self, username: str) -> dict[str, Any]:
        return self._request("GET", f"/users/{username}/collection/folders")

    def get_collection_release(self, username: str, folder_id: int, release_id: int) -> dict[str, Any]:
        return self._request("GET", f"/users/{username}/collection/folders/{folder_id}/releases/{release_id}")

    def get_wantlist_release(self, username: str, release_id: int) -> dict[str, Any]:
        return self._request("GET", f"/users/{username}/wants/{release_id}")

    def add_wantlist_release(self, username: str, release_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/users/{username}/wants/{release_id}", body=payload)

    def remove_wantlist_release(self, username: str, release_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/users/{username}/wants/{release_id}")

    def add_collection_release(self, username: str, folder_id: int, release_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/users/{username}/collection/folders/{folder_id}/releases/{release_id}", body=payload)

    def delete_collection_instance(self, username: str, folder_id: int, release_id: int, instance_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}")


def _decode_json(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {"text": text[:1000]}


def _rate_limit_from_headers(headers: Any) -> dict[str, int | None]:
    def _get(name: str) -> int | None:
        try:
            value = headers.get(name)
        except AttributeError:
            value = None
        return as_int(value, 0) if value not in (None, "") else None

    return {
        "limit": _get("Discogs-Ratelimit"),
        "used": _get("Discogs-Ratelimit-Used"),
        "remaining": _get("Discogs-Ratelimit-Remaining"),
    }


def _error_code_for_status(status: int) -> str:
    if status == 401:
        return "authentication_failed"
    if status == 403:
        return "provider_forbidden"
    if status == 404:
        return "provider_not_found"
    if status == 429:
        return "rate_limited"
    return "provider_request_failed"


def _mock_release(release_id: int) -> dict[str, Any]:
    return {
        "id": release_id,
        "title": "Discovery",
        "artists": [{"id": 1289, "name": "Daft Punk"}],
        "labels": [{"id": 123, "name": "Virgin", "catno": "7243 8 49606 2 9"}],
        "formats": [{"name": "CD", "qty": "1", "descriptions": ["Album"]}],
        "tracklist": [{"position": "1", "title": "One More Time", "duration": "5:20"}],
        "identifiers": [{"type": "Barcode", "value": "724384960629"}],
        "country": "France",
        "year": 2001,
        "master_id": 1000,
        "uri": f"https://www.discogs.com/release/{release_id}",
    }

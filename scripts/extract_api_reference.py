"""Extract the documented Discogs API endpoints from a saved developers page.

The official page (https://www.discogs.com/developers) is pinned in this repository
only as extracted facts: tests/reference/discogs_api_endpoints.json carries the
SHA-256 of the source snapshot and one entry per documented method and path.

Usage (standard library only; run isolated because the input is untrusted):

    python3 -I scripts/extract_api_reference.py SNAPSHOT.html > tests/reference/discogs_api_endpoints.json
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path

SOURCE_URL = "https://www.discogs.com/developers"

_SECTION = re.compile(
    r'<section class="panel panel-(?:info|success|warning|danger)" id="([^"]+)">(.*?)</section>',
    re.DOTALL,
)
_ACTION_NAME = re.compile(r'<span class="sr-only-action-name">([^<]*)</span>')
_METHOD = re.compile(r'<a class="btn btn-xs btn-[a-z]+"[^>]*>(GET|POST|PUT|DELETE|PATCH)</a>')
_URI = re.compile(r'<div class="overflow-hidden">\s*<code>([^<]+)</code>')
_PARAM = re.compile(r"<dt>([^<]+)</dt>\s*<dd>\s*<code>([^<]*)</code>(.*?)</dd>", re.DOTALL)
_REQUIRED = re.compile(r'<span class="required">\(required\)</span>')
_CHOICES = re.compile(r"<strong>Choices:&nbsp;</strong>(.*?)</p>", re.DOTALL)
_STATUS = re.compile(r"<strong> Response\s*(?:&nbsp;)*\s*<code>(\d{3})</code>")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def extract(raw: bytes) -> dict:
    page = raw.decode("utf-8", errors="replace")
    endpoints = []
    for section_id, body in _SECTION.findall(page):
        method = _METHOD.search(body)
        uri = _URI.search(body)
        if not method or not uri:
            continue
        template = html.unescape(uri.group(1)).strip()
        path = re.split(r"\{\?|\?", template, maxsplit=1)[0]
        query = re.search(r"\{[?&]([^}]*)\}$", template)
        params = []
        for name, value_type, rest in _PARAM.findall(body):
            choices = _CHOICES.search(rest)
            params.append(
                {
                    "name": html.unescape(name).strip(),
                    "type": html.unescape(value_type).strip(),
                    "required": bool(_REQUIRED.search(rest)),
                    "choices": re.findall(r"<code>([^<]*)</code>", choices.group(1))
                    if choices
                    else [],
                }
            )
        action = _ACTION_NAME.search(body)
        endpoints.append(
            {
                "section": section_id,
                "action": _text(action.group(1)) if action else "",
                "method": method.group(1),
                "path": path,
                "query": query.group(1).split(",") if query else [],
                "parameters": params,
                "responses": sorted(set(_STATUS.findall(body))),
            }
        )
    text = _text(page)
    headers: list[str] = []
    for name in re.findall(r"\bX-Discogs-Ratelimit[A-Za-z-]*", text):
        if name not in headers:
            headers.append(name)
    per_page = re.search(r"number of items per page \(up to (\d+)\)", text)
    return {
        "source_url": SOURCE_URL,
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_bytes": len(raw),
        "rate_limit_headers": headers,
        "pagination_max_per_page": int(per_page.group(1)) if per_page else None,
        "endpoints": endpoints,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    facts = extract(Path(argv[1]).read_bytes())
    print(json.dumps(facts, indent=1, ensure_ascii=False, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

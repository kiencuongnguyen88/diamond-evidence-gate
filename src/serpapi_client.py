from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


class SerpApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchConfig:
    engine: str = "google"
    num: int = 8
    hl: str = "en"
    gl: str = "us"
    timeout_seconds: int = 20


def build_search_url(query: str, api_key: str, config: SearchConfig | None = None) -> str:
    cfg = config or SearchConfig()
    params = {
        "engine": cfg.engine,
        "q": query,
        "api_key": api_key,
        "num": max(1, min(cfg.num, 20)),
        "hl": cfg.hl,
        "gl": cfg.gl,
        "output": "json",
    }
    return SERPAPI_ENDPOINT + "?" + urllib.parse.urlencode(params)


def _read_fixture(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def search(query: str, *, config: SearchConfig | None = None) -> dict[str, Any]:
    """Run one Google Search through SerpApi.

    For tests only, EVIDENCE_SCOUT_FIXTURE may point to a local JSON fixture.
    Production/live runs require SERPAPI_API_KEY.
    """
    fixture = os.getenv("EVIDENCE_SCOUT_FIXTURE")
    if fixture:
        return _read_fixture(fixture)

    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise SerpApiError(
            "SERPAPI_API_KEY is missing. Live sponsor-API proof cannot run without a SerpApi account key."
        )

    cfg = config or SearchConfig()
    url = build_search_url(query, api_key, cfg)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "LiveEvidenceScout/0.1 (DevNetwork 2026 hackathon)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # network/HTTP is surfaced as one bounded integration failure
        raise SerpApiError(f"SerpApi request failed: {exc}") from exc

    if payload.get("error"):
        raise SerpApiError(str(payload["error"]))
    status = (payload.get("search_metadata") or {}).get("status")
    if status and status != "Success":
        raise SerpApiError(f"SerpApi search status was {status!r}")
    return payload

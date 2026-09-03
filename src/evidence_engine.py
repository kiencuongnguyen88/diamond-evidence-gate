from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Iterable

TIME_CUES = re.compile(
    r"\b(latest|today|current|currently|now|recent|new|newest|this week|this month|202[5-9])\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvidenceItem:
    rank: int
    title: str
    url: str
    domain: str
    snippet: str
    date_hint: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _normalize_domains(domains: Iterable[str]) -> list[str]:
    out: list[str] = []
    for raw in domains:
        value = raw.strip().lower()
        if not value:
            continue
        if value.startswith("http://") or value.startswith("https://"):
            value = _domain(value)
        if value.startswith("www."):
            value = value[4:]
        if value and value not in out:
            out.append(value)
    return out


def _domain_allowed(domain: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in allowlist)


def normalize_serpapi_results(
    payload: dict[str, Any], *, trusted_domains: Iterable[str] = (), max_results: int = 8
) -> list[EvidenceItem]:
    allowlist = _normalize_domains(trusted_domains)
    items: list[EvidenceItem] = []
    for result in payload.get("organic_results") or []:
        url = str(result.get("link") or "").strip()
        domain = _domain(url)
        if not url or not domain or not _domain_allowed(domain, allowlist):
            continue
        items.append(
            EvidenceItem(
                rank=int(result.get("position") or (len(items) + 1)),
                title=str(result.get("title") or "Untitled").strip(),
                url=url,
                domain=domain,
                snippet=str(result.get("snippet") or "").strip(),
                date_hint=(str(result.get("date")).strip() if result.get("date") else None),
            )
        )
        if len(items) >= max(1, min(max_results, 20)):
            break
    return items


def assess_evidence(question: str, items: list[EvidenceItem]) -> dict[str, Any]:
    unique_domains = sorted({item.domain for item in items})
    dated = sum(1 for item in items if item.date_hint)
    flags: list[str] = []
    if not items:
        flags.append("NO_EVIDENCE_RESULTS")
    if len(unique_domains) < 2 and len(items) > 1:
        flags.append("LOW_SOURCE_DIVERSITY")
    if TIME_CUES.search(question) and dated == 0 and items:
        flags.append("TIME_SENSITIVE_QUERY_WITHOUT_DATED_RESULTS")
    if len(items) < 3:
        flags.append("LOW_RESULT_COUNT")

    return {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "result_count": len(items),
        "unique_domain_count": len(unique_domains),
        "dated_result_count": dated,
        "flags": flags,
        "evidence": [item.as_dict() for item in items],
    }


def deterministic_digest(question: str, items: list[EvidenceItem], flags: list[str]) -> str:
    if not items:
        return "No usable live-search evidence was returned. Do not answer the question from this run."
    lines = [f"Evidence packet for: {question}"]
    for idx, item in enumerate(items, start=1):
        date = f" ({item.date_hint})" if item.date_hint else ""
        lines.append(f"[{idx}] {item.title}{date} — {item.domain}: {item.snippet}")
    if flags:
        lines.append("Caution flags: " + ", ".join(flags))
    return "\n".join(lines)

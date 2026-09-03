from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


class AIProviderError(RuntimeError):
    pass


def _evidence_context(packet: dict[str, Any]) -> str:
    rows = []
    for idx, item in enumerate(packet.get("evidence") or [], start=1):
        date = item.get("date_hint") or "undated"
        rows.append(
            f"[{idx}] title={item.get('title')} | domain={item.get('domain')} | date={date} | "
            f"url={item.get('url')} | snippet={item.get('snippet')}"
        )
    return "\n".join(rows)


def synthesize_decision_with_ollama(
    question: str,
    proposed_action: str,
    packet: dict[str, Any],
) -> str | None:
    """Ground a bounded decision brief in live evidence using local Ollama.

    The model may recommend, but it never records the Human decision and never
    executes the proposed action. If local AI is unavailable, the caller keeps a
    deterministic evidence packet and the Human Gate stays review-only.
    """
    base = os.getenv("OLLAMA_URL", "").strip().rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "").strip()
    if not base or not model:
        return None

    prompt = (
        "You are preparing a bounded decision brief for a Human reviewer. "
        "Use ONLY the numbered live-search evidence below. Do not invent facts. "
        "The Human, not you, makes the final decision.\n\n"
        "Return four short sections:\n"
        "RECOMMENDATION: PROCEED | HOLD | REJECT\n"
        "RATIONALE: cite evidence like [1] and [2]\n"
        "UNCERTAINTIES: what is still unclear or weakly supported\n"
        "NEXT CHECK: the single most useful fact to verify next, if any\n\n"
        f"DECISION QUESTION:\n{question}\n\n"
        f"PROPOSED ACTION:\n{proposed_action or 'No proposed action supplied.'}\n\n"
        f"LIVE EVIDENCE:\n{_evidence_context(packet)}\n\n"
        f"QUALITY FLAGS:\n{', '.join(packet.get('flags') or []) or 'none'}"
    )
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.1},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise AIProviderError(f"Local Ollama decision synthesis failed: {exc}") from exc
    content = ((payload.get("message") or {}).get("content") or "").strip()
    return content or None

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.ai_provider import AIProviderError, synthesize_decision_with_ollama
from src.evidence_engine import assess_evidence, deterministic_digest, normalize_serpapi_results
from src.serpapi_client import SearchConfig, SerpApiError, search

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PACKETS: dict[str, dict] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _gate_state(packet: dict) -> str:
    hard_flags = {
        "NO_EVIDENCE_RESULTS",
        "LOW_SOURCE_DIVERSITY",
        "LOW_RESULT_COUNT",
        "LOCAL_AI_SYNTHESIS_FAILED",
    }
    if packet.get("serpapi_integration") != "live" and not os.getenv("EVIDENCE_SCOUT_FIXTURE"):
        return "REVIEW_REQUIRED"
    if hard_flags.intersection(packet.get("flags") or []):
        return "REVIEW_REQUIRED"
    if packet.get("answer_mode") != "ollama_grounded":
        return "REVIEW_REQUIRED"
    return "READY_FOR_HUMAN"


def run_assessment(
    question: str,
    proposed_action: str,
    trusted_domains: list[str],
    max_results: int,
) -> dict:
    search_query = question if not proposed_action else f"{question} {proposed_action}"
    payload = search(search_query, config=SearchConfig(num=max_results))
    items = normalize_serpapi_results(
        payload, trusted_domains=trusted_domains, max_results=max_results
    )
    packet = assess_evidence(question, items)
    packet["proposed_action"] = proposed_action
    try:
        ai_answer = synthesize_decision_with_ollama(question, proposed_action, packet)
    except AIProviderError as exc:
        ai_answer = None
        packet["flags"].append("LOCAL_AI_SYNTHESIS_FAILED")
        packet["ai_error"] = str(exc)

    packet["answer_mode"] = "ollama_grounded" if ai_answer else "deterministic_evidence_digest"
    packet["decision_brief"] = ai_answer or deterministic_digest(question, items, packet["flags"])
    packet["serpapi_integration"] = "live" if not os.getenv("EVIDENCE_SCOUT_FIXTURE") else "fixture_test_only"
    packet["gate_state"] = _gate_state(packet)
    packet["authority_boundary"] = "AI_RECOMMENDS_HUMAN_DECIDES_NO_ACTION_EXECUTED"

    packet_identity = {
        "retrieved_at_utc": packet.get("retrieved_at_utc"),
        "question": question,
        "proposed_action": proposed_action,
        "evidence": packet.get("evidence") or [],
        "decision_brief": packet.get("decision_brief"),
        "gate_state": packet.get("gate_state"),
    }
    packet_id = _stable_hash(packet_identity)
    packet["packet_id"] = packet_id
    PACKETS[packet_id] = packet
    return packet


def record_human_decision(packet_id: str, decision: str, note: str = "") -> dict:
    decision = decision.strip().upper()
    if packet_id not in PACKETS:
        raise KeyError("Unknown packet_id")
    if decision not in {"APPROVE", "HOLD", "REJECT"}:
        raise ValueError("decision must be APPROVE, HOLD, or REJECT")
    packet = PACKETS[packet_id]
    if decision == "APPROVE" and packet.get("gate_state") != "READY_FOR_HUMAN":
        raise PermissionError("APPROVE is fail-closed until gate_state=READY_FOR_HUMAN")

    receipt_body = {
        "packet_id": packet_id,
        "human_decision": decision,
        "human_note": note.strip(),
        "decided_at_utc": _utc_now(),
        "action_executed": False,
        "authority_boundary": "HUMAN_DECISION_RECORDED_ONLY",
    }
    receipt = dict(receipt_body)
    receipt["receipt_id"] = _stable_hash(receipt_body)
    return receipt


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        relative = parsed.path.lstrip("/") or "index.html"
        return str(STATIC / relative)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "serpapi_key_present": bool(os.getenv("SERPAPI_API_KEY")),
                    "ollama_configured": bool(os.getenv("OLLAMA_URL") and os.getenv("OLLAMA_MODEL")),
                    "fixture_mode": bool(os.getenv("EVIDENCE_SCOUT_FIXTURE")),
                    "product": "Diamond Evidence Gate",
                },
            )
            return
        if parsed.path == "/api/assess":
            params = parse_qs(parsed.query)
            question = (params.get("q") or [""])[0].strip()
            proposed_action = (params.get("action") or [""])[0].strip()
            domains_raw = (params.get("domains") or [""])[0]
            trusted_domains = [x.strip() for x in domains_raw.split(",") if x.strip()]
            try:
                max_results = int((params.get("max") or ["5"])[0])
            except ValueError:
                max_results = 5
            if not question:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Missing q parameter"})
                return
            try:
                result = run_assessment(question, proposed_action, trusted_domains, max_results)
            except SerpApiError as exc:
                self._json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": str(exc), "integration_state": "BLOCKED_EXTERNAL_CREDENTIAL_OR_NETWORK"},
                )
                return
            self._json(HTTPStatus.OK, result)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/decision":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            receipt = record_human_decision(
                str(payload.get("packet_id") or ""),
                str(payload.get("decision") or ""),
                str(payload.get("note") or ""),
            )
        except KeyError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except PermissionError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc), "gate_state": "REVIEW_REQUIRED"})
            return
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, receipt)

    def log_message(self, fmt: str, *args) -> None:
        print("[diamond-evidence-gate] " + (fmt % args))


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Diamond Evidence Gate running at http://{host}:{port}")
    print("Health: /health | Assessment: /api/assess?q=...&action=...")
    server.serve_forever()


if __name__ == "__main__":
    main()

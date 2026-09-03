from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class PointBTests(unittest.TestCase):
    def setUp(self) -> None:
        app.PACKETS.clear()

    def _fixture_path(self) -> str:
        return str(Path(__file__).resolve().parents[1] / "fixtures" / "serpapi_sample.json")

    def test_fixture_assessment_builds_packet(self) -> None:
        with patch.dict(os.environ, {"EVIDENCE_SCOUT_FIXTURE": self._fixture_path()}, clear=False), patch(
            "app.synthesize_decision_with_ollama",
            return_value="RECOMMENDATION: HOLD\nRATIONALE: verify [1] and [2]\nUNCERTAINTIES: rollout impact\nNEXT CHECK: official release note",
        ):
            packet = app.run_assessment(
                "Should we enable the new platform capability?",
                "Enable it for one bounded workload.",
                [],
                5,
            )
        self.assertEqual(packet["result_count"], 3)
        self.assertEqual(packet["unique_domain_count"], 3)
        self.assertEqual(packet["answer_mode"], "ollama_grounded")
        self.assertEqual(packet["gate_state"], "READY_FOR_HUMAN")
        self.assertTrue(packet["packet_id"])
        self.assertIn(packet["packet_id"], app.PACKETS)

    def test_human_decision_receipt_never_executes_action(self) -> None:
        app.PACKETS["p"] = {"gate_state": "READY_FOR_HUMAN"}
        receipt = app.record_human_decision("p", "APPROVE", "bounded rollout")
        self.assertEqual(receipt["human_decision"], "APPROVE")
        self.assertFalse(receipt["action_executed"])
        self.assertEqual(receipt["authority_boundary"], "HUMAN_DECISION_RECORDED_ONLY")
        self.assertTrue(receipt["receipt_id"])

    def test_approve_fails_closed_when_evidence_not_ready(self) -> None:
        app.PACKETS["p"] = {"gate_state": "REVIEW_REQUIRED"}
        with self.assertRaises(PermissionError):
            app.record_human_decision("p", "APPROVE")
        # HOLD and REJECT remain valid Human decisions even when evidence is weak.
        self.assertEqual(app.record_human_decision("p", "HOLD")["human_decision"], "HOLD")
        self.assertEqual(app.record_human_decision("p", "REJECT")["human_decision"], "REJECT")

    def test_invalid_decision_rejected(self) -> None:
        app.PACKETS["p"] = {"gate_state": "READY_FOR_HUMAN"}
        with self.assertRaises(ValueError):
            app.record_human_decision("p", "AUTO_APPROVE")

    def test_local_ai_failure_keeps_gate_review_only(self) -> None:
        with patch.dict(os.environ, {"EVIDENCE_SCOUT_FIXTURE": self._fixture_path()}, clear=False), patch(
            "app.synthesize_decision_with_ollama",
            side_effect=app.AIProviderError("synthetic failure"),
        ):
            packet = app.run_assessment("Current platform risk?", "Deploy now", [], 5)
        self.assertEqual(packet["answer_mode"], "deterministic_evidence_digest")
        self.assertEqual(packet["gate_state"], "REVIEW_REQUIRED")
        self.assertIn("LOCAL_AI_SYNTHESIS_FAILED", packet["flags"])

    def test_ui_contains_visible_human_gate_and_max5(self) -> None:
        html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
        for token in ["Human Gate", "Approve", "Hold", "Reject", "/api/decision", "&max=5", "Gate: ${data.gate_state}"]:
            self.assertIn(token, html)

    def test_no_auto_execution_surface_in_app(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertIn('"action_executed": False', source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)


if __name__ == "__main__":
    unittest.main()

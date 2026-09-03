from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.evidence_engine import assess_evidence, normalize_serpapi_results
from src.serpapi_client import SearchConfig, build_search_url


class SearchCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "serpapi_sample.json").read_text(encoding="utf-8"))

    def test_normalize_fixture(self) -> None:
        items = normalize_serpapi_results(self.fixture, max_results=5)
        self.assertEqual(len(items), 3)
        packet = assess_evidence("latest platform update", items)
        self.assertEqual(packet["unique_domain_count"], 3)
        self.assertNotIn("LOW_SOURCE_DIVERSITY", packet["flags"])

    def test_search_url_does_not_drop_query(self) -> None:
        url = build_search_url("live platform risk", "redacted-key", SearchConfig(num=5))
        self.assertIn("q=live+platform+risk", url)
        self.assertIn("num=5", url)
        self.assertIn("output=json", url)


if __name__ == "__main__":
    unittest.main()

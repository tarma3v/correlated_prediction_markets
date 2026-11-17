import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
from collect_public import acquire, normalize_kalshi, normalize_polymarket


class NormalizationTests(unittest.TestCase):
    def test_polymarket_keeps_verified_ids_and_text_only(self):
        event = {"id": "12", "title": "Core CPI", "description": "Event rules"}
        market = {"id": "34", "conditionId": "0xabc", "question": "Above 1?",
                  "description": "Rules", "outcomes": '["Yes", "No"]',
                  "outcomePrices": '["0.9", "0.1"]', "volume": 100, "winner": "Yes"}
        result = normalize_polymarket(event, market, {"raw_file": "raw/p.json"})
        self.assertEqual(result["id"], "34")
        self.assertEqual(result["condition_id"], "0xabc")
        self.assertEqual(result["event_id"], "12")
        self.assertEqual(result["outcomes"], ["Yes", "No"])
        self.assertFalse({"outcomePrices", "volume", "winner"} & result.keys())
        self.assertFalse(result["governing_rules_certified"])

    def test_no_invented_market_id(self):
        with self.assertRaises(ValueError):
            normalize_polymarket({"id": "1"}, {"question": "Q"}, {})

    def test_kalshi_prices_and_results_excluded(self):
        result = normalize_kalshi({"ticker": "KX-26-T1", "event_ticker": "KX-26",
                                  "rules_primary": "Rule", "yes_bid": 50, "result": "yes"}, {})
        self.assertEqual(result["primary"], "Rule")
        self.assertNotIn("result", result)
        self.assertNotIn("yes_bid", result)

    def test_malformed_response_is_preserved_for_audit(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status, response.headers = 200, {}
        response.read.return_value = b"invalid JSON response"
        with tempfile.TemporaryDirectory() as folder, patch("collect_public.urlopen", return_value=response), redirect_stdout(StringIO()):
            output = Path(folder) / "snapshot"
            self.assertEqual(acquire(output, "12", "CORE"), 1)
            self.assertEqual((output / "raw/polymarket_event.json").read_bytes(), b"invalid JSON response")


if __name__ == "__main__":
    unittest.main()

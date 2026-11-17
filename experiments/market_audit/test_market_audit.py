"""Checks for contract payoffs, signed quote sides, depth and Brier chronology."""
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import audit


class MarketTests(unittest.TestCase):
    def test_payoff_on_both_sides_of_boundary(self):
        for strike in range(-1, 7):
            for actual in range(-2, 9):
                for kind, expected in [('eq', actual == strike), ('le', actual <= strike), ('ge', actual >= strike)]:
                    cash, legs = audit.cond_coeffs(kind, strike)
                    self.assertEqual(cash + sum(w * (actual > k) for k, w in legs.items()), expected)

    def test_sell_and_buy_portfolio_use_opposite_sides(self):
        quotes = {1: dict(bid=.55, ask=.6, valid_bid=True, valid_ask=True),
                  2: dict(bid=.15, ask=.2, valid_bid=True, valid_ask=True)}
        bid, ask = audit.interval(quotes, 0, {1: 1, 2: -1})
        self.assertAlmostEqual(bid, .35)
        self.assertAlmostEqual(ask, .45)
        quotes[2]['valid_ask'] = False
        self.assertIsNone(audit.interval(quotes, 0, {1: 1, 2: -1})[0])

    def test_missing_size_suppresses_side(self):
        q = audit.quote({'yes_bid_dollars': '.4', 'yes_bid_size_fp': '0', 'yes_ask_dollars': '.5',
                         'yes_ask_size_fp': '4'}, 'kalshi')
        self.assertFalse(q['valid_bid'])
        self.assertTrue(q['valid_ask'])
        self.assertIsNone(q['mid'])

    def test_replay_with_archived_sources(self):
        with tempfile.TemporaryDirectory() as path, redirect_stdout(io.StringIO()):
            output = Path(path)
            audit.main(output)
            summary = json.loads((output / 'summary.json').read_text())
            self.assertEqual(summary['settlements']['mapped_mismatch'], 0)
            with (output / 'september_forward_scores.csv').open() as f:
                scores = list(csv.DictReader(f))
            self.assertEqual(sum(bool(row['brier']) for row in scores), 6)
            for row in scores:
                self.assertLess(audit.parse_time(row['captured_utc']), audit.parse_time(row['closed_utc']))
                self.assertLessEqual(audit.parse_time(row['closed_utc']), audit.parse_time(row['settled_utc']))


if __name__ == '__main__':
    unittest.main()

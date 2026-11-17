"""Regression checks for calendar-day alignment, chronology and paired scoring."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import run


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.date_range('2025-01-01', periods=100)
        rng = np.random.default_rng(23)
        self.prices = pd.DataFrame(rng.uniform(.2, .8, (100, 2)), index=self.dates,
                                   columns=['kalshi', 'polymarket'])

    def test_delayed_features_and_next_calendar_day(self):
        for delay in (0, 1, 7):
            row = run.build_examples(self.prices, 'kalshi', delay).loc[self.dates[40]]
            self.assertAlmostEqual(row.gap + row.own, self.prices.polymarket.iloc[40 - delay])
            self.assertAlmostEqual(row.source_change, self.prices.polymarket.diff().iloc[40 - delay])
            self.assertEqual(row.actual, self.prices.kalshi.iloc[41])
            self.assertEqual(row.target_date, self.dates[41])
        self.prices.loc[self.dates[41], 'kalshi'] = np.nan
        rows = run.build_examples(self.prices, 'kalshi', 0)
        self.assertNotIn(self.dates[40], rows.index)
        self.assertNotIn(self.dates[42], rows.index)

    def test_future_prices_cannot_change_earlier_predictions(self):
        modified = self.prices.copy()
        modified.loc[self.dates[63]:] = 1 - modified.loc[self.dates[63]:]
        with patch.object(run, 'PLACEBOS', 1):
            results, _, sizes = run.evaluate('senate', 'X', self.prices, 'kalshi', np.random.default_rng(1))
            changed, _, _ = run.evaluate('senate', 'X', modified, 'kalshi', np.random.default_rng(1))
        models = ['persist','own_only','cross_change','cross_full']
        pd.testing.assert_frame_equal(results.loc[results.index < self.dates[63], models],
                                      changed.loc[changed.index < self.dates[63], models])
        for fold in sizes:
            self.assertLessEqual(fold['last_train_label'], fold['first_test_origin'])
        comparable = results[results.delay == 0]
        self.assertTrue(comparable.target_date.is_unique)
        self.assertEqual(len(comparable), len(self.prices) // 2)

    def test_paired_bootstrap_in_percentage_points(self):
        panel = pd.DataFrame({'actual': 0.4, 'own_only': 0.6, 'persist': 0.45, 'cross_full': 0.5,
                              'target_date': self.dates})
        limits = run.block_interval(panel, np.random.default_rng(1))
        np.testing.assert_allclose(limits, [[10, -5], [10, -5]])


if __name__ == '__main__':
    unittest.main()

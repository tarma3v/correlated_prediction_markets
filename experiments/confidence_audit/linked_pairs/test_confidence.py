"""Independent checks of threshold calibration, competitor scores and exclusions."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from run import HERE, ROOT, best_other, competitors, cutoff, held_out_thresholds, run


class LinkedConfidenceTests(unittest.TestCase):
    def test_self_excluded_even_with_ties(self):
        scores = np.array([[.1, .7, .7], [.9, .5, .1]])
        best = competitors(scores)
        self.assertEqual(best_other(best[0], .7), .7)
        self.assertEqual(best_other(best[1], .9), .5)
        self.assertEqual(best_other(best[1], .1), .9)

    def test_highest_observed_cutoff_retains_required_number(self):
        for n in range(1, 30):
            values = [i//2 for i in range(n)]
            t = cutoff(values)
            self.assertGreaterEqual(sum(x >= t for x in values)*10, 9*n)
            self.assertLess(sum(x > t for x in values)*10, 9*n)

    def test_heldout_labels_and_negative_scores_cannot_change_own_cutoff(self):
        samples = [dict(family=f, label="same", cosine=v, margin=v)
                   for f, v in [("a", .9), ("b", .6), ("c", .5)]]
        old = held_out_thresholds(samples)["a"]
        changed = [{**samples[0], "label": "different"}, *samples[1:],
                   dict(family="b", label="different", cosine=987, margin=999)]
        self.assertEqual(held_out_thresholds(changed)["a"], old)
        self.assertEqual(old["calibration_components"], 2)

    def test_bruteforce_exclusion_scores_and_calibration(self):
        d = ROOT / "comparison/retrieval"
        ids = json.loads((d/"embedding_row_ids.json").read_bytes())
        with (HERE/"predictions.csv").open() as f:
            rows = list(csv.DictReader(f))
        for model in {r["model"] for r in rows}:
            subset = [r for r in rows if r["model"] == model]
            m = np.load(d/f"{model}_event_title_scores.npy", allow_pickle=False)
            for row in subset:
                p, k = ids["poly"].index(row["poly_id"]), ids["kalshi"].index(row["kalshi_ticker"])
                other = max(max(np.delete(m[p], k)), max(np.delete(m[:, k], p)))
                self.assertEqual(float(row["margin"]), float(m[p, k])-float(other))
                others = [r for r in subset if r["family"] != row["family"] and r["label"] == "same"]
                self.assertEqual(len(others), int(row["calibration_pairs"]))
                for metric in ("margin", "cosine"):
                    threshold = float(row["threshold_" + metric])
                    self.assertGreaterEqual(sum(float(o[metric]) >= threshold for o in others)*10, 9*len(others))
                    self.assertLess(sum(float(o[metric]) > threshold for o in others)*10, 9*len(others))
                    self.assertEqual(bool(int(row["accepted_" + metric])), float(row[metric]) >= threshold)

    def test_byte_exact_replay(self):
        with TemporaryDirectory() as folder:
            dest = Path(folder)
            run(dest)
            for name in ("results.json", "predictions.csv"):
                self.assertEqual((dest/name).read_bytes(), (HERE/name).read_bytes())


if __name__ == "__main__":
    unittest.main()

"""Controls for ties, family weighting, candidate restriction, and frozen results."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from run import HERE, competition_groups, family_means, run, top_one


class EventCompetitionTests(unittest.TestCase):
    def test_ties_are_uniform_and_target_order_independent(self):
        scores = np.array([3, 4, 3])
        self.assertEqual(top_one(scores, 0, [2, 0]), 0.5)
        self.assertEqual(top_one(scores, 2, [0, 2]), 0.5)
        self.assertEqual(top_one(scores, 0, [0, 1, 2]), 0.0)
        self.assertEqual(top_one(scores, 2, [2]), 1.0)

    def test_groups_do_not_read_labels_or_contract_ids(self):
        groups = competition_groups([{"event_title": "X "}, {"event_title": "Y"}, {"event_title": "x"}])
        self.assertEqual(groups, {0: [0, 2], 1: [1], 2: [0, 2]})

    def test_families_average_links_before_directions(self):
        rows = [dict(family="a", poly_id=p, kalshi_ticker=p, hit=h)
                for p, h in [("one", 0), ("two", 1), ("two", 0)]]
        rows.append(dict(family="b", poly_id="three", kalshi_ticker="three", hit=1))
        self.assertEqual(family_means(rows, "hit"), [0.25, 1])

    def test_scored_records_agree_with_independent_block_sort(self):
        # Check every direction against independently grouped IDs and tied maxima.
        base = HERE.parents[2]
        inputs = base / "comparison/retrieval"
        ids = json.loads((inputs/"embedding_row_ids.json").read_bytes())
        markets = json.loads((base/"redesign/retrieval/markets.json").read_bytes())
        events = {v: [r["event_title"].casefold().strip() for r in markets[v]] for v in ids}
        with (HERE/"directions.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1844)
        for model in {r["model"] for r in rows}:
            selected = [r for r in rows if r["model"] == model]
            for view in ("title", "event_title"):
                scores = np.load(inputs/f"{model}_{view}_scores.npy", allow_pickle=False)
                for row in selected:
                    p, k = ids["poly"].index(row["poly_id"]), ids["kalshi"].index(row["kalshi_ticker"])
                    venue = row["target_venue"]
                    target, values = (p, scores[:, k]) if venue == "poly" else (k, scores[p])
                    pool = [i for i, e in enumerate(events[venue]) if e == events[venue][target]]
                    self.assertEqual(len(pool), int(row["pool_size"]))
                    for field, indices in [("global", range(len(values))), ("within", pool)]:
                        best = max(values[i] for i in indices)
                        winners = {i for i in indices if values[i] == best}
                        expected = int(target in winners)/len(winners)
                        self.assertEqual(float(row[field + "_" + view]), expected)

    def test_byte_exact_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            run(out)
            for name in ("results.json", "directions.csv"):
                self.assertEqual((out/name).read_bytes(), (HERE/name).read_bytes())


if __name__ == "__main__":
    unittest.main()

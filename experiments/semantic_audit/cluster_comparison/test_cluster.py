import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from run import HERE, clusters, evaluate, main, union_order


class ClusterTests(unittest.TestCase):
    def test_union_and_equal_budgets(self):
        self.assertEqual(union_order([0,1,2], [1,0,2]), [0,1,2])
        ranking = [([0,1,2], [1,0,2], [0,1,2])]*2
        keys = {0: {0}, 1: {1}}
        result = evaluate(ranking, keys, np.array([0,2]), np.array([1,0,0]), 5)
        self.assertEqual(result["budget_per_method"], 2)
        self.assertEqual(result["empty_queries"], 1)
        self.assertEqual(result["hits_cluster"], 0)
        self.assertEqual(result["hits_union"], 1)
        self.assertEqual(result["hits_union_full_budget"], 2)

    def test_cluster_geometry(self):
        x = np.array([[1.,0.], [1.,0.], [0.,1.], [0.,1.]])
        for seed in (17,29,53):
            a,b,c,d = clusters(x, 2, seed)
            self.assertTrue(a == b and c == d and a != c)

    def test_consistency_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            main(path)
            for f in ("results.csv", "manifest.json"):
                self.assertEqual((HERE/f).read_bytes(), (path/f).read_bytes())
        with (HERE/"results.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 90)
        for r in rows:
            budget = int(r["budget_per_method"])
            self.assertLessEqual(int(r["hits_cluster"])+int(r["known_outside_cluster"]),int(r["possible_hits"]))
            for channel in ("union", "cluster", "first", "second"):
                self.assertLessEqual(int(r["hits_"+channel]), budget)
            self.assertLessEqual(budget, int(r["k"])*int(r["queries"]))


if __name__ == "__main__":
    unittest.main()

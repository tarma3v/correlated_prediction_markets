"""Read-only verification of frozen inputs, ranks, chunk coverage and blind queue."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import unittest

import numpy as np

from reproduce import HERE, ROOT, canonical, chunk_ids, rank_rows, sha


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


class PipelineBoundaryTests(unittest.TestCase):
    def test_no_loss_at_chunk_boundaries(self):
        for length in [0, 1, 253, 254, 255, 508, 509, 2000]:
            tokens = list(range(length))
            chunks = chunk_ids(tokens, 254)
            self.assertEqual([token for chunk in chunks for token in chunk], tokens)
            self.assertTrue(all(len(chunk) <= 254 for chunk in chunks))

    def test_eligibility_precedes_topk_and_ties_are_stable(self):
        records = [{"id": "a", "event_id": "same"}, {"id": "b", "event_id": "same"}, {"id": "c", "event_id": "other"}, {"id": "d", "event_id": "third"}]
        scores = np.array([[1, .99, .2, .2], [.99, 1, .1, .1], [.2, .1, 1, .3], [.2, .1, .3, 1]])
        rows = rank_rows(scores, records, k=2)
        self.assertEqual([x["id"] for x in rows[0]["top"]], ["c", "d"])
        self.assertEqual(rows[0]["eligible_candidate_count"], 2)


def verify_artifacts():
    lock = json.loads((HERE / "input_lock.json").read_text())
    for name, spec in lock["input_files"].items():
        assert sha((ROOT / name).read_bytes()) == spec["sha256"], name
    corpus = jsonl(HERE / "corpus.jsonl")
    assert len(corpus) == 323 and len({x["id"] for x in corpus}) == 323
    assert {x["venue"] for x in corpus} == {"kalshi"}
    assert sha(canonical(corpus)) == lock["corpus_records_sha256"]
    by_id = {x["id"]: x for x in corpus}
    for row in corpus:
        expected = row["input_sha256"]
        assert sha(canonical({k: v for k, v in row.items() if k != "input_sha256"})) == expected
        raw = json.loads((ROOT / row["provenance"]["raw_file"]).read_text())
        prefix = "response." if "response" in raw else ""
        data = raw.get("response", raw)
        source = next(x for x in data.get("markets", [data.get("market")]) if x and x["ticker"] == row["id"])
        locator = prefix + ("market" if "market" in data else "markets[ticker=" + row["id"] + "]")
        assert row["provenance"]["raw_locator"] == locator
        for field, source_field in [("title", "title"), ("subtitle", "yes_sub_title"), ("primary", "rules_primary"), ("secondary", "rules_secondary"), ("event_id", "event_ticker")]:
            assert row[field] == (source.get(source_field, "") or ""), (row["id"], field)
    run = json.loads((HERE / "run_manifest.json").read_text())
    assert run["script_sha256"] == sha((HERE / "reproduce.py").read_bytes())
    assert run["input_lock_sha256"] == sha((HERE / "input_lock.json").read_bytes())
    for name, spec in run["output_files"].items():
        assert sha((HERE / name).read_bytes()) == spec["sha256"], name
    scores = np.load(HERE / "scores.npz")
    ids = scores["ids"].tolist()
    assert ids == [x["id"] for x in corpus]
    saved = jsonl(HERE / "ranks.jsonl")
    assert len(saved) == 4 * 323
    for arm in ["minilm_title", "minilm_context", "tfidf_title", "tfidf_context"]:
        matrix = scores[arm]
        assert matrix.shape == (323, 323) and np.isfinite(matrix).all()
        assert np.allclose(matrix, matrix.T, atol=1e-6)
        expected = rank_rows(matrix, corpus)
        actual = [{k: v for k, v in x.items() if k != "arm"} for x in saved if x["arm"] == arm]
        assert expected == actual, arm
    embeddings = np.load(HERE / "minilm_embeddings.npz")
    for view in ["title", "context"]:
        assert np.allclose(np.linalg.norm(embeddings[view], axis=1), 1, atol=1e-6)
        assert np.allclose(embeddings[view] @ embeddings[view].T, scores["minilm_" + view], atol=1e-6)
    enc = json.loads((HERE / "encoding_metadata.json").read_text())
    for rows in enc.values():
        assert len(rows) == 323
        assert all(x["discarded_content_tokens"] == 0 and x["content_tokens"] == x["covered_content_tokens"] for x in rows)
    queue = jsonl(HERE / "blind_queue.jsonl")
    assert len(queue) == 40
    pairs, event_pairs, event_counts = set(), set(), Counter()
    for row in queue:
        assert set(row) == {"pair_id", "A", "B", "annotation"}
        a, b = row["A"], row["B"]
        assert a == by_id[a["id"]] and b == by_id[b["id"]]
        assert a["event_id"] != b["event_id"]
        pair = tuple(sorted([a["id"], b["id"]]))
        assert pair not in pairs
        pairs.add(pair)
        event_pair = tuple(sorted([a["event_id"], b["event_id"]]))
        assert event_pair not in event_pairs
        event_pairs.add(event_pair)
        event_counts.update(event_pair)
        ann = row["annotation"]
        assert all(v is None for k, v in ann.items() if k != "state_assessment")
        assert all(v is None for state in ann["state_assessment"].values() for v in state.values())
    assert max(event_counts.values()) <= 6
    poly = jsonl(HERE / "polymarket_text_inventory.jsonl")
    assert len(poly) == 5 and sha(canonical(poly)) == lock["polymarket_inventory_sha256"]
    assert all(x["external_market_id"] is None and x["condition_id"] is None for x in poly)
    assert not any(x["venue"] == "polymarket" for x in corpus)
    forbidden = {"score", "rrf", "rank", "arm", "label", "gold", "relation_candidate", "old_label", "previous_prediction", "last_price", "volume", "open_interest"}
    def walk(value):
        if isinstance(value, dict):
            assert not (set(value) & forbidden), set(value) & forbidden
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(queue)
    for name in ["reproduce.py", "verify.py", "README.md", "input_lock.json", *run["output_files"]]:
        if name.endswith((".json", ".jsonl", ".py", ".md")):
            text = (HERE / name).read_text()
            assert ("/" + "Users" + "/") not in text, name
            assert "\u2014" not in text, name
    print(json.dumps({"passed": True, "corpus": 323, "ranks_recomputed_from_scores": 1292, "blind_pairs": 40, "unique_event_pairs": 40, "dropped_content_tokens": 0, "polymarket_inventory_excluded": 5}))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PipelineBoundaryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    verify_artifacts()

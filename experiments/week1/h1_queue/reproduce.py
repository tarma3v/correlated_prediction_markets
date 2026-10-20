"""Offline, single-venue acquisition/annotation diagnostic; not H1 validation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REV = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_DIR = ROOT / "tmp/hf_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots" / MODEL_REV
TOP_K = 5
QUEUE_SIZE = 40
MAX_PAIR_PER_EVENT_PAIR = 1
MAX_PAIRS_PER_EVENT = 6
SEED = 20261021
MAX_LENGTH = 256
INPUTS = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def read(relative):
    p = ROOT / relative
    content = p.read_bytes()
    INPUTS[relative] = {"sha256": sha(content), "bytes": len(content)}
    return json.loads(content)


def write_json(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(p, rows):
    p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))


def verified_file(relative, expected):
    data = (ROOT / relative).read_bytes()
    digest = sha(data)
    if digest != expected:
        raise ValueError(f"Source digest differs: {relative}")
    INPUTS[relative] = {"sha256": digest, "bytes": len(data)}


def make_record(x, provenance, normalized=False):
    record = {
        "venue": "kalshi",
        "id": x["id" if normalized else "ticker"],
        "event_id": x["event_id" if normalized else "event_ticker"],
        "title": x.get("title", ""),
        "subtitle": x.get("subtitle" if normalized else "yes_sub_title", "") or "",
        "primary": x.get("primary" if normalized else "rules_primary", "") or "",
        "secondary": x.get("secondary" if normalized else "rules_secondary", "") or "",
        "provenance": provenance,
        "coverage": "Official market API fields only; full governing terms and historical version not certified.",
    }
    record["input_sha256"] = sha(canonical(record))
    return record


def build_corpus():
    manifest = read("pilot/manifest.json")
    verified_file("pilot/markets.json", manifest["markets_sha256"])
    pilot = read("pilot/markets.json")
    req = {x["file"]: x for x in manifest["requests"] if x.get("status_code") == 200}
    records = {}
    for x in pilot:
        source = req[x["raw_file"]]
        raw = "pilot/" + x["raw_file"]
        verified_file(raw, source["sha256"])
        records[x["id"]] = make_record(x, {
            "raw_file": raw, "raw_sha256": source["sha256"],
            "raw_locator": "response.markets[ticker=" + x["id"] + "]",
            "request_url": source["request_url"],
            "market_url": x["source_api_url"],
            "fetched_at_utc": source["fetched_at_utc"],
            "kind": "official_live_api",
        }, normalized=True)
    probe = "redesign/discovery/official_probe/"
    requests = read(probe + "kalshi_market_manifest.json")["requests"]
    requests += read(probe + "gaming_manifest.json")
    requests += [read(probe + "gta_historical_manifest.json")]
    allowed = {
        "markets_KXFEDHIKE.json", "markets_KXNBERRECESSQ.json",
        "markets_KXRATEHIKE.json", "markets_KXRECSSNBER.json",
        "markets_KXU3MAX.json", "gta_online.json", "gta_historical_response.json",
    }
    selected_requests = [(probe, x) for x in requests if x.get("file") in allowed and x.get("status_code") == 200]
    political = "redesign/discovery/political/"
    selected_requests += [(political, x) for x in read(political + "manifest.json") if x.get("file") == "kalshi_out.json" and x.get("status") == 200]
    duplicate_ids = []
    for base, source in selected_requests:
        relative = base + source["file"]
        verified_file(relative, source["sha256"])
        data = read(relative)
        for x in data.get("markets", [data.get("market")]):
            if not x:
                continue
            if x["ticker"] in records:
                duplicate_ids.append(x["ticker"])
                continue
            records[x["ticker"]] = make_record(x, {
                "raw_file": relative, "raw_sha256": source["sha256"],
                "raw_locator": "market" if "market" in data else "markets[ticker=" + x["ticker"] + "]",
                "request_url": source["url"],
                "market_url": source["url"] if "historical" in source["url"] else "https://external-api.kalshi.com/trade-api/v2/markets/" + x["ticker"],
                "fetched_at_utc": source["fetched_at_utc"],
                "kind": "official_historical_api" if "historical" in source["url"] else "official_live_api",
            })
    if len(records) != 323:
        raise ValueError(f"Expected frozen 323 records, got {len(records)}")
    return [records[k] for k in sorted(records)], duplicate_ids


def polymarket_inventory():
    base = "redesign/discovery/official_probe/"
    source = read(base + "polymarket_rule_sources.json")
    manifest = read(base + "packet_manifest.json")
    result = []
    for row in source:
        raw = base + row["raw_file"]
        verified_file(raw, manifest["sha256"][row["raw_file"]])
        result.append({
            "local_record_id": row["id"],
            "venue": "polymarket", "external_market_id": None, "condition_id": None,
            "source_url": row["url"], "source_kind": row["source_kind"],
            "observed_outcome_label": row.get("outcome_label"),
            "observed_outcome_labels": row.get("outcome_labels"),
            "rules_text": row["rules"],
            "stored_text_locator": base + "polymarket_rule_sources.json#id=" + row["id"],
            "stored_text_sha256": sha(row["rules"].encode()),
            "raw_file": raw, "raw_sha256": INPUTS[raw]["sha256"],
            "snapshot_recorded_at_utc": row["snapshot_recorded_at_utc"],
            "crawled_as_reported": row.get("crawled_as_reported"),
            "limitations": "Stored rule text from official-page web index/render, not a direct API response. May be stale; exact venue-issued ID not verified. No inference or relation label included. Excluded from retrieval corpus and counts.",
        })
    return result


def text_view(row, view):
    if view == "title":
        return row["title"]
    return "\n".join(row[x] for x in ["title", "subtitle", "primary", "secondary"] if row[x])


def chunk_ids(ids, payload):
    return [ids[i:i + payload] for i in range(0, len(ids), payload)] or [[]]


def dense_encode(texts, ids, tokenizer, model):
    import numpy as np
    import torch
    metadata, chunks, owners, weights = [], [], [], []
    payload = MAX_LENGTH - tokenizer.num_special_tokens_to_add(pair=False)
    for i, text in enumerate(texts):
        tokens = tokenizer.encode(text, add_special_tokens=False, truncation=False)
        pieces = chunk_ids(tokens, payload)
        if sum(map(len, pieces)) != len(tokens):
            raise AssertionError("Token dropped by chunking")
        metadata.append({"id": ids[i], "content_tokens": len(tokens), "chunks": len(pieces), "covered_content_tokens": sum(map(len, pieces)), "discarded_content_tokens": 0})
        for piece in pieces:
            chunks.append(tokenizer.prepare_for_model(piece, add_special_tokens=True, truncation=False, return_attention_mask=True))
            owners.append(i)
            weights.append(max(1, len(piece)))
    sums = np.zeros((len(texts), model.config.hidden_size), dtype=np.float64)
    totals = np.zeros(len(texts), dtype=np.float64)
    for offset in range(0, len(chunks), 32):
        batch = tokenizer.pad(chunks[offset:offset + 32], padding=True, return_tensors="pt")
        if batch["input_ids"].shape[1] > MAX_LENGTH:
            raise AssertionError("Chunk exceeds configured maximum")
        with torch.inference_mode():
            h = model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).to(h.dtype)
            vec = ((h * mask).sum(1) / mask.sum(1).clamp_min(1)).cpu().numpy()
        for j, value in enumerate(vec, start=offset):
            sums[owners[j]] += value * weights[j]
            totals[owners[j]] += weights[j]
    means = sums / totals[:, None]
    means /= np.maximum(np.linalg.norm(means, axis=1, keepdims=True), 1e-12)
    return means.astype(np.float32), metadata


def lexical_scores(texts):
    import numpy as np
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize
    word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, dtype=np.float32).fit_transform(texts)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, dtype=np.float32).fit_transform(texts)
    matrix = normalize(hstack([word, char]), norm="l2")
    return (matrix @ matrix.T).toarray().astype(np.float32), {"word_features": word.shape[1], "char_features": char.shape[1]}


def rank_rows(scores, records, k=TOP_K):
    import numpy as np
    events = np.array([x["event_id"] for x in records])
    result = []
    for i, row in enumerate(records):
        eligible = np.flatnonzero(events != row["event_id"])
        order = eligible[np.argsort(-scores[i, eligible], kind="stable")[:k]]
        result.append({"query_id": row["id"], "eligible_candidate_count": len(eligible), "top": [{"id": records[int(j)]["id"], "rank": rank, "score": float(scores[i, j])} for rank, j in enumerate(order, 1)]})
    return result


def choose_queue(ranks, records):
    by_id = {x["id"]: x for x in records}
    candidates = defaultdict(lambda: {"rrf": 0.0, "retrievals": []})
    for arm, rows in sorted(ranks.items()):
        for row in rows:
            for hit in row["top"]:
                pair = tuple(sorted((row["query_id"], hit["id"])))
                candidates[pair]["rrf"] += 1 / (60 + hit["rank"])
                candidates[pair]["retrievals"].append({"arm": arm, "query_id": row["query_id"], "rank": hit["rank"], "score": hit["score"]})
    groups = defaultdict(list)
    for pair, value in candidates.items():
        key = tuple(sorted(by_id[x]["event_id"] for x in pair))
        groups[key].append((pair, value))
    for key in groups:
        groups[key].sort(key=lambda x: (-x[1]["rrf"], x[0]))
    selected, event_counts = [], Counter()
    # Fixed round-robin over events by SHA order, not their number of thresholds.
    event_order = sorted({x["event_id"] for x in records}, key=lambda x: sha(f"{SEED}:{x}".encode()))
    used_groups, used_pairs = set(), set()
    while len(selected) < QUEUE_SIZE:
        changed = False
        for event in event_order:
            options = []
            for key, values in groups.items():
                if event not in key or key in used_groups or any(event_counts[e] >= MAX_PAIRS_PER_EVENT for e in key):
                    continue
                pair, value = values[0]
                if pair not in used_pairs:
                    options.append((pair, value, key))
            if not options:
                continue
            pair, value, key = min(options, key=lambda x: (-x[1]["rrf"], x[0]))
            selected.append((pair, value, key))
            used_pairs.add(pair)
            used_groups.add(key)
            event_counts.update(key)
            changed = True
            if len(selected) == QUEUE_SIZE:
                break
        if not changed:
            raise ValueError("Frozen diversity policy cannot fill queue; do not silently relax")
    # Blind order independent of rank; A/B orientation fixed by hash parity.
    selected.sort(key=lambda x: sha(f"{SEED}:blind:{'|'.join(x[0])}".encode()))
    blind, audit = [], []
    for n, (pair, value, key) in enumerate(selected, 1):
        a, b = pair
        if int(sha((a + b).encode())[-1], 16) % 2:
            a, b = b, a
        pair_id = f"h1q_{n:03d}"
        blank = {"reviewer_id": None, "reviewed_at_utc": None, "source_completeness": None, "binary_payoff_scope": None, "assumptions": None, "state_assessment": {x: {"status": None, "evidence_or_witness": None} for x in ["00", "01", "10", "11"]}, "relation_types": None, "missing_evidence": None, "notes": None}
        blind.append({"pair_id": pair_id, "A": by_id[a], "B": by_id[b], "annotation": blank})
        audit.append({"pair_id": pair_id, "a": a, "b": b, "event_pair": list(key), **value})
    sets = {arm: {tuple(sorted((row["query_id"], hit["id"]))) for row in rows for hit in row["top"]} for arm, rows in ranks.items()}
    return blind, audit, {"union_pairs": len(candidates), "union_event_pairs": len(groups), "pairs_by_arm": {a: len(s) for a, s in sets.items()}, "pair_intersections": {a + "__" + b: len(sets[a] & sets[b]) for i, a in enumerate(sorted(sets)) for b in sorted(sets)[i + 1:]}, "queue_event_counts": dict(sorted(event_counts.items())), "queue_event_pairs": len(used_groups)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-inputs", action="store_true", help="Only create missing input lock and corpus; no inference")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if not out.is_relative_to(HERE):
        raise SystemExit("Output must stay within this experiment directory")
    out.mkdir(parents=True, exist_ok=True)
    records, duplicate_ids = build_corpus()
    poly = polymarket_inventory()
    lock_path = HERE / "input_lock.json"
    lock = {"input_files": dict(sorted(INPUTS.items())), "corpus_records_sha256": sha(canonical(records)), "polymarket_inventory_sha256": sha(canonical(poly)), "records": len(records), "deduplication": "Pilot snapshot first, then explicit official supplemental files; first occurrence by ticker. No overwritten versions.", "duplicate_ids_in_selected_files": duplicate_ids}
    if args.freeze_inputs:
        if lock_path.exists():
            raise SystemExit("Input lock already exists; refusing overwrite")
        write_json(lock_path, lock)
        write_jsonl(out / "corpus.jsonl", records)
        write_jsonl(out / "polymarket_text_inventory.jsonl", poly)
        print(json.dumps({"frozen_records": len(records), "events": len({x["event_id"] for x in records}), "polymarket_inventory": len(poly)}))
        return
    if not lock_path.exists() or json.loads(lock_path.read_text()) != lock:
        raise SystemExit("Frozen input lock absent or mismatch")
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    start = time.monotonic()
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
    model = AutoModel.from_pretrained(str(MODEL_DIR), local_files_only=True).eval().to("cpu")
    ids = [x["id"] for x in records]
    scores, ranks, embeddings, encoding, features = {}, {}, {}, {}, {}
    for view in ["title", "context"]:
        texts = [text_view(x, view) for x in records]
        embeddings[view], encoding[view] = dense_encode(texts, ids, tokenizer, model)
        scores["minilm_" + view] = embeddings[view] @ embeddings[view].T
        scores["tfidf_" + view], features[view] = lexical_scores(texts)
        for method in ["minilm", "tfidf"]:
            arm = method + "_" + view
            ranks[arm] = rank_rows(scores[arm], records)
    blind, audit, stats = choose_queue(ranks, records)
    write_jsonl(out / "corpus.jsonl", records)
    write_jsonl(out / "polymarket_text_inventory.jsonl", poly)
    write_jsonl(out / "ranks.jsonl", [{"arm": arm, **row} for arm, rows in ranks.items() for row in rows])
    write_jsonl(out / "blind_queue.jsonl", blind)
    write_jsonl(out / "selection_audit.jsonl", audit)
    write_json(out / "encoding_metadata.json", encoding)
    np.savez_compressed(out / "scores.npz", ids=np.array(ids), **scores)
    np.savez_compressed(out / "minilm_embeddings.npz", ids=np.array(ids), **embeddings)
    summary = {"scope": "Single-venue acquisition/annotation diagnostic. H1 cross-venue hypothesis NOT tested. No gold, quality, precision or recall estimates.", "records": len(records), "venues": {"kalshi": len(records)}, "events": len({x["event_id"] for x in records}), "primary_missing": sum(not x["primary"] for x in records), "secondary_empty": sum(not x["secondary"] for x in records), "queue_pairs": len(blind), "polymarket_inventory_records_excluded_from_retrieval": len(poly), "historical_records": sum(x["provenance"]["kind"] == "official_historical_api" for x in records), "candidate_top_k_per_query_per_arm": TOP_K, **stats, "encoding": {view: {"max_content_tokens": max(x["content_tokens"] for x in rows), "chunked_records": sum(x["chunks"] > 1 for x in rows), "total_chunks": sum(x["chunks"] for x in rows), "discarded_content_tokens": sum(x["discarded_content_tokens"] for x in rows)} for view, rows in encoding.items()}, "lexical_features": features}
    write_json(out / "summary.json", summary)
    model_files = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in [MODEL_DIR / x for x in ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "vocab.txt"]] if p.exists()}
    run = {"completed_at_utc": datetime.now(timezone.utc).isoformat(), "wall_seconds": time.monotonic() - start, "python": sys.version.split()[0], "platform": platform.platform(), "script_sha256": sha(Path(__file__).read_bytes()), "input_lock_sha256": sha(lock_path.read_bytes()), "model": {"repo": MODEL_REPO, "revision": MODEL_REV, "files": model_files, "local_files_only": True, "device": "cpu", "threads": 4, "batch_size": 32, "max_length": MAX_LENGTH, "pooling": "Attention-mask mean per non-overlapping chunk; content-token-count weighted chunk mean; final L2 normalization. Chunk pooling includes special tokens; no content token discarded.", "precision": "float32 inference, float64 accumulation, float32 stored embeddings"}, "lexical": {"word_ngrams": [1, 2], "char_wb_ngrams": [3, 5], "sublinear_tf": True, "combination": "Equal weight, concatenate independently L2-normalized word and char blocks, final L2", "fit": "All 323 fixed unlabeled records, separately per text view"}, "selection": {"top_k": TOP_K, "eligibility": "different event_id before top-k; no date/threshold/source filter", "tie_break": "ascending frozen market ID", "union": "four arms, both query directions; reciprocal rank fusion constant 60", "event_order": "SHA256(seed:event_id)", "event_pair_cap": MAX_PAIR_PER_EVENT_PAIR, "event_degree_cap": MAX_PAIRS_PER_EVENT, "queue_size": QUEUE_SIZE, "seed": SEED, "blind_order": "SHA256(seed:blind:sorted_pair)", "labels_used": False, "prior_model_predictions_used": False}, "dependencies": {x: importlib.metadata.version(x) for x in ["numpy", "scipy", "scikit-learn", "torch", "transformers", "tokenizers", "safetensors"]}}
    run["output_files"] = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file() and p.name in {"corpus.jsonl", "polymarket_text_inventory.jsonl", "ranks.jsonl", "blind_queue.jsonl", "selection_audit.jsonl", "encoding_metadata.json", "scores.npz", "minilm_embeddings.npz", "summary.json"}}
    write_json(out / "run_manifest.json", run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

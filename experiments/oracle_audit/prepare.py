"""Build compact numeric audit inputs from public, revision-pinned research archives."""

import argparse
import csv
import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODELS = ("gpt4o", "deepseek", "llama")


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def norm(*fields):
    return tuple(" ".join(x.replace("\\n", " ").split()) for x in fields)


def fetch(path):
    path.mkdir(exist_ok=True)
    for file, src in json.loads((DATA / "sources.json").read_text()).items():
        url = f"https://raw.githubusercontent.com/{src['repository']}/{src['revision']}/{src['path']}"
        with urllib.request.urlopen(url, timeout=90) as response:
            body = response.read()
        git_hash = hashlib.sha1(
            b"blob " + str(len(body)).encode() + b"\0" + body
        ).hexdigest()
        if git_hash != src["git_blob"]:
            raise ValueError(f"Git blob checksum mismatch: {file}")
        (path / file).write_bytes(body)


def prepare(path):
    reference = read_csv(path / "dataset.csv")
    dates, labels = defaultdict(set), defaultdict(set)
    for r in reference:
        key = norm(r["id"], r["question"], r["description"])
        dates[key].add((r["close_time"], r["ground_truth"].upper()))
        if r["close_time"] >= "2025-10-01":
            labels[r["id"]].add(r["ground_truth"])
    kota = []
    blind_features = []
    for i, r in enumerate(read_csv(path / "a.csv")):
        key = norm(r["question_id"], r["question_text"], r["resolution_criteria"])
        candidates = dates.get(key, set())
        eligible = {date for date, truth in candidates if truth == r["ground_truth"]}
        item = dict(
            row=i + 1,
            group=r["question_id"],
            category=r["category"],
            close_date=next(iter(eligible))[:10] if len(eligible) == 1 else "",
            y=int(r["ground_truth"] == "YES"),
            saved=r["final_decision"],
            wall_ms=r["resolution_time_ms"],
        )
        for m in MODELS:
            item[m] = r[m + "_decision"]
            item[m + "_conf"] = r[m + "_confidence"]
        kota.append(item)
        # Fixed binary word unigrams from contract text alone. Hashes make the projected input compact.
        tokens = set(
            re.findall(
                r"[a-z]+|[0-9]+",
                (r["question_text"] + " " + r["resolution_criteria"]).lower(),
            )
        )
        buckets = sorted(
            {
                int.from_bytes(hashlib.sha256(t.encode()).digest()[:4], "big") % 8192
                for t in tokens
            }
        )
        blind_features.append(dict(row=i + 1, buckets=" ".join(map(str, buckets))))
    write_csv(DATA / "kota_votes.csv", kota)
    write_csv(DATA / "blind_features.csv", blind_features)
    b = read_csv(path / "b_curve.csv")
    write_csv(
        DATA / "kota_b_final.csv",
        [dict(uid=r["row_uid"], correct=int(r["is_correct"] == "True")) for r in b],
    )
    nel, published = [], {}
    for i in range(5):
        obj = json.loads((path / f"nel{i}.json").read_text())
        name = obj["model_name"]
        published[name] = {
            k: obj[k]
            for k in (
                "num_samples",
                "accuracy",
                "brier_score",
                "avg_latency_ms",
                "total_cost_usd",
            )
        }
        for pos, pred in enumerate(obj["predictions"]):
            qid = pred["question_id"]
            raw = re.search(
                r"<confidence>\s*(\d+(?:\.\d+)?)\s*</confidence>",
                pred["raw_output"] or "",
                re.I,
            )
            p = min(1.0, max(0.0, float(raw[1]) / 100)) if raw else None
            eligible = labels.get(qid, set())
            y = int(next(iter(eligible)) == "yes") if len(eligible) == 1 else ""
            nel.append(
                dict(
                    model=name,
                    position=pos,
                    group=qid,
                    y=y,
                    answer=pred["predicted_answer"],
                    stored_p=pred["predicted_probability"],
                    raw_tag_p=p,
                    latency_ms=pred["latency_ms"],
                )
            )
    write_csv(DATA / "nel_votes.csv", nel)
    (DATA / "nel_published.json").write_text(json.dumps(published, indent=2) + "\n")
    jev = []
    for line in (path / "jev.jsonl").read_text().splitlines():
        r = json.loads(line)
        assert r["kind"] == "obs"
        ans = r["answers"]["cat"]
        jev.append(
            dict(
                id=r["meta"]["id"],
                rep=r["meta"]["rep"],
                label=r["meta"]["truth"],
                answer=ans["choice"],
                confidence=ans["confidence"],
                difficulty=r["meta"]["diff"],
                usd=r["cost"],
                latency_ms=r["latency_ms"],
            )
        )
    write_csv(DATA / "jev_choices.csv", jev)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source-dir", type=Path, default=ROOT / ".staging")
    cli.add_argument(
        "--fetch", action="store_true", help="Download and verify original Git blobs"
    )
    opt = cli.parse_args()
    if opt.fetch:
        fetch(opt.source_dir)
    prepare(opt.source_dir)

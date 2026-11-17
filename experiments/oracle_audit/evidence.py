"""Count cache fields in committed inventory; optionally verify against the pinned Git tree."""

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from prepare import ROOT, DATA, read_csv

REPO = "Tkota10/Senior-Thesis-Multi-LLM-Resolution"
REV = "f76754b5bcff1a1d7a50c2f1073a4b6d44bd985c"


def recalculate(directory=None):
    items = read_csv(DATA / "evidence_inventory.csv")
    for saved in items:
        name = saved["packet"]
        if directory:
            data = (directory / name).read_bytes()
        else:
            url = (
                f"https://raw.githubusercontent.com/{REPO}/{REV}/cache/evidence/{name}"
            )
            with urlopen(url, timeout=45) as response:
                data = response.read()
        digest = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        assert saved["git_blob"] == digest, name
        packet = json.loads(data)
        s = packet["sources"]
        close = date.fromisoformat(packet["resolution_date"][:10])
        dates = [
            date.fromisoformat(x["published_date"][:10])
            for x in s
            if x.get("published_date")
        ]
        expected = dict(
            packet=name,
            git_blob=digest,
            resolution_date=packet["resolution_date"],
            retrieved=packet["retrieval_timestamp"],
            n_sources=len(s),
            empty_text=sum(not (x.get("text") or "").strip() for x in s),
            empty_highlights=sum(not x.get("highlights") for x in s),
            missing_pub=len(s) - len(dates),
            after_close_day=sum(d > close for d in dates),
            after_plus1_day=sum(d > close + timedelta(days=1) for d in dates),
            domains=len({urlsplit(x["url"]).netloc for x in s}),
        )
        assert {k: str(v) for k, v in expected.items()} == saved, name


def summarize():
    items = read_csv(DATA / "evidence_inventory.csv")
    keys = [
        "n_sources",
        "empty_text",
        "empty_highlights",
        "missing_pub",
        "after_close_day",
        "after_plus1_day",
    ]
    return dict(
        packets=len(items),
        source_counts={k: sum(int(r[k]) for r in items) for k in keys},
        packets_with_at_least_one={k: sum(int(r[k]) > 0 for r in items) for k in keys},
        retrieval_range=[
            min(r["retrieved"] for r in items),
            max(r["retrieved"] for r in items),
        ],
        retrieved_after_close_day=sum(
            r["retrieved"][:10] > r["resolution_date"][:10] for r in items
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--verify-network", action="store_true")
    cli.add_argument("--verify-directory", type=Path)
    opt = cli.parse_args()
    if opt.verify_network or opt.verify_directory:
        recalculate(opt.verify_directory)
    (ROOT / "results" / "evidence.json").write_text(
        json.dumps(summarize(), indent=2) + "\n"
    )

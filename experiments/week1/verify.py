"""Verify frozen inputs and reproduce all non-timing E01 summary fields offline."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from evaluate import summarize
from prepare import build

HERE = Path(__file__).resolve().parent


def without_checker_timing(summary):
    result = copy.deepcopy(summary)
    for method in result["methods"].values():
        method["cost"].pop("checker_seconds", None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=HERE / "results/observed")
    args = parser.parse_args()
    packets, refs, sources = build()
    assert json.loads((HERE / "data/packets.json").read_text()) == packets
    assert json.loads((HERE / "data/reference.json").read_text()) == refs
    manifest = json.loads((HERE / "data/manifest.json").read_text())
    for name, expected in manifest["source_sha256"].items():
        assert hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() == expected
    saved = json.loads((args.run / "summary.json").read_text())
    with tempfile.TemporaryDirectory(prefix="week1-verify-") as folder:
        recomputed = summarize(args.run, Path(folder))
    assert without_checker_timing(saved) == without_checker_timing(recomputed), "Summary mismatch"
    assert saved["methods"]["rule_only"]["controlled"]["exact_pairs"] == 16
    assert saved["methods"]["always_no_constraint"]["controlled"]["forbidden_recall"] == 0
    assert saved["methods"]["always_unknown"]["controlled"]["state_coverage"] == 0
    print("PASS: frozen source inputs, 24 packets, 96 unique calls, complete offline metric reproduction")


if __name__ == "__main__":
    main()

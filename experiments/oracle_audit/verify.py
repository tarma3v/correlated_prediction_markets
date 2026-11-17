"""Verify frozen inputs and reproduce all result files without external services."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCK = json.loads((ROOT / "checksums.json").read_text())


def verify_table(paths):
    for rel, digest in paths.items():
        path = ROOT / rel
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {rel}")


def main():
    verify_table(LOCK["inputs_sha256"])
    for program in (
        "audit.py",
        "text_baseline.py",
        "evidence.py",
        "replay.py",
        "jev_packets.py",
    ):
        subprocess.run(
            [sys.executable, "-B", str(ROOT / program)], check=True, cwd=ROOT
        )
    verify_table(LOCK["results_sha256"])
    print(
        f"Verified {len(LOCK['inputs_sha256'])} inputs and reproduced {len(LOCK['results_sha256'])} result files."
    )


if __name__ == "__main__":
    main()

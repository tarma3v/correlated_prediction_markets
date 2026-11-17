"""Read frozen inputs and write only files belonging to this audit."""

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INPUTS = {}
STATES = ("00", "01", "10", "11")


def read(path, lines=False):
    content = (ROOT / path).read_bytes()
    INPUTS[path] = hashlib.sha256(content).hexdigest()
    return list(map(json.loads, content.splitlines())) if lines else json.loads(content)


def write(name, obj, lines=False):
    if lines:
        serialized = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in obj)
    else:
        serialized = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    (HERE / name).write_text(serialized, encoding="utf-8")


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.casefold())


def div(num, den):
    return num / den if den else None

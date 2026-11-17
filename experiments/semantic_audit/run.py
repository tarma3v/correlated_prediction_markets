#!/usr/bin/env python3
"""Run offline from any working directory. Frozen results need only Python 3.10+."""
import hashlib
import platform
from common import HERE, INPUTS, write
from graph import evaluate_graph
from llm import llm
from mutations import mutation_audit
from search import cpi, retrieval


def main():
    result = {
        "author_retrieval": retrieval(),
        "cpi": cpi(),
        "llm": llm(),
        "graph": evaluate_graph(),
        "text_mutations": mutation_audit(),
    }
    write("results.json", result)
    sources = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(HERE.glob("*.py"))
    }
    out = {
        name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        for name in (
            "results.json",
            "author_ranks.jsonl",
            "cpi_pairs.jsonl",
            "graph_edges.jsonl",
            "mutation_cases.jsonl",
        )
    }
    write(
        "manifest.json",
        dict(
            python=platform.python_version(),
            input_sha256=dict(sorted(INPUTS.items())),
            code_sha256=sources,
            output_sha256=out,
            protocol_sha256=hashlib.sha256(
                (HERE / "PROTOCOL_RU.md").read_bytes()
            ).hexdigest(),
            mutation_protocol_sha256=hashlib.sha256(
                (HERE / "MUTATION_PROTOCOL_RU.md").read_bytes()
            ).hexdigest(),
            model_inference_this_run=False,
        ),
    )
    print("Wrote results.json, 4 row-level files and manifest.json")


if __name__ == "__main__":
    main()

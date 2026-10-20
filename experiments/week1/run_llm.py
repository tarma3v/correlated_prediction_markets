"""Run E01 with a pinned local MLX model. The runner never reads reference labels."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATES = ("00", "01", "10", "11")
RELATIONS = ("equivalent", "a_implies_b", "b_implies_a", "disjoint", "exhaustive",
             "complement", "no_hard_relation", "unknown")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def schema(branch):
    score = {"type": "number", "minimum": 0, "maximum": 1}
    if branch == "direct":
        props = {"relation": {"enum": list(RELATIONS)}, "confidence": score}
    else:
        fields = {k: {"type": "string", "minLength": 1} for k in
                  ("metric", "source", "period", "unit", "threshold", "predicate_quote")}
        fields["op"] = {"enum": ["gt", "ge", "lt", "le"]}
        extraction = {"anyOf": [{"type": "null"}, {"type": "object", "properties": fields,
                      "required": list(fields), "additionalProperties": False}]}
        witness = {"anyOf": [{"type": "null"}, {"type": "object", "properties": {
                   "x_a": {"type": "string"}, "x_b": {"type": "string"}},
                   "required": ["x_a", "x_b"], "additionalProperties": False}]}
        props = {"A": extraction, "B": extraction, "confidence": score,
                 "states": {"type": "object", "properties": {s: {"enum": ["forbidden", "possible", "unknown"]}
                            for s in STATES}, "required": list(STATES), "additionalProperties": False},
                 "witnesses": {"type": "object", "properties": {s: witness for s in STATES},
                               "required": list(STATES), "additionalProperties": False}}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def parse(raw, branch):
    import jsonschema
    try:
        obj = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except ValueError:
        return None, "json_error"
    try:
        jsonschema.validate(obj, schema(branch))
    except jsonschema.ValidationError:
        return None, "schema_error"
    return obj, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; existing files are never replaced")
    parser.add_argument("--download", action="store_true", help="Download pinned public model files if absent")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output directory is not empty; choose a new directory")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    from huggingface_hub import snapshot_download

    config = json.loads((HERE / "config.json").read_text())
    manifest = json.loads((HERE / "data/manifest.json").read_text())
    for name, expected in {**manifest["inputs_sha256"], **manifest["prompt_sha256"]}.items():
        if digest(HERE / name) != expected:
            raise ValueError("Frozen input changed: " + name)
    packets = json.loads((HERE / "data/packets.json").read_text())
    prompts = {p.stem: p.read_text() for p in (HERE / "prompts").glob("*.txt")}
    spec = config["model"]
    snapshot = Path(snapshot_download(spec["repo"], revision=spec["revision"],
                    cache_dir=str(ROOT / "tmp/llm_cache"), token=False,
                    local_files_only=not args.download,
                    allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja", "README.md", "LICENSE*"]))
    model, tokenizer = load(str(snapshot), tokenizer_config={"trust_remote_code": False})
    args.output.mkdir(parents=True, exist_ok=True)
    run = {"experiment": config["experiment"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
           "status": "running", "config": config, "data_manifest_sha256": digest(HERE / "data/manifest.json"),
           "runner_sha256": digest(Path(__file__)), "python": platform.python_version(),
           "platform": platform.system() + " " + platform.machine(),
           "packages": {x: metadata.version(x) for x in ["mlx", "mlx-lm", "transformers", "numpy", "jsonschema", "huggingface-hub"]},
           "model_files_sha256": {str(p.relative_to(snapshot)): digest(p) for p in sorted(snapshot.rglob("*")) if p.is_file()},
           "generation": "Greedy, no constrained decoding, no retries or JSON repair; format errors retained",
           "calls_planned": len(packets) * len(config["branches"])}
    save(args.output / "run_manifest.json", run)
    output = args.output / "predictions.jsonl"
    start = time.monotonic()
    for index, case in enumerate(packets, 1):
        draft = None
        for branch in config["branches"]:
            extra = ""
            task = prompts[branch]
            if branch in ("repeat", "critic"):
                task += "\n" + prompts["structured"]
                extra = "\nINITIAL DRAFT (untrusted prediction):\n" + draft
            task += "\nYour response MUST satisfy this JSON schema:\n" + json.dumps(schema(branch), sort_keys=True)
            messages = [{"role": "system", "content": prompts["common"] + "\n" + task},
                        {"role": "user", "content": json.dumps(case["packet"], ensure_ascii=False) + extra}]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            input_tokens = len(tokenizer.encode(prompt))
            raw, last, error = "", None, None
            begun = time.monotonic()
            if input_tokens > config["max_input_tokens"]:
                error = "input_too_long_no_truncation"
            else:
                mx.random.seed(config["seed"])
                try:
                    for response in stream_generate(model, tokenizer, prompt=prompt,
                            max_tokens=config["max_new_tokens_per_call"], sampler=make_sampler(temp=config["temperature"])):
                        raw += response.text
                        last = response
                except Exception as exc:
                    error = "runtime_" + type(exc).__name__
            parsed, parse_error = parse(raw, branch)
            finish = getattr(last, "finish_reason", None)
            if finish == "length":
                error = "output_token_limit"
            error = error or parse_error
            row = {"case_id": case["case_id"], "packet_sha256": case["packet_sha256"],
                   "branch": branch, "raw_output": raw, "parsed": parsed,
                   "error": error, "input_tokens": input_tokens,
                   "output_tokens": getattr(last, "generation_tokens", 0),
                   "finish_reason": finish, "seconds": time.monotonic() - begun,
                   "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
            with output.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if branch == "structured":
                draft = raw
            mx.clear_cache()
        print(f"E01 {index}/{len(packets)} pairs, {time.monotonic()-start:.1f}s", flush=True)
    run.update(status="complete", completed_at_utc=datetime.now(timezone.utc).isoformat(),
               seconds=time.monotonic() - start, predictions_sha256=digest(output))
    save(args.output / "run_manifest.json", run)


if __name__ == "__main__":
    main()

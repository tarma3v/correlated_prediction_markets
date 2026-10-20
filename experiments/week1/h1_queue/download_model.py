"""Download only the public, revision-pinned MiniLM files used by this diagnostic."""
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[3]
snapshot_download(
    "sentence-transformers/all-MiniLM-L6-v2",
    revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    cache_dir=str(ROOT / "tmp/hf_cache"),
    token=False,
    allow_patterns=["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
                    "special_tokens_map.json", "vocab.txt", "README.md", "LICENSE*"],
)
print("Pinned MiniLM snapshot is available in the local cache")

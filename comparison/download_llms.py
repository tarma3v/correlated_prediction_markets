"""Download two pinned public MLX quantizations; weights stay outside Git."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
ALLOW_PATTERNS = ['*.json', '*.safetensors', '*.txt', '*.model', '*.jinja', '.gitattributes', 'README.md', 'LICENSE*']
MODELS = {
    'qwen3_4b': {'repo': 'mlx-community/Qwen3-4B-Instruct-2507-4bit',
                'revision': '50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b'},
    'llama32_3b': {'repo': 'mlx-community/Llama-3.2-3B-Instruct-4bit',
                   'revision': '7f0dc925e0d0afb0322d96f9255cfddf2ba5636e'},
}

def main():
    manifest = {}
    for key, spec in MODELS.items():
        print('Downloading', key, flush=True)
        path = snapshot_download(spec['repo'], revision=spec['revision'],
             cache_dir=str(ROOT/'tmp/llm_cache'), token=False,
             allow_patterns=ALLOW_PATTERNS,
             max_workers=3)
        hashes = {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in Path(path).rglob('*') if p.is_file()}
        manifest[key] = dict(spec, fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                             files_sha256=hashes, quantization='4 bit, MLX community conversion')
        print('Downloaded and hashed', key, len(hashes), 'files', flush=True)
    dest=ROOT/'comparison/llm';dest.mkdir(exist_ok=True)
    (dest/'models.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__ == '__main__':
    main()

"""Download pinned public safetensors models; no account or inference API."""
import os
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT=Path(__file__).resolve().parents[2]
MODELS=[('sentence-transformers/all-MiniLM-L6-v2','1110a243fdf4706b3f48f1d95db1a4f5529b4d41'),
        ('MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli','6f5cf0a2b59cabb106aca4c287eed12e357e90eb')]
for repo,revision in MODELS:
    print('Downloading',repo,flush=True)
    snapshot_download(repo_id=repo,revision=revision,token=False,cache_dir=str(ROOT/'tmp/hf_cache'),
       allow_patterns=['config.json','model.safetensors','tokenizer.json','tokenizer_config.json',
                       'special_tokens_map.json','added_tokens.json','vocab.txt','spm.model',
                       'sentence_bert_config.json','1_Pooling/config.json'],max_workers=3)

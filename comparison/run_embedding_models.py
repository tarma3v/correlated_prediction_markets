#!/usr/bin/env python3
"""Pinned E5/BGE retrieval extension on the frozen author-audit candidate pool.

No training, no remote inference, no independent gold labels. Corpus embeddings
are computed without labels; the existing evaluator is reused with a new OUT.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import time

os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
import numpy as np
import torch
from huggingface_hub import snapshot_download
from transformers import AutoModel, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'comparison/retrieval'
CACHE = ROOT/'tmp/hf_cache'
INPUTS = {
    'redesign/retrieval/markets.json': '730b5a504dae16ea5fe620e1354aa2120c97b5ad5770095f2fa529cc9b90e152',
    'redesign/retrieval/reference_pairs.json': '424400dd5cfb0735aea1e6f777ae7367ca2235c1992ac63c1147da66b3687629',
    'redesign/run_retrieval.py': '6889d69f6828dfbf6fd986232630e529f0ee29dd35d2f35257cbdebbdf9185ab',
}
MODELS = {
    'e5_small_v2': {
        'repo': 'intfloat/e5-small-v2',
        'revision': 'ffb93f3bd4047442299a41ebb6fa998a38507c52',
        'weights_sha256': '45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1',
        'prefix': 'query: ', 'pooling': 'masked_mean', 'max_length': 512,
        'instruction_reason': 'Official card recommends query: on both sides for symmetric semantic similarity / paraphrase retrieval. This is market-to-market matching, not short-query to long-passage search.',
    },
    'bge_small_en_v1_5': {
        'repo': 'BAAI/bge-small-en-v1.5',
        'revision': '5c38ec7c405ec4b44b94cc5a9bb96e735b38267a',
        'weights_sha256': '3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad',
        'prefix': '', 'pooling': 'cls', 'max_length': 512,
        'instruction_reason': 'Official card permits no instruction; recommends query instruction for short-query to long-passage search. Here both sides are short market descriptors.',
    },
}
MODEL_FILES = ['README.md', 'config.json', 'model.safetensors', 'tokenizer.json',
               'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt',
               'modules.json', '1_Pooling/config.json']


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()
def save(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
def load(path): return json.loads(path.read_text())


def get_evaluator():
    spec = importlib.util.spec_from_file_location('frozen_retrieval_evaluator', ROOT/'redesign/run_retrieval.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT  # Its evaluate() writes pair ranks; never use the old OUT.
    assert module.OUT != ROOT/'redesign/retrieval'
    return module.evaluate


def prepare_model(key, offline):
    spec = MODELS[key]
    started = time.monotonic()
    path = Path(snapshot_download(spec['repo'], revision=spec['revision'],
                cache_dir=str(CACHE), allow_patterns=MODEL_FILES, token=False,
                local_files_only=offline, max_workers=4))
    checksums = {name: {'sha256': sha(path/name), 'bytes': (path/name).stat().st_size}
                 for name in MODEL_FILES}
    assert checksums['model.safetensors']['sha256'] == spec['weights_sha256']
    # Card, tokenizer and weights remain in the ignored, revision-pinned cache.
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                     use_safetensors=True).eval().to('cpu')
    metadata = dict(spec, official_model_card_url=f"https://huggingface.co/{spec['repo']}/blob/{spec['revision']}/README.md",
                    snapshot_path=str(path.relative_to(ROOT)), files=checksums,
                    normalization='L2 after pooling', dtype='float32',
                    embedding_dimensions=int(model.config.hidden_size),
                    parameter_count=sum(p.numel() for p in model.parameters()),
                    setup_wall_seconds=time.monotonic()-started)
    return tokenizer, model, metadata


def encode(tokenizer, model, texts, spec, batch_size):
    # Refuse silently lossy evaluation. Prefix and special tokens count too.
    inputs = [spec['prefix']+t for t in texts]
    lengths = [len(ids) for ids in tokenizer(inputs, add_special_tokens=True,
                                           truncation=False)['input_ids']]
    if max(lengths) > spec['max_length']:
        raise ValueError(f"Input exceeds {spec['max_length']} tokens; no truncation is allowed")
    chunks = []
    for start in range(0, len(inputs), batch_size):
        batch = tokenizer(inputs[start:start+batch_size], padding=True,
                          truncation=False, return_tensors='pt')
        with torch.inference_mode():
            hidden = model(**batch).last_hidden_state
            if spec['pooling'] == 'masked_mean':
                mask = batch['attention_mask'].unsqueeze(-1)
                hidden = hidden.masked_fill(~mask.bool(), 0.0)
                pooled = hidden.sum(dim=1)/mask.sum(dim=1)
            elif spec['pooling'] == 'cls':
                pooled = hidden[:, 0]
            else:
                raise ValueError(spec['pooling'])
            chunks.append(torch.nn.functional.normalize(pooled, p=2, dim=1).cpu().numpy())
    embeddings = np.concatenate(chunks)
    assert np.isfinite(embeddings).all()
    assert np.allclose(np.linalg.norm(embeddings, axis=1), 1.0, atol=2e-6)
    return embeddings, {'input_count': len(inputs), 'truncated_inputs': 0,
                        'max_untruncated_tokens': max(lengths),
                        'tokens_per_input': lengths,
                        'exact_prefixed_inputs_sha256': hashlib.sha256(
                            json.dumps(inputs, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', choices=MODELS, default=list(MODELS))
    parser.add_argument('--views', nargs='+', choices=['event_title', 'title'], default=['event_title', 'title'])
    parser.add_argument('--offline', action='store_true', help='Use only already downloaded pinned snapshots')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    assert args.batch_size > 0 and args.threads > 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, expected in INPUTS.items():
        if sha(ROOT/name) != expected: raise ValueError('Frozen input changed: '+name)
    frozen_artifacts = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'redesign/retrieval').iterdir()
                        if p.is_file() and p.suffix in ['.json', '.npz']}
    markets = load(ROOT/'redesign/retrieval/markets.json')
    pairs = load(ROOT/'redesign/retrieval/reference_pairs.json')
    assert {k: len(v) for k,v in markets.items()} == {'poly': 493, 'kalshi': 493}
    assert Counter(p['label'] for p in pairs) == {'same': 461, 'different': 27, 'unsure': 5}
    for rows in markets.values(): assert len({r['id'] for r in rows}) == len(rows)
    torch.manual_seed(0); np.random.seed(0); torch.set_num_threads(args.threads)
    started = time.monotonic()
    manifest = {
        'created_at_utc': now(), 'status': 'running', 'script_sha256': sha(Path(__file__)),
        'inputs_sha256': INPUTS, 'old_artifacts_sha256': frozen_artifacts,
        'python': platform.python_version(), 'platform': platform.platform(),
        'dependencies': {p: importlib.metadata.version(p) for p in ['torch','transformers','numpy','huggingface-hub','tokenizers','safetensors','scikit-learn']},
        'settings': {'device': 'cpu', 'threads': args.threads, 'batch_size': args.batch_size,
                     'seed': 0, 'model_eval': True, 'gradients': False,
                     'views': args.views, 'models': args.models, 'offline': args.offline,
                     'cosine': 'L2-normalized dot product', 'tie_break': 'stable argsort; frozen input order'},
        'text_views': {'event_title': "event_title + '\\n' + title", 'title': 'title'},
        'candidate_pool': {'poly': 493, 'kalshi': 493, 'filtering': 'none; all opposite-venue markets'},
        'evaluation': 'Existing frozen evaluate(), explicit OUT redirection; k=1,3,5,10; both retrieval directions.',
        'primary_view': 'event_title', 'secondary_view': 'title',
        'reference_labels': dict(Counter(p['label'] for p in pairs)),
        'warning': 'External author-audit known links, not independently adjudicated exhaustive gold. No precision, population recall, payoff-equivalence or resolution-rule accuracy claim. No model selection/tuning beyond this descriptive comparison.',
        'models': {},
    }
    save('run_manifest.json', manifest)
    save('embedding_row_ids.json', {v: [r['id'] for r in rows] for v,rows in markets.items()})
    evaluate = get_evaluator()
    all_results = []; metadata = {}
    for key in args.models:
        print('Loading', key, now(), flush=True)
        tokenizer, model, model_meta = prepare_model(key, args.offline)
        manifest['models'][key] = model_meta
        save('run_manifest.json', manifest)
        for view in args.views:
            view_started = time.monotonic()
            arrays = {}; token_meta = {}
            for venue, rows in markets.items():
                texts = [(r['event_title']+'\n'+r['title']) if view=='event_title' else r['title'] for r in rows]
                encode_started = time.monotonic()
                arrays[venue], token_meta[venue] = encode(tokenizer, model, texts, MODELS[key], args.batch_size)
                token_meta[venue]['encoding_wall_seconds'] = time.monotonic()-encode_started
                print('Encoded', key, view, venue, len(rows), 'max_tokens', token_meta[venue]['max_untruncated_tokens'], flush=True)
            sim = arrays['poly']@arrays['kalshi'].T
            assert sim.shape == (493,493) and np.isfinite(sim).all()
            # One symmetric short-text encoder; reverse retrieval uses matrix.T.
            np.savez_compressed(OUT/f'{key}_{view}_embeddings.npz', **arrays)
            np.save(OUT/f'{key}_{view}_scores.npy', sim)
            results = evaluate(sim, markets, pairs, key, view)
            all_results.extend(results)
            ranks = load(OUT/f'{key}_{view}_pair_ranks.json')
            negative_diagnostics = {}
            for label in ['different','unsure']:
                rows = [r for r in ranks if r['reference_label']==label]
                negative_diagnostics[label] = {
                    'total_reference_pairs': len(rows),
                    'poly_to_kalshi_top1': sum(r['kalshi_rank_for_poly']==1 for r in rows),
                    'kalshi_to_poly_top1': sum(r['poly_rank_for_kalshi']==1 for r in rows),
                    'poly_to_kalshi_top5': sum(r['kalshi_rank_for_poly']<=5 for r in rows),
                    'kalshi_to_poly_top5': sum(r['poly_rank_for_kalshi']<=5 for r in rows),
                }
            metadata[f'{key}_{view}'] = {
                'model': key, 'view': view, 'tokenization': token_meta,
                'wall_seconds': time.monotonic()-view_started,
                'reference_non_same_retrieved_diagnostic': negative_diagnostics,
            }
            save('results.json', all_results)
            save('summary.json', [{k:v for k,v in r.items() if k!='queries'} for r in all_results])
            save('encoding_metadata.json', metadata)
            print('Completed', key, view, 'seconds', round(metadata[f'{key}_{view}']['wall_seconds'],2), flush=True)
        del model, tokenizer
    for name, expected in frozen_artifacts.items():
        if sha(ROOT/name) != expected: raise ValueError('Old artifact modified during run: '+name)
    manifest.update(status='complete', completed_at_utc=now(), wall_seconds=time.monotonic()-started,
                    frozen_artifacts_unchanged=True)
    manifest['output_files'] = {
        str(p.relative_to(OUT)): {'sha256': sha(p), 'bytes': p.stat().st_size}
        for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='run_manifest.json'
    }
    save('run_manifest.json', manifest)
    print('All complete', round(manifest['wall_seconds'],2), 'seconds', flush=True)


if __name__ == '__main__': main()

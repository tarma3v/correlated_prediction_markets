#!/usr/bin/env python3
"""Verify saved outputs without loading models or rerunning inference."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
def load(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

markets = load(ROOT/'redesign/retrieval/markets.json')
indices = {v: {r['id']: i for i,r in enumerate(rows)} for v,rows in markets.items()}
summary = load(OUT/'summary.json')
row_ids = load(OUT/'embedding_row_ids.json')
assert row_ids == {v: [r['id'] for r in rows] for v,rows in markets.items()}
report = {'purpose': 'Independent checks from stored score matrices and pair ranks; no further inference', 'checks': []}
for model in ['e5_small_v2','bge_small_en_v1_5']:
    for view in ['event_title','title']:
        prefix = f'{model}_{view}'
        emb = np.load(OUT/f'{prefix}_embeddings.npz')
        sim = np.load(OUT/f'{prefix}_scores.npy')
        assert sim.shape == (493,493)
        assert np.allclose(sim, emb['poly']@emb['kalshi'].T, atol=1e-6)
        for venue in ['poly','kalshi']:
            assert np.allclose(np.linalg.norm(emb[venue], axis=1), 1, atol=2e-6)
        rows = load(OUT/f'{prefix}_pair_ranks.json')
        assert len(rows) == 493
        for row in rows:
            i = indices['poly'][row['poly_id']]
            j = indices['kalshi'][row['kalshi_ticker']]
            value = sim[i,j]
            assert float(value) == row['similarity']
            # Independent of evaluator argsort: count higher values and earlier ties.
            rank = 1 + int((sim[i]>value).sum()) + int(((sim[i]==value)&(np.arange(493)<j)).sum())
            reverse = 1 + int((sim[:,j]>value).sum()) + int(((sim[:,j]==value)&(np.arange(493)<i)).sum())
            assert rank == row['kalshi_rank_for_poly']
            assert reverse == row['poly_rank_for_kalshi']
        same = [r for r in rows if r['reference_label']=='same']
        for src,key in [('poly','kalshi_rank_for_poly'),('kalshi','poly_rank_for_kalshi')]:
            result = next(r for r in summary if r['method']==model and r['view']==view and r['source_venue']==src)
            assert result['query_count'] == len(same) == 461
            for k in [1,3,5,10]:
                recall = sum(r[key]<=k for r in same)/len(same)
                assert abs(recall-result['at_k'][str(k)]['known_link_recall']) < 1e-12
        report['checks'].append({'model':model, 'view':view, 'score_shape':list(sim.shape),
                                'norms_valid':True, 'stored_pair_scores_checked':len(rows),
                                'directional_pair_ranks_checked':2*len(rows), 'metrics_verified':True})
manifest = load(OUT/'run_manifest.json')
omitted=[]
for name,expected in manifest['old_artifacts_sha256'].items():
    if not (ROOT/name).exists():
        omitted.append(name)
        continue
    assert sha(ROOT/name) == expected, name
report.update(retained_old_artifacts_unchanged=True, omitted_historical_artifacts=omitted, all_passed=True)
(OUT/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print('PASS: 1,972 scores; 3,944 directional ranks; known-link metrics; retained original artifacts unchanged.')

"""Cross-venue retrieval against an external audit fixture, without training.

Reference 'same' labels come from another project's audit, not human gold.
Unknown cross-pairs are NOT negatives. Metrics recover known links only.
"""
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'redesign' / 'retrieval'
SOURCE = ROOT / 'redesign/datasets/rawsamples/nl2992_endorsed_fixture.txt'
sys.path.insert(0, str(ROOT / 'extension/nlp'))
from run_models import load_model, MODELS


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records():
    raw = json.loads(SOURCE.read_text())
    pairs, markets, conflicts = {}, {'poly': {}, 'kalshi': {}}, []
    for subset in ['signal_subset', 'stratified_subset']:
        for row in raw[subset]:
            key = (row['poly_id'], row['kalshi_ticker'])
            if key in pairs:
                assert pairs[key]['label'] == row['label'], 'Conflicting pair labels'
                pairs[key]['subsets'].append(subset)
            else:
                pairs[key] = dict(row, subsets=[subset])
            for venue, mid in [('poly', key[0]), ('kalshi', key[1])]:
                rec = {'id': mid, 'title': row[venue + '_title'],
                       'event_title': row[venue + '_event_title']}
                if mid in markets[venue] and markets[venue][mid] != rec:
                    conflicts.append({'venue': venue, 'id': mid,
                                      'first': markets[venue][mid], 'alternative': rec})
                else:
                    markets[venue][mid] = rec
    assert not conflicts, f'Metadata conflicts require review: {conflicts[:2]}'
    return {v: [ms[k] for k in sorted(ms)] for v, ms in markets.items()}, list(pairs.values())


def text_view(record, view):
    if view == 'title':
        return record['title']
    return record['event_title'] + '\n' + record['title']


def encode_dense(texts, tokenizer, model):
    lengths = [len(tokenizer(t, truncation=False)['input_ids']) for t in texts]
    chunks = []
    for start in range(0, len(texts), 32):
        batch = tokenizer(texts[start:start+32], padding=True, truncation=True,
                          max_length=256, return_tensors='pt')
        with torch.inference_mode():
            hidden = model(**batch).last_hidden_state
            mask = batch['attention_mask'].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            chunks.append(torch.nn.functional.normalize(pooled, p=2, dim=1).numpy())
    return np.concatenate(chunks), {'max_tokens': max(lengths),
                                   'truncated_inputs': sum(x > 256 for x in lengths)}


def evaluate(sim, markets, pairs, method, view):
    results = []
    for src, dst, matrix in [('poly', 'kalshi', sim), ('kalshi', 'poly', sim.T)]:
        sid, tid = (('poly_id', 'kalshi_ticker') if src == 'poly'
                    else ('kalshi_ticker', 'poly_id'))
        relevant = defaultdict(set)
        for pair in pairs:
            if pair['label'] == 'same':
                relevant[pair[sid]].add(pair[tid])
        order = np.argsort(-matrix, axis=1, kind='stable')
        query_rows = []
        for i, query in enumerate(markets[src]):
            if query['id'] not in relevant:
                continue
            ranked = [markets[dst][int(j)]['id'] for j in order[i]]
            positions = [ranked.index(mid) + 1 for mid in relevant[query['id']]]
            query_rows.append({'source_venue': src, 'id': query['id'],
                'event_title': query['event_title'], 'known_link_count': len(positions),
                'best_known_link_rank': min(positions), 'known_link_ranks': positions,
                'top10': [{'id': ranked[k], 'score': float(matrix[i, order[i, k]])}
                          for k in range(min(10, len(ranked)))]})
        groups = defaultdict(list)
        for row in query_rows:
            groups[row['event_title']].append(row)
        metrics = {}
        for k in [1, 3, 5, 10]:
            micro = np.mean([r['best_known_link_rank'] <= k for r in query_rows])
            macro = np.mean([np.mean([r['best_known_link_rank'] <= k for r in rows])
                             for rows in groups.values()])
            link_recall = sum(sum(rank <= k for rank in r['known_link_ranks'])
                              for r in query_rows) / sum(r['known_link_count'] for r in query_rows)
            metrics[str(k)] = {'query_hit_rate': float(micro),
                              'event_macro_query_hit_rate': float(macro),
                              'known_link_recall': float(link_recall)}
        results.append({'method': method, 'view': view, 'source_venue': src,
            'target_venue': dst, 'candidate_count_per_query': len(markets[dst]),
            'query_count': len(query_rows), 'source_event_groups': len(groups),
            'at_k': metrics, 'queries': query_rows})
    # Preserve ranks of all externally labelled pairs, including different/unsure.
    indices = {v: {r['id']: i for i, r in enumerate(rows)} for v, rows in markets.items()}
    ranks = []
    for pair in pairs:
        i, j = indices['poly'][pair['poly_id']], indices['kalshi'][pair['kalshi_ticker']]
        order = np.argsort(-sim[i], kind='stable')
        reverse = np.argsort(-sim[:, j], kind='stable')
        ranks.append({'poly_id': pair['poly_id'], 'kalshi_ticker': pair['kalshi_ticker'],
            'reference_label': pair['label'], 'reason_class': pair['reason_class'],
            'similarity': float(sim[i, j]), 'kalshi_rank_for_poly': int(np.where(order == j)[0][0])+1,
            'poly_rank_for_kalshi': int(np.where(reverse == i)[0][0])+1})
    save(f'{method}_{view}_pair_ranks.json', ranks)
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)
    torch.set_num_threads(4)
    markets, pairs = records()
    save('markets.json', markets)
    save('reference_pairs.json', pairs)
    plan = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_sha256': digest(SOURCE), 'script_sha256': digest(Path(__file__)),
        'plan': 'No tuning. Compare lexical and MiniLM; title vs event+title; both cross-venue directions.',
        'metrics': 'Known-link hit/recall at k=1,3,5,10; event-macro query hit rate. Unlabelled cross-pairs are not negatives.',
        'reference': 'External project author audit labels, not independent human gold or contract proof.',
        'candidate_scope': 'All unique opposite-venue markets occurring in this enriched audit fixture.',
        'primary_contrast': 'Adding parent event context to the same model, at fixed k.',
        'excluded_inputs': ['reference labels and reasons', 'prices and outcomes', 'close timestamps'],
        'model': MODELS['dense'], 'device': 'cpu', 'seed': 0,
        'pair_count': len(pairs), 'market_counts': {v:len(rs) for v,rs in markets.items()}}
    save('run_manifest.json', plan)  # Commit the comparisons before first inference.
    outputs, truncations = [], {}
    tok, model = load_model('dense')
    arrays = {}
    started = time.monotonic()
    for view in ['title', 'event_title']:
        source_texts = [text_view(r, view) for r in markets['poly']]
        target_texts = [text_view(r, view) for r in markets['kalshi']]
        texts = source_texts + target_texts
        n = len(source_texts)
        # Identical fixed lexical construction in both views.
        sims = []
        for kwargs in [dict(analyzer='word', ngram_range=(1,2), token_pattern=r'(?u)\b\w+\b'),
                       dict(analyzer='char_wb', ngram_range=(3,5))]:
            vec = TfidfVectorizer(sublinear_tf=True, **kwargs)
            matrix = vec.fit_transform(texts)
            sims.append((matrix[:n] @ matrix[n:].T).toarray())
        outputs += evaluate((sims[0]+sims[1])/2, markets, pairs, 'lexical', view)
        encoded, stats = encode_dense(texts, tok, model)
        arrays[view] = encoded
        truncations[view] = stats
        outputs += evaluate(encoded[:n] @ encoded[n:].T, markets, pairs, 'dense', view)
        print('Completed', view, stats, flush=True)
    np.savez_compressed(OUT/'embeddings.npz', **arrays)
    save('results.json', outputs)
    save('summary.json', [{k:v for k,v in r.items() if k != 'queries'} for r in outputs])
    plan.update(completed_at_utc=datetime.now(timezone.utc).isoformat(),
                inference_and_scoring_seconds=time.monotonic()-started,
                tokenizer_stats=truncations)
    save('run_manifest.json', plan)
    print('Completed all fixed retrieval comparisons.', flush=True)


if __name__ == '__main__':
    main()

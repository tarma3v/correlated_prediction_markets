#!/usr/bin/env python3
"""Post-hoc overlap and candidate-union diagnostics from saved results only."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
OLD = ROOT/'redesign/retrieval'
SPECS = {
    'TFIDF': (OLD/'lexical_event_title_pair_ranks.json', OLD/'top1_candidates.json', 'lexical'),
    'MiniLM': (OLD/'dense_event_title_pair_ranks.json', OLD/'top1_candidates.json', 'dense'),
    'E5': (OUT/'e5_small_v2_event_title_pair_ranks.json', OUT/'top1_candidates.json', 'e5_small_v2'),
    'BGE': (OUT/'bge_small_en_v1_5_event_title_pair_ranks.json', OUT/'top1_candidates.json', 'bge_small_en_v1_5'),
}
def load(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def pair_key(row): return row['poly_id'], row['kalshi_ticker']
def pair_ids(keys):
    return [{'poly_id':p, 'kalshi_ticker':k} for p,k in sorted(keys)]

rank_rows = {name:load(spec[0]) for name,spec in SPECS.items()}
labels = {pair_key(r):r['reference_label'] for r in rank_rows['TFIDF']}
assert len(labels)==493
assert Counter(labels.values())=={'same':461,'different':27,'unsure':5}
for name,rows in rank_rows.items():
    assert len(rows)==len(labels)
    assert {pair_key(r):r['reference_label'] for r in rows}==labels
known = {pair for pair,label in labels.items() if label=='same'}
result = {
    'created_at_utc':datetime.now(timezone.utc).isoformat(),
    'analysis':'Diagnostic post-hoc analysis of fixed saved event_title retrieval outputs. No inference, training, threshold tuning, or independent gold annotation.',
    'error_definition':'For a reference pair labelled same by the external author, its opposite-venue market has rank > 1 for the specified direction.',
    'ensemble_definition':'Deduplicated union of each component model\'s top-1 candidate per query. No reranking, score averaging or final classification.',
    'scope':'461 known-link queries per direction, one reference same link per query; each searches 493 opposite-venue candidates. Candidate budgets below cover those 461 queries only.',
    'limits':'External non-exhaustive labels; different-at-top1 is a labelled-pair retrieval diagnostic, not classification false-positive rate. Descriptive post-hoc gains are not independent confirmation or proof of statistical significance.',
    'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted({p for spec in SPECS.values() for p in spec[:2]})},
    'script_sha256':sha(Path(__file__)), 'directions':{},
}
for direction,venue,rank_key,source_pos,target_pos in [
    ('poly_to_kalshi','poly','kalshi_rank_for_poly',0,1),
    ('kalshi_to_poly','kalshi','poly_rank_for_kalshi',1,0),
]:
    expected = {p[source_pos]:p[target_pos] for p in known}
    assert len(expected)==461
    errors = {name:{pair_key(r) for r in rows if r['reference_label']=='same' and r[rank_key]>1}
              for name,rows in rank_rows.items()}
    top1 = {}
    for name,(_,path,method) in SPECS.items():
        view = [r for r in load(path) if r['method']==method and r['view']=='event_title' and r['source_venue']==venue]
        assert len(view)==1
        queries=view[0]['queries']
        assert len(queries)==461 and {r['id'] for r in queries}==set(expected)
        top1[name]={r['id']:r['top1_id'] for r in queries}
        assert {p for p in known if top1[name][p[source_pos]]!=p[target_pos]}==errors[name]
    pairs=[]
    for a,b in itertools.combinations(SPECS,2):
        joint=errors[a]&errors[b]
        pairs.append({'models':[a,b], 'joint_error_count':len(joint),
                      'joint_error_pairs':pair_ids(joint),
                      'only_first_model_error_count':len(errors[a]-errors[b]),
                      'only_second_model_error_count':len(errors[b]-errors[a]),
                      'union_top1_known_link_hits':461-len(joint)})
    groups=[]
    for group in list(itertools.combinations(SPECS,2))+[tuple(SPECS)]:
        candidates={q:{top1[m][q] for m in group} for q in expected}
        hits=sum(expected[q] in candidates[q] for q in expected)
        joint=set.intersection(*(errors[m] for m in group))
        assert hits==461-len(joint)
        groups.append({'models':list(group), 'known_link_hits':hits, 'known_link_queries':461,
                       'known_link_hit_rate':hits/461,
                       'candidate_count_total':sum(map(len,candidates.values())),
                       'candidates_per_query_mean':sum(map(len,candidates.values()))/461,
                       'candidates_per_query_max':max(map(len,candidates.values())),
                       'candidate_count_histogram':dict(sorted(Counter(map(len,candidates.values())).items())),
                       'remaining_error_pairs':pair_ids(joint)})
    base=next(g for g in groups if g['models']==['TFIDF','MiniLM'])
    full=groups[-1]
    result['directions'][direction]={
        'models':{name:{'known_link_errors_at1':len(errors[name]),
                         'known_link_hits_at1':461-len(errors[name]),
                         'known_link_error_pairs':pair_ids(errors[name]),
                         'different_reference_pairs':27,
                         'different_reference_pairs_at1':sum(r['reference_label']=='different' and r[rank_key]==1 for r in rows),
                         'unsure_reference_pairs_at1':sum(r['reference_label']=='unsure' and r[rank_key]==1 for r in rows)}
                  for name,rows in rank_rows.items()},
        'pairwise_errors':pairs, 'candidate_unions':groups,
        'four_models_vs_tfidf_minilm':{
            'additional_known_link_hits':full['known_link_hits']-base['known_link_hits'],
            'additional_candidates_total':full['candidate_count_total']-base['candidate_count_total'],
            'additional_models':['E5','BGE'],
        },
    }
(OUT/'error_overlap.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
for direction,rows in result['directions'].items():
    print(direction)
    for group in rows['candidate_unions']:
        print('+'.join(group['models']), group['known_link_hits'], '/461',
              group['candidate_count_total'],'candidates;', round(group['candidates_per_query_mean'],4),'per query')
    print('Additional E5+BGE:',rows['four_models_vs_tfidf_minilm'])

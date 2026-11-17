"""Audit the stored NLI decisions on common-scalar threshold pairs."""
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research'))
from verify_findings import key, mapped_type, scalar, true_at

FORBIDS = {
    'exclusion_candidate': {'11'},
    'equivalence_candidate': {'10', '01'},
    'a_implies_b_candidate': {'10'},
    'b_implies_a_candidate': {'01'},
    'abstain': set(),
}


def possible_states(a, b):
    op_a, t_a, template_a = scalar(a)
    op_b, t_b, template_b = scalar(b)
    assert template_a == template_b
    assert all(a[k] == b[k] for k in ('event_id', 'secondary', 'close_time', 'expected_expiration_time'))
    lo, hi = sorted((t_a, t_b))
    # Each open interval and each endpoint has a representative.
    grid = [lo-1, lo, (lo+hi)/2, hi, hi+1]
    return {
        f'{int(true_at(x, op_a, t_a))}{int(true_at(x, op_b, t_b))}': str(x)
        for x in grid
    }


def summary(rows):
    calls = [r for r in rows if r['decision'] != 'abstain']
    errors = sum(bool(r['violations']) for r in calls)
    return dict(pairs=len(rows), calls=len(calls), errors=errors,
                coverage=len(calls)/len(rows), risk=errors/len(calls) if calls else None)


def main():
    hashes = {}

    def read(rel):
        raw = (ROOT / rel).read_bytes()
        hashes[rel] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    markets = {r['id']: r for r in read('pilot/markets.json')}
    predictions = read('extension/nlp/corpus_nli_predictions.json')
    templates = {key(r):r for r in read('extension/retrieval/results/threshold_candidates.json')}
    selected = [p for p in predictions if key(p) in templates]
    assert len({key(p) for p in selected}) == len(selected) == 839
    result = []
    table = []
    for cutoff in (0.5, 0.8, 0.9, 0.95, 0.99):
        rows = []
        strata = defaultdict(list)
        for p in selected:
            a, b = [markets[p[x]] for x in ('a', 'b')]
            series = a['id'].split('-')[0]
            assert series == b['id'].split('-')[0]
            witnesses = possible_states(a, b)
            decision = mapped_type(p, cutoff, 0.1)
            if cutoff == 0.8:
                assert decision == p['nli_candidate_type']
            violations = sorted(FORBIDS[decision].intersection(witnesses))
            row = dict(cutoff=cutoff, series=series, a=p['a'], b=p['b'], decision=decision,
                       violations=','.join(violations), counterexamples=','.join(witnesses[s] for s in violations))
            rows.append(row)
            strata[series].append(row)
        by_series = {s:summary(rr) for s,rr in sorted(strata.items())}
        loo = {s:summary([r for r in rows if r['series'] != s])['risk'] for s in by_series}
        observed = [v['risk'] for v in by_series.values() if v['risk'] is not None]
        result.append(dict(cutoff=cutoff, **summary(rows), series_with_calls=len(observed),
                           macro_series_risk=mean(observed) if observed else None, by_series=by_series,
                           leave_one_series_out=loo, wrong_by_type=dict(Counter(r['decision'] for r in rows if r['violations']))))
        table.extend(rows)
    with (HERE/'decisions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(table)
    (HERE/'results.json').write_text(json.dumps({'input_sha256':hashes,'thresholds':result},indent=2)+'\n')
    for r in result:
        print(r['cutoff'], r['errors'], r['calls'], r['coverage'], r['risk'],r['macro_series_risk'],r['series_with_calls'],r['wrong_by_type'])
    print(result[1]['by_series'])


if __name__ == '__main__':
    main()

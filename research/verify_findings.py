#!/usr/bin/env python3
"""Independent checks of saved outputs; standard library, no inference/network.

Reconstructs NLI mapping, parses scalar predicates directly from market.primary,
checks both-YES witnesses, and reports exact title-containment definitions.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / 'verified_findings.json'
used = {}
def load(rel):
    raw = (ROOT / rel).read_bytes()
    used[rel] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)
def text(rel):
    raw = (ROOT / rel).read_bytes()
    used[rel] = hashlib.sha256(raw).hexdigest()
    return ' '.join(raw.decode('utf-8').split())
def digest(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
def key(row):
    return tuple(sorted((row['a'], row['b'])))

def mapped_type(row, threshold, margin):
    ab, ba = row['a_to_b'], row['b_to_a']
    for scores in [ab, ba]:
        assert set(scores) == {'entailment', 'neutral', 'contradiction'}
        assert all(0 <= p <= 1 for p in scores.values())
        assert abs(sum(scores.values()) - 1) < 1e-5
    c = (ab['contradiction'] + ba['contradiction']) / 2
    e1, e2 = ab['entailment'], ba['entailment']
    if c >= threshold and c - max(e1, e2) >= margin:
        return 'exclusion_candidate'
    if min(e1, e2) >= threshold and min(e1, e2) - c >= margin:
        return 'equivalence_candidate'
    if e1 >= threshold and e1 - c >= margin:
        return 'a_implies_b_candidate'
    if e2 >= threshold and e2 - c >= margin:
        return 'b_implies_a_candidate'
    return 'abstain'

NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
COMPARISON = re.compile(r'\b(more than|above|at least)\s+(' + NUMBER + r')(?![\w.,])', re.I)
def scalar(row):
    matches = list(COMPARISON.finditer(row['primary']))
    assert len(matches) == 1, row['id']
    m = matches[0]
    op = '>=' if m.group(1).lower() == 'at least' else '>'
    bound = Decimal(m.group(2).replace(',', ''))
    template = row['primary'][:m.start(2)] + '<THRESHOLD>' + row['primary'][m.end(2):]
    return op, bound, template

def true_at(x, op, bound):
    return x > bound if op == '>' else x >= bound


def main():
    markets_list = load('pilot/markets.json')
    markets = {r['id']: r for r in markets_list}
    predictions = load('extension/nlp/corpus_nli_predictions.json')
    manifest = load('extension/nlp/corpus_run_manifest.json')
    candidates = load('pilot/results/candidates.json')
    conditional = load('extension/nlp/conditional_consistency.json')
    templates = load('extension/retrieval/results/threshold_candidates.json')
    extractions = {r['id']: r for r in load('extension/retrieval/results/extractions.json')}
    assert digest('pilot/markets.json') == manifest['input_hash']
    assert digest('pilot/results/candidates.json') == manifest['candidate_hash']
    assert digest('extension/nlp/score_candidate_pool.py') == manifest['script_hash']
    assert len(predictions) == manifest['n_pairs'] == len(candidates) == 1188
    assert manifest['directional_inferences'] == 2 * len(predictions) == 2376
    assert len({key(r) for r in predictions}) == len(predictions)
    assert {key(r) for r in candidates} == {key(r) for r in predictions}
    for p in predictions:
        assert mapped_type(p, manifest['threshold'], manifest['dominance_margin']) == p['nli_candidate_type']
    assert dict(Counter(r['nli_candidate_type'] for r in predictions)) == manifest['output_counts']
    by_template = {key(r): r for r in templates}
    assert len(by_template) == len(templates)
    stored = {key(r): r for r in conditional['records']}
    expected_keys = {key(r) for r in predictions} & set(by_template)
    assert set(stored) == expected_keys and len(stored) == len(conditional['records']) == 839
    groups, conflicts, checked, examples = set(), [], 0, []
    for p in predictions:
        pair = key(p)
        if pair not in expected_keys:
            continue
        tr, sr = by_template[pair], stored[pair]
        a, b = markets[p['a']], markets[p['b']]
        oa, ta, pa = scalar(a)
        ob, tb, pb = scalar(b)
        # Match actual retained predicates and non-threshold context, not titles.
        assert pa == pb
        assert (a['venue'], a['event_id'], a['secondary'], a['close_time'], a['expected_expiration_time']) == (
            b['venue'], b['event_id'], b['secondary'], b['close_time'], b['expected_expiration_time'])
        ea, eb = extractions[a['id']], extractions[b['id']]
        assert ea['constraints'] == eb['constraints']
        assert ea['threshold_masked_template'] == pa == ea['constraints']['template']
        assert ea['primary_evidence'] == a['primary'] and eb['primary_evidence'] == b['primary']
        group = hashlib.sha256(json.dumps(ea['constraints'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        assert group == ea['group_key'] == eb['group_key'] == tr['group_key'] == sr['template_group']
        for side in ['a', 'b']:
            op, bound, _ = scalar(markets[tr[side]])
            assert op == tr['operator_' + side] and bound == Decimal(tr['threshold_' + side])
        with localcontext() as ctx:
            ctx.prec = 60
            x = max(ta, tb) + Decimal(1)
        assert x == Decimal(sr['scalar_both_yes_witness'])
        assert true_at(x, oa, ta) and true_at(x, ob, tb)
        is_conflict = p['nli_candidate_type'] == 'exclusion_candidate'
        assert sr['nli_candidate_type'] == p['nli_candidate_type']
        assert sr['conflict_in_scalar_scope'] is is_conflict
        assert sr['human_gold'] is False and sr['unconditional_contract_certified'] is False
        groups.add(group); checked += 1
        if is_conflict:
            conflicts.append(pair)
            if len(examples) < 3:
                examples.append({'a': a['id'], 'b': b['id'], 'operator_a': oa, 'threshold_a': str(ta),
                    'operator_b': ob, 'threshold_b': str(tb), 'x_both_yes': str(x),
                    'mean_contradiction_score': (p['a_to_b']['contradiction'] + p['b_to_a']['contradiction']) / 2})
    assert checked == conditional['matched_pairs'] == 839
    assert len(groups) == conditional['event_template_groups'] == 19
    assert len(conflicts) == conditional['exclusion_conflicts'] == 325
    reference_paths = ['redesign/retrieval/reference_pairs.json', 'redesign/retrieval/markets.json']
    reference_available = all((ROOT / rel).exists() for rel in reference_paths)
    positive, containment = [], {}
    if reference_available:
        refs = load('redesign/retrieval/reference_pairs.json')
        positive = [r for r in refs if r['label'] == 'same']
        external_markets = load('redesign/retrieval/markets.json')
        em = {v: {r['id']: r for r in rs} for v, rs in external_markets.items()}
        for p in positive:
            assert p['poly_title'] == em['poly'][p['poly_id']]['title']
            assert p['kalshi_title'] == em['kalshi'][p['kalshi_ticker']]['title']
            assert p['poly_title'] and p['kalshi_title']
        methods = {'literal_case_sensitive': lambda s: s,
                   'literal_lowercase': lambda s: s.lower(),
                   'nfkc_casefold_whitespace': lambda s: ' '.join(unicodedata.normalize('NFKC', s).casefold().split()),
                   'lowercase_word_tokens': lambda s: ' '.join(re.findall(r'\w+', s.lower()))}
        containment = {name: sum(fn(r['poly_title']) in fn(r['kalshi_title']) for r in positive)
                       for name, fn in methods.items()}
        assert len(positive) == 461 and containment['literal_lowercase'] == 285
    else:
        print('Title containment unavailable: run python3 scripts/fetch_reference_inputs.py to restore pinned reference inputs.')
    terms_manifest = load('extension/terms/manifest.json')
    download_hashes = {r['path']: r.get('sha256') for r in terms_manifest['downloads']}
    pdf_hash_checks = {}
    for name in ['KXCPIYOY_terms.pdf', 'KXLCPIMAXYOY_terms.pdf', 'KXCPI_terms.pdf']:
        rel = 'extension/terms/' + name
        if (ROOT / rel).exists():
            actual = digest(rel)
            assert actual == download_hashes[name]
            used[rel] = actual
            pdf_hash_checks[name] = 'matches_saved_download_manifest'
        else:
            pdf_hash_checks[name] = 'not_distributed_locally'
    clauses = {}
    for filename, phrases in {
        'KXCPIYOY_terms.txt': ['^(13/12)', 'three months', '8:29 AM ET'],
        'KXLCPIMAXYOY_terms.txt': ['fourteen days', 'six months', 'one-month', 'year-over-year'],
        'KXCPI_terms.txt': ['8:29 AM ET']}.items():
        rel = 'extension/terms/' + filename
        if not (ROOT / rel).exists():
            clauses[filename] = {'status': 'not_checked_local_extraction_not_distributed'}
            continue
        value = text(rel)
        assert all(phrase in value for phrase in phrases), filename
        clauses[filename] = {'status': 'phrases_verified', 'phrase_checks': len(phrases)}
    assert '8:25 AM ET' in markets['KXCPI-26OCT-T0.9']['secondary']
    assert 'more than 5.0%' in markets['KXCPIYOY-26DEC-T5.0']['primary']
    assert 'at least 5%' in markets['KXLCPIMAXYOY-27-P5']['primary']
    political = load('redesign/cards/political_inputs.json')['kalshi_out']
    for phrase in ['solely because they have died', 'last traded price', 'fair allocation']:
        assert phrase in political
    raw_departure = 'redesign/discovery/political/kalshi_out.json'
    if (ROOT / raw_departure).exists():
        raw_market = load(raw_departure)['market']
        assert raw_market['ticker'] == 'KXTRUMPOUT27-27-DJT'
        assert political == raw_market['rules_primary'] + '\n' + raw_market['rules_secondary']
    audit_record = next(r for r in terms_manifest['artifacts'] if r['path'] == 'AUDIT_RU.md')
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'all_assertions_passed': True,
        'method': 'Independent probability-to-type reconstruction plus direct source predicate parsing and Decimal witness evaluation; no model rerun.',
        'deberta': {'pairs': len(predictions), 'directional_inferences': 2376, 'reported_truncations': manifest['truncated_inputs'],
            'mapping_recomputed': len(predictions), 'conditional_pairs': checked, 'template_groups': len(groups),
            'exclusion_conflicts': len(conflicts), 'conflict_fraction_among_conditional_pairs': len(conflicts) / checked,
            'both_yes_witnesses_checked': checked, 'examples': examples,
            'scope': 'Common unrestricted scalar, matched templates, lower-bound predicates, binary rule-following settlement. Not human-gold accuracy or unconditional contract certification.'},
        'title_containment': {'status': 'verified' if reference_available else 'unavailable',
            'restore_command': None if reference_available else 'python3 scripts/fetch_reference_inputs.py',
            'positive_pairs': len(positive) if reference_available else None, 'counts': containment if reference_available else None,
            'headline_formula': "poly_title.lower() in kalshi_title.lower(), restricted to label == 'same'",
            'headline_fraction': containment['literal_lowercase'] / len(positive) if reference_available else None,
            'scope': 'Text overlap in an author-selected snapshot; not retrieval accuracy, equivalence or absence of difficult negatives.'},
        'source_clauses': {'pdf_hash_checks': pdf_hash_checks, 'terms_text_checks': clauses, 'cpi_api_0825_vs_template_0829': True,
            'yoy_strict_above_vs_annual_at_least_api': True, 'kalshi_departure_nonbinary_branch_in_saved_text': True,
            'scope': 'Textual discrepancies and explicit branch verified; current documents not proved to be the historical governing version; no unconditional payout counterexample inferred.'},
        'terms_audit_editorial_update': {'historical_manifest_sha256': audit_record['sha256'],
            'current_markdown_sha256': digest('extension/terms/AUDIT_RU.md'),
            'note': 'Concluding section updated; source documents and historical manifest remain unchanged.'},
        'input_sha256': used, 'validator_sha256': digest('research/verify_findings.py')}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['all_assertions_passed', 'deberta', 'title_containment']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

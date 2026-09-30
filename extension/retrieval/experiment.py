#!/usr/bin/env python3
"""Offline retrieval sensitivity + conservative threshold candidate generator.
Reads the frozen pilot; writes only under this extension. No model or API calls.
All rule-generated links remain conditional candidates, not certified contracts.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PILOT = ROOT.parents[1] / 'pilot'
OPERATORS = {'more than': '>', 'above': '>', 'at least': '>='}
NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
THRESHOLD_RE = re.compile(r'\b(?P<operator>more than|above|at least)\s+(?P<number>' + NUMBER + r')(?![\w.,])', re.I)
UNSUPPORTED_RE = re.compile(r'\b(not|unless|except|between|below|less than|at most|no more than)\b', re.I)
POSITIVE_CONTROLS = {'same_title_thresholds', 'strict_thresholds'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def exact_decimal(value):
    # Require lexical decimal strings to avoid silently promoting lossy floats.
    if not isinstance(value, str):
        raise ValueError('Exact lexical decimal string required')
    if not re.fullmatch(NUMBER + r'(?:[eE][+-]?\d+)?', value):
        raise ValueError('Malformed decimal spelling')
    try:
        result = Decimal(value.replace(',', ''))
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    if not result.is_finite():
        raise ValueError('Nonfinite decimal')
    return result


def implies(operator_a, threshold_a, operator_b, threshold_b):
    """Set inclusion over real x; unknown discrete-domain refinements excluded."""
    if operator_a not in ('>', '>=') or operator_b not in ('>', '>='):
        raise ValueError('Unsupported comparator')
    a, b = exact_decimal(threshold_a), exact_decimal(threshold_b)
    return a > b or (a == b and (operator_a == '>' or operator_b == '>='))


def extract(record, source_metadata=None):
    text = record.get('primary', '')
    result = {'id': record['id'], 'venue': record['venue'], 'event_id': record.get('event_id'),
              'primary_evidence': text, 'secondary_evidence': record.get('secondary', ''),
              'source_api_url': record.get('source_api_url'), 'status': 'abstain', 'abstain_reasons': []}
    if not record.get('event_id'):
        result['abstain_reasons'].append('missing_event_id')
    if not text.startswith('If ') or not text.endswith('then the market resolves to Yes.'):
        result['abstain_reasons'].append('unsupported_resolution_sentence_shape')
    if UNSUPPORTED_RE.search(text):
        result['abstain_reasons'].append('unsupported_condition_or_comparator')
    matches = list(THRESHOLD_RE.finditer(text))
    if len(matches) != 1:
        result['abstain_reasons'].append(f'expected_one_numeric_comparison_found_{len(matches)}')
    if result['abstain_reasons']:
        return result
    match = matches[0]
    lexical_number = match.group('number')
    threshold = exact_decimal(lexical_number)
    # Used only as consistency evidence; coarse strike_type never overrides prose.
    floor = record.get('floor_strike')
    if floor is not None and Decimal(str(floor)) != threshold:
        result['abstain_reasons'].append('floor_strike_disagrees_with_text')
        return result
    template = text[:match.start('number')] + '<THRESHOLD>' + text[match.end('number'):]
    source = {'explicit_resolution_source': record.get('resolution_source'), 'series_settlement_sources': source_metadata}
    source_known = bool(source['explicit_resolution_source'] or source_metadata)
    # Exact template keeps units, source names, comparator wording, observation
    # period, rounding and any other numbers. Never cluster by title alone.
    constraints = {'venue': record['venue'], 'event_id': record['event_id'], 'template': template,
                   'secondary_exact': record.get('secondary', ''), 'source_constraints': source,
                   'close_time': record.get('close_time'), 'expected_expiration_time': record.get('expected_expiration_time')}
    result.update(status='parsed_candidate_only', operator=OPERATORS[match.group('operator').lower()],
                  operator_evidence=match.group('operator'), threshold_lexical=lexical_number, threshold=str(threshold),
                  threshold_span=[match.start('number'), match.end('number')], threshold_masked_template=template,
                  constraints=constraints, group_key=sha(json.dumps(constraints,sort_keys=True,ensure_ascii=False).encode()),
                  source_coverage='explicit_source_available' if source_known else 'source_not_explicit_in_structured_snapshot',
                  certification_abstain_reasons=['full_contract_terms_not_reviewed'] + ([] if source_known else ['source_incomplete']))
    return result


def generate_threshold_candidates(records, source_by_series):
    extracted=[];groups=defaultdict(list)
    for r in records:
        item=extract(r,source_by_series.get(r['id'].split('-')[0]));extracted.append(item)
        if item['status']=='parsed_candidate_only':groups[item['group_key']].append(item)
    pairs=[]
    for key,items in sorted(groups.items()):
        for a,b in itertools.combinations(items,2):
            a_to_b=implies(a['operator'],a['threshold'],b['operator'],b['threshold'])
            b_to_a=implies(b['operator'],b['threshold'],a['operator'],a['threshold'])
            relation='conditional_equivalent' if a_to_b and b_to_a else ('conditional_A_implies_B' if a_to_b else 'conditional_B_implies_A')
            pairs.append({'a':a['id'],'b':b['id'],'relation':relation,'group_key':key,'same_event':True,
                          'operator_a':a['operator'],'threshold_a':a['threshold'],'operator_b':b['operator'],'threshold_b':b['threshold'],
                          'a_implies_b':a_to_b,'b_implies_a':b_to_a,
                          'certification':'abstain_full_contract_guarantee',
                          'certification_abstain_reasons':sorted(set(a['certification_abstain_reasons']+b['certification_abstain_reasons']))})
    return extracted,pairs,groups


def main():
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pilot',type=Path,default=PILOT);parser.add_argument('--output',type=Path,default=ROOT/'results');args=parser.parse_args()
    paths=['manifest.json','markets.json','results/candidates.json','results/review_cases.json']
    input_hashes={p:sha((args.pilot/p).read_bytes()) for p in paths}
    manifest=json.loads((args.pilot/'manifest.json').read_text());records=json.loads((args.pilot/'markets.json').read_text())
    if input_hashes['markets.json']!=manifest['markets_sha256']:raise ValueError('Original normalized snapshot failed manifest hash')
    for r in manifest['requests']:
        if sha((args.pilot/r['file']).read_bytes())!=r['sha256']:raise ValueError('Raw snapshot mismatch: '+r['file'])
    sources={}
    for ticker in ['KXCPIYOY','KXLCPIMAXYOY']:
        metadata=json.loads((args.pilot/'raw'/f'metadata_{ticker}.json').read_text())['response']['series']
        sources[ticker]=metadata.get('settlement_sources')
    extracted,threshold_pairs,groups=generate_threshold_candidates(records,sources)
    index={r['id']:i for i,r in enumerate(records)}
    template_set={tuple(sorted((index[r['a']],index[r['b']]))) for r in threshold_pairs}
    variants={'title':lambda r:r['title'],'rules':lambda r:r['primary']+'\n'+r['secondary'],
              'title_rules':lambda r:r['title']+'\n'+r['primary']+'\n'+r['secondary']}
    scores={};ordered={}
    for name,fn in variants.items():
        texts=[fn(r) for r in records]
        w=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,token_pattern=r'(?u)\b\w+\b').fit_transform(texts)
        c=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True).fit_transform(texts)
        sim=(0.5*(w@w.T)+0.5*(c@c.T)).toarray();np.fill_diagonal(sim,-1.0)
        scores[name]=sim;ordered[name]=np.argsort(-sim,axis=1,kind='stable')
    cases=json.loads((args.pilot/'results/review_cases.json').read_text())
    original_candidates=json.loads((args.pilot/'results/candidates.json').read_text())
    original_set={tuple(sorted((index[c['a']],index[c['b']]))) for c in original_candidates}
    def describe(edges):
        same=sum(records[i]['venue']==records[j]['venue'] and records[i]['event_id']==records[j]['event_id'] for i,j in edges)
        hits={c['case_id']:tuple(sorted((index[c['a']['id']],index[c['b']['id']]))) in edges for c in cases}
        hit_count=sum(hits[c] for c in POSITIVE_CONTROLS)
        return {'candidate_pairs':len(edges),'same_event_pairs':same,'cross_event_pairs':len(edges)-same,
                'fraction_of_all_pairs':len(edges)/(len(records)*(len(records)-1)//2),
                'exploratory_case_presence':hits,
                'positive_control_hit_count':hit_count,'positive_control_count':len(POSITIVE_CONTROLS),
                'positive_control_retrieval_hit_rate':hit_count/len(POSITIVE_CONTROLS)}
    sweep=[]
    for k in [1,5,10,20,50]:
        sets={}
        for name in variants:
            sets[name]={tuple(sorted((i,int(j)))) for i in range(len(records)) for j in ordered[name][i,:k] if scores[name][i,j]>0}
        union=set().union(*sets.values())
        if k==5 and union!=original_set:
            raise ValueError('Top-5 candidate set failed exact original-pilot reproduction')
        sets['text_union']=union;sets['text_union_plus_threshold']=union|template_set
        sweep.append({'top_k':k,'variants':{name:describe(pairs) for name,pairs in sets.items()},
                      'additional_threshold_pairs':len(template_set-union)})
    detailed_cases=[]
    for c in cases:
        i,j=index[c['a']['id']],index[c['b']['id']]
        detailed_cases.append({'case_id':c['case_id'],'a':c['a']['id'],'b':c['b']['id'],'provisional_relation':c['provisional_relation'],
                              'used_as_positive_control':c['case_id'] in POSITIVE_CONTROLS,'threshold_candidate_present':tuple(sorted((i,j))) in template_set,
                              'source_review_note':c['note_ru'],
                              'retrieval':{name:{'similarity':round(float(s[i,j]),6),'rank_b_for_a':int(np.flatnonzero(ordered[name][i]==j)[0])+1,
                                                 'rank_a_for_b':int(np.flatnonzero(ordered[name][j]==i)[0])+1} for name,s in scores.items()}})
    summary={'created_at_utc':datetime.now(timezone.utc).isoformat(),'input_hashes':input_hashes,
             'dependencies':{p:importlib.metadata.version(p) for p in ['numpy','scipy','scikit-learn']},
             'top5_original_candidate_set_reproduced':True,'markets':len(records),'possible_pairs':len(records)*(len(records)-1)//2,
             'positive_controls':sorted(POSITIVE_CONTROLS),'metric_warning':'Post-hoc selected two same-event textual controls. Hit rate is NOT population recall. Other exploratory case presences are neither gold true/false positives nor accuracy.',
             'threshold_generator':{'extraction_status':dict(Counter(r['status'] for r in extracted)), 'groups':len(groups),
                                    'groups_with_multiple_markets':sum(len(v)>1 for v in groups.values()),
                                    'conditional_candidates':len(threshold_pairs),'certified_contract_implications':0,
                                    'candidate_budget':describe(template_set),
                                    'scope':'Same-event controls only; full contract/source review remains required. No cross-event or cross-platform discoveries.'},
             'sweep':sweep}
    write_json(args.output/'summary.json',summary);write_json(args.output/'extractions.json',extracted)
    write_json(args.output/'threshold_candidates.json',threshold_pairs);write_json(args.output/'exploratory_cases.json',detailed_cases)
    if input_hashes!={p:sha((args.pilot/p).read_bytes()) for p in paths}:raise ValueError('Original pilot files changed during run')
    print(json.dumps({'markets':len(records),'threshold_candidates':len(threshold_pairs),'extraction_status':summary['threshold_generator']['extraction_status'],
                      'topk':[(s['top_k'],s['variants']['text_union']['candidate_pairs'],s['variants']['text_union']['positive_control_hit_count'],
                               s['variants']['text_union_plus_threshold']['candidate_pairs'],s['variants']['text_union_plus_threshold']['positive_control_hit_count']) for s in sweep]},indent=2))

if __name__=='__main__':main()

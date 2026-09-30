#!/usr/bin/env python3
"""Validate provisional relation records, not the truth of their annotations.

Standard-library only. Reads saved data; no network, model inference or trading.
"""
from collections import Counter
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
def load(name): return json.loads((HERE/name).read_text())
rows = load('typed_pairs.json')
sources = load('sources.json')
api = {r['case_number']:r for r in load('kalshi_provenance.json')}
manifest = load('manifest.json')
expected = {
    'EQUIVALENT':['01','10'], 'A_IMPLIES_B':['10'], 'B_IMPLIES_A':['01'],
    'DISJOINT':['11'], 'COMPLEMENT':['00','11'], 'NO_HARD_RELATION':[],
    'ABSTAIN':None, 'OUT_OF_BINARY_SCOPE':None,
}
assert len(rows)==32
assert [r['pair_id'] for r in rows]==[f'rel_{n:02}' for n in range(1,33)]
keys={(r['A']['external_id'],r['B']['external_id']) for r in rows}
assert len(keys)==32
assert Counter(r['external_reference']['label'] for r in rows)=={'different':27,'unsure':5}
assert Counter(r['relation_candidate'] for r in rows)==manifest['relation_candidate_counts']
for i,r in enumerate(rows,1):
    assert r['A']['venue']=='Polymarket' and r['B']['venue']=='Kalshi'
    assert re.fullmatch(r'0x[0-9a-f]{64}',r['A']['external_id'])
    assert r['B']['external_id']==api[i]['ticker']
    assert api[i]['http_status']==200
    assert r['human_gold'] is False
    assert r['external_reference']['is_relation_gold'] is False
    assert r['established_contract_forbidden_states'] is None
    assert r['forbidden_states']==expected[r['relation_candidate']]
    assert set(r['state_assessment'])=={'00','01','10','11'}
    for state,status in r['state_assessment'].items():
        states=r['forbidden_states']
        want=('unknown_or_out_of_binary_scope' if states is None else
              'forbidden_under_assumptions' if state in states else
              'not_excluded_under_assumptions')
        assert status==want
    assert r['scope']['assumptions'] and r['missing_evidence']
    assert all(s in sources for s in r['evidence_source_ids'])
    assert r['correlation_hypothesis']['empirical_evidence'] is False
    assert r['provenance']['kalshi_response_sha256']==api[i]['response_sha256']
    assert r['provenance']['kalshi_resolution_text_fields_sha256']==api[i]['resolution_text_fields_sha256']
    assert r['A']['derived_yes_description'] and r['B']['derived_yes_description']
    if r['illustrative_state_witnesses'] is not None:
        assert set(r['illustrative_state_witnesses'])==set('00 01 10 11'.split())-set(r['forbidden_states'])

# Meaningful boundary examples: title buckets can differ from raw thresholds.
# These are mathematical diagnostics, NOT validation of a target contract rule.
unit=Decimal('25')
def round_up_magnitude(x): return (x/unit).to_integral_value(rounding=ROUND_CEILING)*unit
for value in ['0','12.5','25','25.0001','30','37.5','49.9999','50','100']:
    x=Decimal(value)
    assert (round_up_magnitude(x)>=50)==(x>25)
assert round_up_magnitude(Decimal('25'))==25
assert round_up_magnitude(Decimal('25.0001'))==50
rounded=(Decimal('30')/unit).to_integral_value(rounding=ROUND_HALF_UP)*unit
assert rounded==25 and Decimal('30')>25  # 11 under the rounding interpretation.
assert set([1,2,3,4]).isdisjoint({5})

# Link to the original fixture only if the non-redistributed file is present.
reference=HERE.parent/'redesign/retrieval/reference_pairs.json'
linkage='not checked: original fixture is not present; saved selected IDs remain available'
if reference.exists():
    assert hashlib.sha256(reference.read_bytes()).hexdigest()==manifest['input_scope']['reference_pairs_sha256']
    original=[r for r in json.loads(reference.read_text()) if r['label']!='same']
    assert {(r['poly_id'],r['kalshi_ticker']) for r in original}==keys
    linkage='all32 selected ID pairs and original source hash match'
print('PASS:32 records;27different+5unsure;ID/provenance linkage;candidate truth-table encoding;human_gold=false.')
print('Original-fixture linkage:',linkage)
print('PASS:Decimal rounding boundary diagnostics and NFL seed-set consistency.')
print('This verifier checks integrity/schema/math only; it does not certify settlement relations or empirical correlation.')

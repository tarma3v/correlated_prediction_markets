#!/usr/bin/env python3
"""Build one transparent provisional cross-platform evidence packet offline."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
POLY_URL='https://polymarket.com/event/core-cpi-yoy-september-2026/will-core-cpi-yoy-be-2pt3-in-september-2026'
kalshi=json.loads((ROOT/'kalshi_2pt2.json').read_text())
k=kalshi['response']['market']
assert k['ticker']=='KXCPICOREYOY-26SEP-T2.2'
assert 'more than 2.2%' in k['rules_primary']
assert 'twelve months ending September 2026' in k['rules_primary']
assert 'federal government shutdown' in k['rules_secondary']
rules_file=(ROOT/'polymarket_indexed_rules.txt').read_text()
rules=rules_file.split('\n\n',1)[1].strip()
assert 'period ending in September 2026' in rules
assert 'one decimal point' in rules
assert 'most recent previous month with available data' in rules
assert 'Experimental AI-generated' not in rules
assert POLY_URL in (ROOT/'polymarket_indexed_identity.txt').read_text()
pair={
 'pair_id':'poly_core_cpi_september_exact_2p3__kalshi_gt2p2',
 'built_at_utc':datetime.now(timezone.utc).isoformat(),
 'status':'provisional_cross_platform_candidate__current_polymarket_rules_not_verified',
 'polymarket':{
  'public_market_slug':'will-core-cpi-yoy-be-2pt3-in-september-2026',
  'event_slug':'core-cpi-yoy-september-2026',
  'url':POLY_URL,'numeric_market_id':None,'condition_id':None,
  'identity_limit':'Exact public slug corroborated by official-page search hit; numeric market/condition IDs not retrieved.',
  'observed_outcome_label':'2.3%','predicate_under_normal_release':'September 2026 core CPI YoY, published one-decimal value == 2.3%',
  'rules_evidence_file':'polymarket_indexed_rules.txt',
  'rules_acquisition':'official website search-index text; metadata says crawled two weeks ago',
  'current_page_acquisition':'web-rendered official event page lists outcome2.3 but hides rule body behind Rules button',
  'snapshot_recorded_at_utc':'2026-09-28T21:20:07+00:00',
  'freshness_warning':'Snapshot-recording time is not source publication/update time. Indexed text may be stale.',
  'rule_dimensions':{'underlying':'Core CPI-U excluding food and energy','horizon':'12 months ending September 2026','seasonal_adjustment':'before seasonal adjustment (indexed rules)',
                     'source':'official monthly BLS CPI news release','precision':'published one-decimal figure',
                     'scheduled_release_as_stated':'October 14, 2026, 08:30 ET',
                     'delayed_publication':'may remain open until scheduled time of next CPI report; if still absent, use most recent previous month with data'}},
 'kalshi':{'ticker':k['ticker'],'event_ticker':k['event_ticker'],'url':kalshi['request_url'],
           'fetched_at_utc':kalshi['fetched_at_utc'],'acquisition':'direct public official API response HTTP200',
           'raw_evidence_file':'kalshi_2pt2.json','rules_primary':k['rules_primary'],'rules_secondary':k['rules_secondary'],
           'predicate_under_normal_release':'September 2026 core CPI YoY, published one-decimal value > 2.2%',
           'close_time':k['close_time'],'expected_expiration_time':k['expected_expiration_time'],
           'latest_expiration_time_at_snapshot':k['latest_expiration_time']},
 'inference':{
  'normal_release_relation':'A_implies_B; not equivalent',
  'normal_release_assumptions':['same timely September BLS core CPI series and release vintage','same one-decimal published value','outcome mapping and full contract rules consistent with retrieved text'],
  'forward_reason':'If a common published value equals2.3 then it is greater than2.2.',
  'reverse_counterexample':{'hypothetical_common_value':'2.4','polymarket_yes':False,'kalshi_yes':True},
  'exception_mismatch':'Polymarket indexed rules use a prior-month fallback after another report deadline; Kalshi secondary specifies an extension for shutdown-related delays.',
  'unconditional_contract_implication':'not certified; exception policies differ and live Polymarket rules are unverified',
  'hypothetical_exception_counterexample':{
    'is_observed_outcome':False,
    'assumptions':['government shutdown delays September data past Polymarket indexed fallback deadline','previous available month has2.3%','September eventually released as2.2% within Kalshi extension','no unobserved rules override those clauses'],
    'polymarket_yes':True,'kalshi_yes':False,
    'meaning':'Scenario compatible with the retrieved clauses defeats an unconditional implication claim; not evidence that this scenario occurred.'}},
 'limits':['No live Polymarket API contract record, numeric ID, oracle data or rule-version diff.','No full Kalshi contract_terms PDF or general rulebook audit.','No model evaluation, price comparison, arbitrage or population accuracy claims.','Single pair manually selected; one new Kalshi contract is separate from frozen286-market pilot.'],
 'request_budget':{'logical_requests_total':9,'http_local':4,'web_search_queries':3,'web_opens':2},
 'excluded_evidence':['AI-generated market summaries','FAQ forecast/accuracy marketing','prices and trading volume']
}
(ROOT/'pair.json').write_text(json.dumps(pair,ensure_ascii=False,indent=2)+'\n')
files=['probe.py','probe_manifest.json','kalshi_2pt2.json','polymarket_indexed_rules.txt','polymarket_indexed_identity.txt','polymarket_current_page_render.txt','polymarket_exact_market_failure.txt','build_pair.py','pair.json']
manifest={'written_at_utc':datetime.now(timezone.utc).isoformat(),'request_budget':pair['request_budget'],
          'artifact_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
          'original_pilot_modified':False}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Pair evidence packet written; status:',pair['status'])

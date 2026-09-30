#!/usr/bin/env python3
"""Offline discovery packet. No adjudicated labels, no model inference."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
poly={x['id']:x for x in json.loads((ROOT/'polymarket_rule_sources.json').read_text())}
registry={}
request_meta={}
for metadata_file in ['kalshi_market_manifest.json','monthly_u3_manifest.json','gaming_manifest.json','gta_historical_manifest.json']:
    metadata=json.loads((ROOT/metadata_file).read_text())
    rows=metadata if isinstance(metadata,list) else metadata.get('requests',[metadata])
    for row in rows:
        if row.get('file'):request_meta[row['file']]=row

def kalshi(ticker,filename):
    payload=json.loads((ROOT/filename).read_text())
    ms=payload.get('markets',[payload.get('market')])
    found=[m for m in ms if m and m['ticker']==ticker]
    assert len(found)==1,ticker
    m=found[0]
    # Deliberately exclude result, settlement_value, status, prices, volume.
    record={'id':'kalshi:'+ticker,'local_record_id':'kalshi:'+ticker,'external_market_id':ticker,'venue':'kalshi','title':m['title'],'primary':m['rules_primary'],'secondary':m.get('rules_secondary',''),
            'source_url':'https://external-api.kalshi.com/trade-api/v2/'+('historical/markets?tickers='+ticker if filename=='gta_historical_response.json' else 'markets/'+ticker),
            'source_kind':'official_historical_api' if filename=='gta_historical_response.json' else 'official_live_api','raw_file':filename,
            'source_sha256':hashlib.sha256((ROOT/filename).read_bytes()).hexdigest(),
            'actual_request_url':request_meta.get(filename,{}).get('url'),
            'retrieved_at_utc':request_meta.get(filename,{}).get('fetched_at_utc'),
            'yes_proposition_evidence':{'text':m['rules_primary'],'kind':'verbatim primary rule; secondary retained separately'},
            'timing_metadata':{k:m.get(k) for k in ['created_time','open_time','close_time']},
            'coverage_note':'primary/secondary fields; full series contract_terms and general rulebook not audited'}
    registry[record['id']]=record;return record['id']

def polymarket(source_id,title,outcome=None,verified_market_url=None):
    s=poly[source_id];rid='polymarket:'+source_id+('::'+outcome if outcome else '')
    registry[rid]={'id':rid,'local_record_id':rid,'external_market_id':None,'id_note':'Local alias only; not a venue-issued market ID. Identity evidence is the source URL and observed outcome label.','venue':'polymarket','title':title,'primary':s['rules'],'secondary':'','outcome_label':outcome,
                   'source_url':verified_market_url or s['url'],'source_kind':s['source_kind'],'raw_file':s['raw_file'],
                   'source_sha256':hashlib.sha256((ROOT/s['raw_file']).read_bytes()).hexdigest(),
                   'numeric_market_id':None,'condition_id':None,'crawled_as_reported':s['crawled_as_reported'],
                   'source_anomalies':s.get('source_anomalies',[]),
                   'snapshot_recorded_at_utc':s.get('snapshot_recorded_at_utc'),
                   'yes_proposition_evidence':{'text':s['rules'],'observed_outcome_binding':outcome,'kind':'verbatim indexed rules; bind only the explicitly observed outcome label'},'coverage_note':'Official-site indexed/rendered text, may be stale. Event+outcome identifiers where numeric contract ID unavailable; not Gamma API.'}
    return rid

k_recession=kalshi('KXRECSSNBER-26','markets_KXRECSSNBER.json')
k_peak=kalshi('KXNBERRECESSQ-Q1-2026','markets_KXNBERRECESSQ.json')
k_hike=kalshi('KXFEDHIKE-2-26DEC31','markets_KXFEDHIKE.json')
k_count=kalshi('KXRATEHIKE-2026-1','markets_KXRATEHIKE.json')
k_release=kalshi('KXGTA6ONTIME-26MAY26','gta_historical_response.json')
k_online=kalshi('KXGTAONLINE-GTA6ONLINE-27','gta_online.json')
p_postpone=polymarket('poly_gta_postponed','GTA 6 launch postponed?')
p_release=polymarket('poly_gta_release_oct31','GTA VI officially released in US by October 31, 2026?', 'October 31')
p_world=polymarket('poly_dodgers_ws2026','Will the Los Angeles Dodgers win the 2026 World Series?','Los Angeles Dodgers')
p_nl_la=polymarket('poly_nlcs2026','Will Los Angeles Dodgers win the 2026 National League Championship Series?','Los Angeles Dodgers')
p_nl_atl=polymarket('poly_nlcs2026','Will Atlanta Braves win the 2026 National League Championship Series?','Atlanta Braves',
                    'https://polymarket.com/event/mlb-2026-national-league-champion?marketSlug=will-atlanta-braves-win-the-2026-national-league-championship-series&outcomeIndex=1')

specs=[
('macro_recession_definition','macroeconomics',k_recession,k_peak,
 'Одно слово recession, разные операционные определения: два отрицательных GDP-квартала против квартала business-cycle peak по NBER.',
 'Не выводить логическую связь из названия или тикера. KXRECSSNBER-26 несмотря на NBER в ID использует GDP в primary; второй контракт использует решение NBER и quarter clarification.',
 ['definition_mismatch','source_mismatch','event_time_vs_announcement_time'],'no_deterministic_relation_established_from_available_text'),
('macro_hike_unit_and_window','macroeconomics',k_hike,k_count,
 'Хотя оба контракта о Fed hike, один спрашивает наличие повышения после issuance, другой — ровно одну единицу повышения за календарный год.',
 'Secondary второго считает 26–50 bp как два hikes. Нельзя заменить числом заседаний. Primary первого отсчитывает окно от issuance, не от начала 2026.',
 ['counting_unit','time_window','existence_vs_exact_count'],'relation_requires_event_window_and_unit_reasoning'),
('gaming_release_vs_postponement','gaming',k_release,p_postpone,
 'Кажущиеся противоположности: выпущена к May26 и postponed byMay26.',
 'Polymarket имеет OR: официальное объявление переноса ИЛИ фактический невыпуск. Объявление, позже отозванное, допускает иной результат, чем чистое отрицание факта выпуска. Kalshi ограничивает major platforms, Polymarket определяет публичные purchase/download и исключает early access.',
 ['announcement_vs_realization','disjunction','apparent_complement','platform_scope'],'do_not_assume_complements'),
('gaming_base_game_vs_online','gaming',p_release,k_online,
 'Похожие названия GTA VI release: base-game release в октябре против онлайн-сервиса до2027.',
 'Kalshi явно допускает bundled или separately distributed multiplayer service, независимо от имени. Polymarket basegame покупка/загрузка вUS, исключены early access/beta/leaks; даты также различаются. Не подменять different product тематической похожестью.',
 ['different_product','release_definition','time_window'],'no_deterministic_relation_established_from_available_text'),
('sports_world_to_league','sports',p_world,p_nl_la,
 'Dodgers World Series champion против Dodgers National League champion.',
 'Ожидаемая спортивная вложенность зависит от структуры турнира; payout rules содержат разные deadline/cancellation clauses. В NLCS опубликовано November31,2026 — несуществующая дата: сохранить и отправить на уточнение.',
 ['tournament_hierarchy','deadline_mismatch','invalid_calendar_date','other_outcome'],'conditional_implication_candidate_but_abstain_until_date_and_format_verified'),
('sports_world_vs_other_league_winner','sports',p_world,p_nl_atl,
 'Dodgers World Series champion против Atlanta Braves National League champion.',
 'При стандартном маршруте MLB кандидат на несовместимость, но это требует внешней структуры турнира и проверки exceptions. Не объявлять независимость и не исправлять November31 из NLCS rules.',
 ['tournament_constraint','mutual_exclusion_candidate','invalid_calendar_date','other_outcome'],'conditional_exclusion_candidate_but_abstain_until_date_and_format_verified')]
pairs=[]
for cid,domain,a,b,question,reason,tags,hypothesis in specs:
    pairs.append({'case_id':cid,'domain':domain,'a':a,'b':b,'pair_scope':'cross_platform' if registry[a]['venue']!=registry[b]['venue'] else 'cross_event',
                  'question_ru':question,'research_note_ru':reason,'challenge_tags':tags,'relation_hypothesis_for_review':hypothesis,
                  'adjudicated_label':None,'annotation_status':'UNADJUDICATED_DISCOVERY_CANDIDATE','do_not_use_as_gold':True})
(ROOT/'candidate_pairs.json').write_text(json.dumps(pairs,ensure_ascii=False,indent=2)+'\n')
(ROOT/'source_records.json').write_text(json.dumps(list(registry.values()),ensure_ascii=False,indent=2)+'\n')
with (ROOT/'pairs_blind.jsonl').open('w') as f:
    for p in pairs:
        rec={'case_id':p['case_id']}
        for side in ['a','b']:
            x=registry[p[side]];rec[side]={k:x.get(k) for k in ['title','primary','secondary','outcome_label']}
        f.write(json.dumps(rec,ensure_ascii=False)+'\n')
files=[p for p in ROOT.iterdir() if p.is_file() and p.name!='packet_manifest.json']
manifest={'built_at_utc':datetime.now(timezone.utc).isoformat(),'source_type_warning':'No Polymarket Gamma data obtained. Official Kalshi current/historical API plus official-site web index/render. Primary prose is separated from AI context.',
          'candidate_count':len(pairs),'domains':sorted({p['domain'] for p in pairs}),'gold_labels':0,
          'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(ROOT/'packet_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'pairs':len(pairs),'domains':manifest['domains'],'source_records':len(registry),'gold_labels':0},ensure_ascii=False))

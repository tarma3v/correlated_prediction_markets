#!/usr/bin/env python3
"""Build evidence packets for six post-hoc selected, AI-assisted review cases.
These qualitative interpretations are provisional, not independently labeled gold.
"""
import json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent
specs = [
 ('same_title_thresholds', 'KXLCPIMAXYOY-27-P7.0', 'KXLCPIMAXYOY-27-P6.5', 'A_implies_B',
  'Одинаковые title скрывают разные пороги ≥7.0% и ≥6.5% для любого месяца одного года. При одинаковой интерпретации CPI истинность A влечёт B; обратное неверно. Это positive control внутри известного event, а не обнаруженная неизвестная связь.'),
 ('strict_thresholds', 'KXCPI-26OCT-T0.9', 'KXCPI-26OCT-T0.8', 'A_implies_B',
  'Одинаковый показатель, месяц и secondary rules. Строгое >0.9% влечёт >0.8%, но не наоборот. Десятичные числа и строгость сравнения нельзя удалять как noise.'),
 ('different_periods', 'KXCPICOREYOY-26DEC-T2.6', 'KXCPICOREYOY-26NOV-T2.6', 'no_deterministic_relation_established',
  'Различаются двенадцатимесячные периоды: заканчивающийся в декабре и в ноябре. Высокая близость текстов не доказывает эквивалентность или импликацию. Это не утверждение статистической независимости.'),
 ('headline_vs_core', 'KXCPI-26NOV-T0.2', 'KXCPICORE-26NOV-T0.2', 'no_deterministic_relation_established',
  'Одинаковый порог и месяц; однако CPI и CPI All Items less Food and Energy — разные показатели. Из текста не следует знак эмпирической корреляции или детерминированная связь.'),
 ('month_to_any_month', 'KXCPIYOY-26DEC-T5.0', 'KXLCPIMAXYOY-27-P5', 'conditional_A_implies_B_pending_terms_review',
  'Если используются одна версия ряда CPI, одинаковая политика ревизий и трактовка месяца, декабрьский YoY >5.0% влечёт наличие месяца 2026 года с YoY ≥5%. В обоих series metadata указан BLS, но полные contract_terms PDFs ещё не сверены. Поэтому условный кандидат, не подтверждённая контрактная гарантия.'),
 ('different_assets_shared_boilerplate', 'KXPLATINUMH-26SEP2819-T1724.49', 'KXPALLADIUMH-26SEP2819-T1219.49', 'no_deterministic_relation_established',
  'Одинаковая структура времени и fallback rules, но разные базовые активы: platinum и palladium. Общий boilerplate не превращает их в эквивалентные контракты. Эмпирическая связь здесь не измерена.')
]
records = json.loads((ROOT/'markets.json').read_text()); index={r['id']:i for i,r in enumerate(records)}
variants={'title':lambda r:r['title'], 'rules':lambda r:r['primary']+'\n'+r['secondary'], 'title_rules':lambda r:r['title']+'\n'+r['primary']+'\n'+r['secondary']}
scores={}
for name,fn in variants.items():
 text=[fn(r) for r in records]
 w=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,token_pattern=r'(?u)\b\w+\b').fit_transform(text)
 c=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True).fit_transform(text)
 sim=(0.5*(w@w.T)+0.5*(c@c.T)).toarray();np.fill_diagonal(sim,-1);scores[name]=sim
cases=[]
for key,a,b,label,note in specs:
 i,j=index[a],index[b]
 evidence={}
 for name,s in scores.items():
  ra=int(np.flatnonzero(np.argsort(-s[i],kind='stable')==j)[0])+1
  rb=int(np.flatnonzero(np.argsort(-s[j],kind='stable')==i)[0])+1
  evidence[name]={'similarity':round(float(s[i,j]),6),'rank_b_for_a':ra,'rank_a_for_b':rb,'in_top5_union':min(ra,rb)<=5}
 cases.append({'case_id':key,'review_status':'AI-assisted exploratory interpretation; not independently annotated gold','provisional_relation':label,'note_ru':note,
               'a':records[i],'b':records[j],'retrieval':evidence})
(ROOT/'results/review_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
for c in cases:print(c['case_id'],c['retrieval'])

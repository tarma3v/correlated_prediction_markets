"""Offline integrity/provenance audit; no models, no inferred relation labels."""
from pathlib import Path
from collections import Counter,defaultdict
import json,hashlib
BASE=Path(__file__).resolve().parents[1]
SOURCE=BASE/'rawsamples/nl2992_pinned_audit.json'
d=json.loads(SOURCE.read_text()); rows=[]
for subset in ['signal_subset','stratified_subset']:
 for n,r in enumerate(d[subset]):rows.append({**r,'source_subset':subset,'source_row':n})
key=lambda r:(r['poly_id'],r['kalshi_ticker'])
pair_groups=defaultdict(list)
for r in rows: pair_groups[key(r)].append(r)
unique=[v[0] for v in pair_groups.values()]
labelconflicts=[{'poly_id':p[0],'kalshi_ticker':p[1],'labels':sorted(set(r['label'] for r in rs))} for p,rs in pair_groups.items() if len(set(r['label'] for r in rs))>1]
markets={}; metadata_conflicts=[]
for venue,idfield,titlefield,eventfield,datefield in [('polymarket','poly_id','poly_title','poly_event_title','poly_close'),('kalshi','kalshi_ticker','kalshi_title','kalshi_event_title','kalshi_close')]:
 out=defaultdict(list)
 for r in rows:out[r[idfield]].append(r)
 markets[venue]=[]
 for id,rs in out.items():
  vals={f:sorted({str(r.get(f,'')) for r in rs}) for f in [titlefield,eventfield,datefield]}
  if any(len(v)>1 for v in vals.values()):metadata_conflicts.append({'venue':venue,'id':id,'variants':vals})
  markets[venue].append({'id':id,'title':rs[0][titlefield],'event_title':rs[0][eventfield],'close_date':rs[0][datefield]})
 (BASE/f'{venue}_author_audit_markets.json').write_text(json.dumps(markets[venue],ensure_ascii=False,indent=2))
# Group keys use source-provided paired event titles; they are observable proxies, not adjudicated families.
group=lambda r:(r['poly_event_title'],r['kalshi_event_title'])
groups=defaultdict(list)
for r in unique:groups[group(r)].append(r)
negative=[r for r in unique if r['label']=='different']
positive=[r for r in unique if r['label']=='same']
audit={
 'source_commit':'f7f652b7ea7c2285fca7c2aa7c02785b11ba9e84','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
 'generated_by_source':d['generated'],'rows':len(rows),'unique_id_pairs':len(unique),'duplicate_rows_by_ids':len(rows)-len(unique),
 'duplicate_id_pairs':[{'poly_id':k[0],'kalshi_ticker':k[1],'count':len(rs),'subsets':[r['source_subset'] for r in rs]} for k,rs in pair_groups.items() if len(rs)>1],
 'conflicting_labels':labelconflicts,'metadata_conflicts':metadata_conflicts,
 'labels_raw':dict(Counter(r['label'] for r in rows)), 'labels_unique':dict(Counter(r['label'] for r in unique)),
 'categories_raw':dict(Counter(r['category'] for r in rows)), 'categories_unique':dict(Counter(r['category'] for r in unique)),
 'negative_reason_counts':dict(Counter(r['reason_class'] for r in negative)),
 'unsure_reason_counts':dict(Counter(r['reason_class'] for r in unique if r['label']=='unsure')),
 'unique_markets':{v:len(m) for v,m in markets.items()},
 'positive_unique_queries':{f:len(set(r[f] for r in positive)) for f in ['poly_id','kalshi_ticker']},
 'paired_event_title_groups_all':len(groups),'paired_event_title_groups_positive':len(set(group(r) for r in positive)),
 'largest_groups':[{'poly_event_title':k[0],'kalshi_event_title':k[1],'pairs':len(rs),'labels':dict(Counter(r['label'] for r in rs))} for k,rs in sorted(groups.items(),key=lambda item:-len(item[1]))[:20]],
 'fields':sorted(set().union(*(r.keys() for r in rows))),
 'source_license':None,'label_provenance':'Author audit; no independent annotation protocol found. Repository fixture loader says human-labelled; commit adding this fixture is AI-coauthored. Do not infer independent human gold.',
 'evaluation_caveats':['Selected among author v2-endorsed candidate pairs; not exhaustive all-pair labels.','Only titles, event titles, dates and IDs; no full resolution rules.','Unlabelled cross-pairs are not confirmed negatives.','Group by event family and report group macro to reduce template dominance.','No reuse license declared in repo metadata/tree.']}
(BASE/'author_audit_summary.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
(BASE/'author_audit_pairs_unique.json').write_text(json.dumps(unique,ensure_ascii=False,indent=2))
(BASE/'author_audit_negative_pairs.json').write_text(json.dumps(negative,ensure_ascii=False,indent=2))
print(json.dumps({k:audit[k] for k in ['rows','unique_id_pairs','duplicate_rows_by_ids','conflicting_labels','metadata_conflicts','labels_unique','categories_unique','negative_reason_counts','unsure_reason_counts','unique_markets','positive_unique_queries','paired_event_title_groups_all','paired_event_title_groups_positive','largest_groups']},ensure_ascii=False,indent=2))

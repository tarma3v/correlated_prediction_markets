"""Exploratory audit of filtering same-event pairs BEFORE versus AFTER top-k.
Counts and preselected case ranks only: no independent gold, no quality claim.
"""
from collections import Counter
import json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
records=json.loads((ROOT/'pilot/markets.json').read_text())
cases=json.loads((ROOT/'pilot/results/review_cases.json').read_text())
idx={r['id']:i for i,r in enumerate(records)}
valid=np.array([[a['event_id']!=b['event_id'] for b in records] for a in records])
emb=np.load(OUT/'dense_embeddings.npz')
views={'title':lambda r:r['title'],'rules':lambda r:r['primary']+'\n'+r['secondary'],
       'title_rules':lambda r:r['title']+'\n'+r['primary']+'\n'+r['secondary']}
result={'scope':'Post-hoc candidate-budget and eligibility diagnostic, not recall',
        'all_unordered_pairs':len(records)*(len(records)-1)//2,
        'cross_event_unordered_pairs':int(valid.sum()//2),'methods':{}}
for kind in ['lexical','dense']:
    unions={k:{'pre':set(),'post':set()} for k in [1,5,10,20]}
    detail={}
    for view,fn in views.items():
        if kind=='dense': sim=emb[view]@emb[view].T
        else:
            texts=[fn(r) for r in records]
            w=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,token_pattern=r'(?u)\b\w+\b').fit_transform(texts)
            c=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True).fit_transform(texts)
            sim=(.5*(w@w.T)+.5*(c@c.T)).toarray()
        np.fill_diagonal(sim,-np.inf)
        ordinary=np.argsort(-sim,axis=1,kind='stable')
        masked=sim.copy(); masked[~valid]=-np.inf
        eligible=np.argsort(-masked,axis=1,kind='stable')
        ranks=[]
        for case in cases:
            i,j=idx[case['a']['id']],idx[case['b']['id']]
            if not valid[i,j]: continue
            ranks.append({'case_id':case['case_id'],
                          'ordinary_min_direction_rank':min(int(np.where(ordinary[i]==j)[0][0])+1,int(np.where(ordinary[j]==i)[0][0])+1),
                          'eligible_min_direction_rank':min(int(np.where(eligible[i]==j)[0][0])+1,int(np.where(eligible[j]==i)[0][0])+1)})
        budgets={}
        for k in unions:
            pre={tuple(sorted((i,int(j)))) for i in range(len(records)) for j in eligible[i,:k] if valid[i,j] and sim[i,j]>0}
            post={tuple(sorted((i,int(j)))) for i in range(len(records)) for j in ordinary[i,:k] if valid[i,j] and sim[i,j]>0}
            assert post.issubset(pre)
            budgets[str(k)]={'filter_before_topk_pairs':len(pre),'filter_after_topk_pairs':len(post)}
            unions[k]['pre']|=pre; unions[k]['post']|=post
        detail[view]={'budgets':budgets,'case_ranks':ranks}
    detail['union']={str(k):{'filter_before_topk_pairs':len(v['pre']),'filter_after_topk_pairs':len(v['post'])} for k,v in unions.items()}
    result['methods'][kind]=detail
(OUT/'eligible_retrieval.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v['union'] for k,v in result['methods'].items()},indent=2))

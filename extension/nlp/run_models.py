#!/usr/bin/env python3
"""Frozen, local dense/NLI diagnostic. No trading, remote inference, or training.

Synthetic labels follow explicitly stipulated scalar worlds. Real cases are
exploratory inputs with NO gold labels and cannot yield market accuracy.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
import re
import sys
import time

os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
import numpy as np
import torch
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CACHE = ROOT/'tmp/hf_cache'
MODELS = {
    'dense': {'repo':'sentence-transformers/all-MiniLM-L6-v2',
              'revision':'1110a243fdf4706b3f48f1d95db1a4f5529b4d41', 'max_length':256},
    'nli': {'repo':'MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli',
            'revision':'6f5cf0a2b59cabb106aca4c287eed12e357e90eb', 'max_length':512},
}


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
def load(name): return json.loads((OUT/name).read_text())


def truth(x, op, boundary):
    return {'gt': x > boundary, 'ge': x >= boundary,
            'lt': x < boundary, 'le': x <= boundary}[op]


def possible_states(a, b):
    # For unary comparisons, boundaries, intervening intervals and tails are
    # a complete finite partition of the real line for truth-value purposes.
    boundaries = sorted({Decimal(a['threshold']),Decimal(b['threshold'])})
    representatives = [boundaries[0]-1, boundaries[-1]+1] + boundaries
    representatives += [(x+y)/2 for x,y in zip(boundaries,boundaries[1:])]
    worlds = ((x,x) for x in representatives) if a['context']==b['context'] else itertools.product(representatives, repeat=2)
    return sorted({(int(truth(x,a['op'],Decimal(a['threshold']))),
                    int(truth(y,b['op'],Decimal(b['threshold'])))) for x,y in worlds})


def synthetic_dataset():
    patterns = [('strict_nested','gt','hi','gt','lo'),
                ('inclusive_nested','ge','hi','ge','lo'),
                ('strict_to_inclusive','gt','lo','ge','lo'),
                ('inclusive_to_strict','ge','lo','gt','lo'),
                ('complement_strict','gt','lo','le','lo'),
                ('complement_inclusive','ge','lo','lt','lo'),
                ('exclusion_with_gap','lt','lo','gt','hi'),
                ('inclusive_overlap','ge','lo','le','lo'),
                ('identical','gt','lo','gt','lo'),
                ('strict_overlap','lt','hi','gt','lo')]
    domains = [
        {'name':'cpi','head':'The CPI inflation rate reported by the Bureau of Labor Statistics',
         'lo':'0.2','hi':'0.3','unit':'%'},
        {'name':'temperature','head':'The temperature reported by Station Alpha',
         'lo':'20','hi':'21','unit':' degrees Celsius'},
        {'name':'price','head':'The closing price reported by Exchange Alpha',
         'lo':'100','hi':'150','unit':' USD'},
    ]
    wording={'gt':'more than','ge':'at least','lt':'less than','le':'at most'}
    pairs=[]
    for d in domains:
        def clause(op,key,context='October 2026',head=None):
            head=head or d['head']; threshold=d[key]
            return {'text':f"{head} for {context} is {wording[op]} {threshold}{d['unit']}.",
                    'op':op,'threshold':threshold,'context':head+'|'+context}
        for name,oa,ta,ob,tb in patterns:
            pairs.append({'id':d['name']+'_'+name,'slice':name,'domain':d['name'],
                          'a':clause(oa,ta),'b':clause(ob,tb)})
        pairs.append({'id':d['name']+'_different_period','slice':'different_period','domain':d['name'],
                      'a':clause('gt','lo'),'b':clause('gt','lo','November 2026')})
        pairs.append({'id':d['name']+'_different_source','slice':'different_source','domain':d['name'],
                      'a':clause('gt','lo'),'b':clause('gt','lo',head=d['head']+' Alternative')})
    for p in pairs:
        states=possible_states(p['a'],p['b']); p['possible_states']=states
        # This is ordinary proposition-NLI under our stipulated scalar contexts.
        p['gold_a_to_b']='entailment' if (1,0) not in states else ('contradiction' if (1,1) not in states else 'neutral')
        p['gold_b_to_a']='entailment' if (0,1) not in states else ('contradiction' if (1,1) not in states else 'neutral')
    return pairs


def load_model(kind, classification=False):
    spec=MODELS[kind]
    kwargs=dict(revision=spec['revision'],cache_dir=str(CACHE),token=False,
                trust_remote_code=False,local_files_only=True)
    tok=AutoTokenizer.from_pretrained(spec['repo'],**kwargs)
    cls=AutoModelForSequenceClassification if classification else AutoModel
    model=cls.from_pretrained(spec['repo'],use_safetensors=True,**kwargs).eval().to('cpu')
    return tok,model


def dense(records,cases):
    start=time.monotonic(); tok,model=load_model('dense')
    fns={'title':lambda r:r['title'], 'rules':lambda r:r['primary']+'\n'+r['secondary'],
         'title_rules':lambda r:r['title']+'\n'+r['primary']+'\n'+r['secondary']}
    ids={r['id']:i for i,r in enumerate(records)}; summaries={}; case_rows=[]; arrays={}
    for view,fn in fns.items():
        texts=[fn(r) for r in records]
        lengths=[len(tok(t,add_special_tokens=True,truncation=False)['input_ids']) for t in texts]
        chunks=[]
        for st in range(0,len(texts),16):
            batch=tok(texts[st:st+16],padding=True,truncation=True,max_length=256,return_tensors='pt')
            with torch.inference_mode():
                h=model(**batch).last_hidden_state
                mask=batch['attention_mask'].unsqueeze(-1).float()
                pooled=(h*mask).sum(1)/mask.sum(1).clamp(min=1)
                chunks.append(torch.nn.functional.normalize(pooled,p=2,dim=1).cpu().numpy())
        emb=np.concatenate(chunks); arrays[view]=emb
        sim=emb@emb.T; np.fill_diagonal(sim,-1)
        order=np.argsort(-sim,axis=1,kind='stable')
        summary={'input_count':len(texts),'truncated_inputs':sum(x>256 for x in lengths),
                 'max_untruncated_tokens':max(lengths),'top_k':{}}
        for k in [1,5,10,20,50]:
            edges={tuple(sorted((i,int(j)))) for i in range(len(records)) for j in order[i,:k]}
            summary['top_k'][str(k)]={'candidate_pairs':len(edges),
                'cross_event_pairs':sum(records[i]['event_id']!=records[j]['event_id'] for i,j in edges)}
        summaries[view]=summary
        for case in cases:
            i,j=ids[case['a']['id']],ids[case['b']['id']]
            ra=int(np.where(order[i]==j)[0][0])+1; rb=int(np.where(order[j]==i)[0][0])+1
            case_rows.append({'case_id':case['case_id'],'view':view,'similarity':float(sim[i,j]),
                              'rank_b_for_a':ra,'rank_a_for_b':rb,'in_top5_union':min(ra,rb)<=5})
        print('Dense completed',view,summary['truncated_inputs'],'truncated',flush=True)
    np.savez_compressed(OUT/'dense_embeddings.npz',**arrays)
    write('dense_case_ranks.json',case_rows)
    write('dense_summary.json',{'model':MODELS['dense'],'views':summaries,'wall_seconds':time.monotonic()-start,
                               'warning':'No human gold; candidate counts and case ranks are not market recall/accuracy.'})


def nli(cases,synthetic):
    start=time.monotonic(); tok,model=load_model('nli',True)
    labels={int(k):v.lower() for k,v in model.config.id2label.items()}
    if set(labels.values())!={'entailment','neutral','contradiction'}: raise ValueError(labels)
    requests=[]
    for p in synthetic:
        for direct,a,b in [('a_to_b','a','b'),('b_to_a','b','a')]:
            requests.append({'kind':'synthetic','id':p['id'],'slice':p['slice'],'direction':direct,
                'premise':p[a]['text'],'hypothesis':p[b]['text'],'gold':p['gold_'+direct]})
    def event_clause(r):
        text=r['primary']
        match=re.fullmatch(r'If (.*), then the market resolves to Yes\.',text,flags=re.S)
        return match.group(1).strip()+'.' if match else text
    views={'title':lambda r:r['title'],
           'title_rules':lambda r:r['title']+'\n'+r['primary']+'\n'+r['secondary'],
           'event_clause':event_clause}
    for c in cases:
        for view,fn in views.items():
            for direct,a,b in [('a_to_b','a','b'),('b_to_a','b','a')]:
                requests.append({'kind':'real_exploratory','id':c['case_id'],'view':view,'direction':direct,
                                 'premise':fn(c[a]),'hypothesis':fn(c[b]),'gold':None})
    # Freeze exact inputs and labels before inference; no tuning on results.
    write('nli_inputs.json',requests)
    for st in range(0,len(requests),4):
        rows=requests[st:st+4]
        lengths=[len(tok(r['premise'],r['hypothesis'],truncation=False)['input_ids']) for r in rows]
        batch=tok([r['premise'] for r in rows],[r['hypothesis'] for r in rows],
                  padding=True,truncation=True,max_length=512,return_tensors='pt')
        with torch.inference_mode(): probs=model(**batch).logits.softmax(-1).cpu().numpy()
        for r,p,length in zip(rows,probs,lengths):
            r['probabilities']={labels[i]:float(v) for i,v in enumerate(p)}
            r['prediction']=labels[int(p.argmax())]
            r['untruncated_tokens']=length; r['truncated']=length>512
        if (st//4)%6==0: print('NLI progress',min(st+4,len(requests)), '/',len(requests),flush=True)
    write('nli_predictions.json',requests)
    syn=[r for r in requests if r['kind']=='synthetic']
    by_slice={}
    for s in sorted({r['slice'] for r in syn}):
        part=[r for r in syn if r['slice']==s]
        by_slice[s]={'n':len(part),'correct':sum(r['prediction']==r['gold'] for r in part)}
    conf=Counter((r['gold'],r['prediction']) for r in syn)
    write('nli_summary.json',{'model':MODELS['nli'],'label_mapping':labels,
       'synthetic_directional_examples':len(syn),'synthetic_correct':sum(r['prediction']==r['gold'] for r in syn),
       'synthetic_label_counts':dict(Counter(r['gold'] for r in syn)),
       'synthetic_confusion':[{'gold':g,'predicted':p,'count':n} for (g,p),n in sorted(conf.items())],
       'by_slice':by_slice,'real_directional_inputs':len(requests)-len(syn),
       'truncated_inputs':sum(r['truncated'] for r in requests),'wall_seconds':time.monotonic()-start,
       'warning':'Synthetic diagnostic templates only; no real-market accuracy estimate, no human gold, no LLM evaluation.'})


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--stage',choices=['all','dense','nli'],default='all')
    args=parser.parse_args()
    torch.manual_seed(0); np.random.seed(0); torch.set_num_threads(4)
    sys.path.insert(0,str(ROOT/'pilot'))
    from pilot import input_digest
    manifest=json.loads((ROOT/'pilot/manifest.json').read_text())
    if sha(ROOT/'pilot/markets.json')!=manifest['markets_sha256']: raise ValueError('Changed snapshot')
    records=json.loads((ROOT/'pilot/markets.json').read_text())
    if not all(input_digest(r)==r['input_sha256'] for r in records): raise ValueError('Changed record')
    cases=json.loads((ROOT/'pilot/results/review_cases.json').read_text())
    synth=synthetic_dataset(); write('synthetic_dataset.json',synth)
    # Exact minimal mathematical checks, independent of learned predictions.
    by={p['id']:p for p in synth}
    assert by['cpi_strict_nested']['gold_a_to_b']=='entailment'
    assert by['cpi_strict_nested']['gold_b_to_a']=='neutral'
    assert by['cpi_inclusive_overlap']['possible_states']==[(0,1),(1,0),(1,1)]
    assert by['cpi_different_period']['possible_states']==[(0,0),(0,1),(1,0),(1,1)]
    plan={'created_at_utc':now(),'purpose':'Exploratory local diagnostic, not a preregistered external benchmark',
          'input_hash':sha(ROOT/'pilot/markets.json'),'synthetic_hash':sha(OUT/'synthetic_dataset.json'),
          'script_hash':sha(Path(__file__)),'models':MODELS,'device':'cpu','threads':4,'seed':0,
          'python':platform.python_version(),'platform':platform.platform(),
          'dependencies':{p:importlib.metadata.version(p) for p in ['torch','transformers','numpy','tokenizers','safetensors','huggingface-hub','sentencepiece']},
          'views':'Dense: title/rules/title_rules; real NLI: title/title_rules/event_clause; both NLI directions',
          'scope':'No training, no paid API, no remote inference, no independent real-market gold'}
    write('run_manifest.json',plan)
    if args.stage in ['dense','all']: dense(records,cases)
    if args.stage in ['nli','all']: nli(cases,synth)
    plan['completed_at_utc']=now(); plan['stage']=args.stage
    write('run_manifest.json',plan)
    print('COMPLETED',args.stage,flush=True)


if __name__=='__main__': main()

#!/usr/bin/env python3
"""Bidirectional NLI over the frozen 1,188 lexical candidates; no gold accuracy."""
from collections import Counter
import json
import time
import torch
from run_models import ROOT, OUT, MODELS, load_model, sha, now, write


def main():
    torch.manual_seed(0); torch.set_num_threads(4)
    start=time.monotonic()
    records=json.loads((ROOT/'pilot/markets.json').read_text())
    original=json.loads((ROOT/'pilot/manifest.json').read_text())
    if sha(ROOT/'pilot/markets.json')!=original['markets_sha256']: raise ValueError('Changed snapshot')
    by_id={r['id']:r for r in records}
    candidates=json.loads((ROOT/'pilot/results/candidates.json').read_text())
    tok,model=load_model('nli',True)
    labels={int(k):v.lower() for k,v in model.config.id2label.items()}
    if set(labels.values())!={'entailment','neutral','contradiction'}: raise ValueError(labels)
    def text(r): return r['title']+'\n'+r['primary']+'\n'+r['secondary']
    predictions=[]
    run={'started_at_utc':now(),'input_hash':sha(ROOT/'pilot/markets.json'),
         'candidate_hash':sha(ROOT/'pilot/results/candidates.json'),
         'script_hash':sha(__import__('pathlib').Path(__file__)), 'model':MODELS['nli'],
         'view':'title + primary + secondary', 'threshold':0.8,'dominance_margin':0.1,
         'purpose':'Descriptive output distribution; no gold labels; not reproduction of article.'}
    write('corpus_run_manifest.json',run)
    pending=[]
    for ci,c in enumerate(candidates):
        for direction,a,b in [('a_to_b','a','b'),('b_to_a','b','a')]:
            pending.append((ci,direction,text(by_id[c[a]]),text(by_id[c[b]])))
    by_pair=[{} for _ in candidates]
    truncations=0
    for st in range(0,len(pending),4):
        batchrows=pending[st:st+4]
        lens=[len(tok(a,b,truncation=False)['input_ids']) for _,_,a,b in batchrows]
        batch=tok([r[2] for r in batchrows],[r[3] for r in batchrows],padding=True,
                  truncation=True,max_length=512,return_tensors='pt')
        with torch.inference_mode(): p=model(**batch).logits.softmax(-1).cpu().numpy()
        for (ci,direction,_,_),scores,length in zip(batchrows,p,lens):
            by_pair[ci][direction]={labels[i]:float(v) for i,v in enumerate(scores)}
            truncations+=int(length>512)
        if st%200==0: print('Corpus NLI',min(st+4,len(pending)),'/',len(pending),flush=True)
    for c,scores in zip(candidates,by_pair):
        ab,ba=scores['a_to_b'],scores['b_to_a']
        contradiction=(ab['contradiction']+ba['contradiction'])/2
        ea,eb=ab['entailment'],ba['entailment']
        if contradiction>=.8 and contradiction>=max(ea,eb)+.1:
            candidate='exclusion_candidate'
        elif min(ea,eb)>=.8 and min(ea,eb)>=contradiction+.1:
            candidate='equivalence_candidate'
        elif ea>=.8 and ea>=contradiction+.1:
            candidate='a_implies_b_candidate'
        elif eb>=.8 and eb>=contradiction+.1:
            candidate='b_implies_a_candidate'
        else: candidate='abstain'
        predictions.append({'a':c['a'],'b':c['b'],'same_event':c['same_event'],
                            **scores,'nli_candidate_type':candidate,'verified':False})
    write('corpus_nli_predictions.json',predictions)
    run.update(completed_at_utc=now(),wall_seconds=time.monotonic()-start,
       n_pairs=len(predictions),directional_inferences=len(pending),truncated_inputs=truncations,
       output_counts=dict(Counter(r['nli_candidate_type'] for r in predictions)),
       cross_event_counts=dict(Counter(r['nli_candidate_type'] for r in predictions if not r['same_event'])),
       warning='None of these model labels is a verified payoff relation. No precision/recall measured.')
    write('corpus_run_manifest.json',run)
    print(json.dumps(run,ensure_ascii=False,indent=2))


if __name__=='__main__': main()

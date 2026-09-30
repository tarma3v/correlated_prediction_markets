"""Audit-corrected synthetic diagnostic: explicit continuous fictional variables.

Version 1 is preserved. V2 removes repeated ordered text pairs BEFORE inference
and avoids confusing real CPI rounding with an explicitly continuous toy world.
This is an exploratory correction after review, not a new independent test set.
"""
from collections import Counter
import json
import time
import torch
from run_models import OUT, MODELS, synthetic_dataset, possible_states, load_model, write, now, sha


def main():
    torch.manual_seed(0); torch.set_num_threads(2)
    rows=[]; seen={}
    heads={
        'cpi':'The value of a hypothetical continuous inflation indicator reported by Source Alpha',
        'temperature':'The continuous temperature measurement reported by Station Alpha',
        'price':'The value of a hypothetical continuous price indicator reported by Source Alpha',
    }
    ops={'gt':'more than','ge':'at least','lt':'less than','le':'at most'}
    units={'cpi':'%','temperature':' degrees Celsius','price':' USD'}
    for pair in synthetic_dataset():
        for side in ['a','b']:
            r=pair[side]
            period='November 2026' if pair['slice']=='different_period' and side=='b' else 'October 2026'
            head=heads[pair['domain']]
            if pair['slice']=='different_source' and side=='b': head=head.replace('Alpha','Beta')
            r['context']=head+'|'+period
            r['text']=f"{head} for {period} is {ops[r['op']]} {r['threshold']}{units[pair['domain']]} .".replace(' .','.')
        states=possible_states(pair['a'],pair['b'])
        for direction,a,b,forbidden in [('a_to_b','a','b',(1,0)),('b_to_a','b','a',(0,1))]:
            gold='entailment' if forbidden not in states else ('contradiction' if (1,1) not in states else 'neutral')
            key=(pair[a]['text'],pair[b]['text'])
            if key in seen:
                old=rows[seen[key]]; assert old['gold']==gold
                old['origin_ids'].append(pair['id']+':'+direction)
                continue
            seen[key]=len(rows)
            rows.append({'id':len(rows)+1,'origin_ids':[pair['id']+':'+direction],
                         'slice':pair['slice'],'domain':pair['domain'],
                         'premise':key[0],'hypothesis':key[1],'gold':gold,
                         'world_assumption':'Continuous real scalar for same context; unconstrained different contexts. Fictional.'})
    write('synthetic_v2_inputs.json',rows)
    manifest={'started_at_utc':now(),'input_hash':sha(OUT/'synthetic_v2_inputs.json'),
              'model':MODELS['nli'],'n_unique_ordered_text_pairs':len(rows),'device':'cpu','threads':2,
              'reason':'Post-review correction of duplicate weighting and ambiguous real-CPI versus continuous domain in v1.',
              'warning':'Exploratory template diagnostic, neither held-out independent study nor real-market accuracy.'}
    write('synthetic_v2_manifest.json',manifest)
    tok,model=load_model('nli',True)
    labels={int(k):v.lower() for k,v in model.config.id2label.items()}
    start=time.monotonic()
    for st in range(0,len(rows),4):
        part=rows[st:st+4]
        batch=tok([r['premise'] for r in part],[r['hypothesis'] for r in part],
                  padding=True,truncation=True,max_length=512,return_tensors='pt')
        with torch.inference_mode(): probs=model(**batch).logits.softmax(-1).cpu().numpy()
        for r,p in zip(part,probs):
            r['prediction']=labels[int(p.argmax())]
            r['probabilities']={labels[i]:float(v) for i,v in enumerate(p)}
    write('synthetic_v2_predictions.json',rows)
    confusion=Counter((r['gold'],r['prediction']) for r in rows)
    manifest.update(completed_at_utc=now(),inference_wall_seconds=time.monotonic()-start,
                    correct=sum(r['prediction']==r['gold'] for r in rows),
                    gold_counts=dict(Counter(r['gold'] for r in rows)),
                    confusion=[{'gold':g,'prediction':p,'n':n} for (g,p),n in sorted(confusion.items())])
    write('synthetic_v2_manifest.json',manifest)
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()

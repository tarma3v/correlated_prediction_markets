"""Join NLI outputs to exact-template scalar candidates, not human market gold."""
from collections import Counter
from decimal import Decimal, localcontext
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
templates=json.loads((ROOT/'extension/retrieval/results/threshold_candidates.json').read_text())
by_pair={tuple(sorted((r['a'],r['b']))):r for r in templates}
predictions=json.loads((OUT/'corpus_nli_predictions.json').read_text())
matched=[]
for p in predictions:
    template=by_pair.get(tuple(sorted((p['a'],p['b']))))
    if template is None: continue
    # A witness for simultaneous truth under the stated unbounded scalar model.
    with localcontext() as ctx:
        ctx.prec=60
        x=max(Decimal(template['threshold_a']),Decimal(template['threshold_b']))+Decimal(1)
    assert x>Decimal(template['threshold_a']) and x>Decimal(template['threshold_b'])
    matched.append({'a':p['a'],'b':p['b'],'nli_candidate_type':p['nli_candidate_type'],
                    'template_group':template['group_key'],'scalar_both_yes_witness':str(x),
                    'conflict_in_scalar_scope':p['nli_candidate_type']=='exclusion_candidate',
                    'scope':'Same unrestricted scalar value, same template, binary rule-following settlement only.',
                    'human_gold':False,'unconditional_contract_certified':False})
result={'scope':'Conditional mathematical consistency diagnostic, NOT human-gold market accuracy',
        'matched_pairs':len(matched),'event_template_groups':len({r['template_group'] for r in matched}),
        'nli_counts':dict(Counter(r['nli_candidate_type'] for r in matched)),
        'exclusion_conflicts':sum(r['conflict_in_scalar_scope'] for r in matched),'records':matched}
(OUT/'conditional_consistency.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))

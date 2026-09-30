"""Run two pinned local LLMs on frozen, label-blind packets using MLX/Metal."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import time

os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
from huggingface_hub import snapshot_download
import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler
import jsonschema
from download_llms import MODELS, ALLOW_PATTERNS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'comparison/llm'
PLAN_PATH=ROOT/'comparison/plan.json'


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def packets(plan):
    external=[{'kind':'external', 'id':r['pair_id'],
               'packet':{'pair_id':r['pair_id'],**r['input']}}
              for r in plan['external_llm']['selected_pairs']]
    core=[]
    for path,h in plan['core_rules_llm']['source_hashes'].items():
        assert sha(ROOT/path)==h, f'Changed input {path}'
    for case in plan['core_rules_llm']['cases']:
        assert sha(ROOT/case['identity_source']) == case['identity_source_sha256']
        raw=json.loads((ROOT/case['rule_input_source']).read_text())
        packet={'case_id':case['case_id']}
        if isinstance(raw,dict):
            card=json.loads((ROOT/case['identity_source']).read_text())
            for side in ['A','B']:
                source_ids=card['contracts'][side]['source_ids']
                sources=[s for s in card['sources'] if s['source_id'] in source_ids]
                packet[side]={'title':card['contracts'][side]['title'],
                    'rules_raw':raw[case['rule_keys'][side]],
                    'source_provenance':[{k:s[k] for k in ['provenance','coverage_note']} for s in sources]}
        else:
            lookup={r['id']:r for r in raw}
            for side in ['A','B']:
                r=lookup[case['rule_keys'][side]]
                packet[side]={k:r[k] for k in ['title','primary','secondary','timing_metadata','source_kind','coverage_note'] if k in r}
        core.append({'kind':'core','id':case['case_id'],'packet':packet})
    return external+core


def parse_output(text, schema):
    # No repair model, extraction of embedded JSON, or selective retries.
    try:
        obj=json.loads(text.strip())
        jsonschema.validate(obj,schema)
        return obj,None
    except (ValueError,jsonschema.ValidationError) as exc:
        return None,type(exc).__name__+': '+str(exc).splitlines()[0][:250]


def evidence_check(parsed, packet):
    checks=[]
    for item in parsed.get('evidence',[]):
        original=packet.get(item['contract'],{}).get(item['field'])
        if isinstance(original,dict): original=json.dumps(original,ensure_ascii=False,sort_keys=True)
        ok=isinstance(original,str) and bool(item['quote']) and item['quote'] in original
        checks.append({'contract':item['contract'],'field':item['field'],
                       'quote':item['quote'],'exact_substring':ok})
    return checks


def summarize(rows, plan):
    labels={r['pair_id']:r['reference_label'] for r in plan['external_llm']['selected_pairs']}
    expected_ids={('external',key) for key in labels} | {
        ('core',case['case_id']) for case in plan['core_rules_llm']['cases']}
    actual_ids=[(r['kind'],r['id']) for r in rows]
    assert len(actual_ids)==len(expected_ids) and set(actual_ids)==expected_ids, \
        'Incomplete or duplicated run: preserve error rows instead of changing denominators'
    ext=[r for r in rows if r['kind']=='external']
    definite=[r for r in ext if labels[r['id']] in ['same','different']]
    expected={'same':'exact_match','different':'not_exact_match'}
    decision=lambda r:r['parsed']['decision'] if r.get('parsed') and not r.get('error') else 'error'
    matches=sum(decision(r)==expected[labels[r['id']]] for r in definite)
    covered=[r for r in definite if decision(r) in ['exact_match','not_exact_match']]
    conf=Counter((labels[r['id']],decision(r)) for r in definite)
    by={label:{'n':sum(labels[r['id']]==label for r in definite),
               'agree':sum(labels[r['id']]==label and decision(r)==want for r in definite)}
        for label,want in expected.items()}
    checks=[c for r in rows for c in r.get('evidence_checks',[])]
    return {'external_n':len(ext),'definite_author_labels':len(definite),
        'reference_label_agreement':{'agree':matches,'n':len(definite),'fraction':matches/len(definite)},
        'coverage':{'covered':len(covered),'n':len(definite),'fraction':len(covered)/len(definite)},
        'selective_agreement':{'agree':matches,'n':len(covered),'fraction':matches/len(covered) if covered else None},
        'per_class':by,'balanced_agreement':sum(v['agree']/v['n'] for v in by.values())/2,
        'confusion':[{'author_label':a,'prediction':b,'n':n} for (a,b),n in sorted(conf.items())],
        'author_unsure_prediction_counts':dict(Counter(decision(r) for r in ext if labels[r['id']]=='unsure')),
        'schema_valid_json':sum(r.get('parsed') is not None for r in rows),
        'valid_first_pass_json':sum(r.get('parsed') is not None and not r.get('error') for r in rows),
        'error_counts':dict(Counter(r['error'].split(':',1)[0] for r in rows if r.get('error'))),
        'total_n':len(rows),'quote_exact_substrings':{'valid':sum(c['exact_substring'] for c in checks),'n':len(checks)},
        'core_decisions':[{'id':r['id'],'decision':decision(r),
                          'relation':r['parsed'].get('relation') if r.get('parsed') and not r.get('error') else None}
                         for r in rows if r['kind']=='core'],
        'caveat':'Agreement with external author labels on an enriched 64-pair sample, not human-gold accuracy. Core cases have no scored gold. Quote existence is not evidence sufficiency.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',choices=list(MODELS),required=True)
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    plan=json.loads(PLAN_PATH.read_text());items=packets(plan)
    for item in items:
        part=plan['external_llm' if item['kind']=='external' else 'core_rules_llm']
        item['system_prompt']=part['prompt']+'\nRequired JSON schema: '+json.dumps(part['output_schema'],ensure_ascii=False)
        item['user_prompt']=json.dumps(item['packet'],ensure_ascii=False,sort_keys=True)
    inputs=OUT/'inputs.json'
    encoded=json.dumps(items,ensure_ascii=False,indent=2)+'\n'
    if inputs.exists(): assert inputs.read_text()==encoded, 'Changed frozen LLM inputs'
    else: inputs.write_text(encoded)
    spec=MODELS[args.model];dest=OUT/args.model;dest.mkdir(exist_ok=True)
    if (dest/'predictions.jsonl').exists(): raise RuntimeError('Preserve existing run; use a new output directory for a rerun.')
    manifest={'started_at_utc':now(),'model':spec,'quantization':'MLX 4-bit',
        'device':'Apple Metal','seed':plan['runtime']['seed'],'temperature':0,
        'max_tokens_external':plan['runtime']['max_new_tokens_external'],
        'max_tokens_core':plan['runtime']['max_new_tokens_core'],
        'plan_sha256':sha(PLAN_PATH),'inputs_sha256':sha(inputs),'script_sha256':sha(Path(__file__)),
        'python':platform.python_version(),'runtime_versions':{x:md.version(x) for x in ['mlx','mlx-lm','transformers','huggingface-hub','jsonschema']},
        'generation':'Greedy decoding; same serialized packets, prompts and token limits for both models. No answer repair.'}
    save(dest/'run_manifest.json',manifest)
    model_path=snapshot_download(spec['repo'],revision=spec['revision'],cache_dir=str(ROOT/'tmp/llm_cache'),token=False,local_files_only=True,allow_patterns=ALLOW_PATTERNS)
    model,tok=load(model_path,tokenizer_config={'trust_remote_code':False})
    rows=[];start=time.monotonic()
    for n,item in enumerate(items,1):
        cap=manifest['max_tokens_external' if item['kind']=='external' else 'max_tokens_core']
        result='';last=None;begin=time.monotonic();tokens=None;generation_error=None
        try:
            mx.random.seed(plan['runtime']['seed'])
            prompt=tok.apply_chat_template([{'role':'system','content':item['system_prompt']},
                                           {'role':'user','content':item['user_prompt']}],tokenize=False,add_generation_prompt=True)
            tokens=tok.encode(prompt)
            if len(tokens)>8192:
                generation_error='InputTokenLimit: exceeds declared 8192 token cap; no truncation'
            else:
                for response in stream_generate(model,tok,prompt=prompt,max_tokens=cap,sampler=make_sampler(temp=0.0)):
                    result+=response.text;last=response
                if last is None:
                    generation_error='EmptyGeneration'
        except Exception as exc:
            # An unsuccessful case remains in the fixed denominator. No answer repair.
            generation_error='GenerationError: '+type(exc).__name__+': '+str(exc)[:250]
        part=plan['external_llm' if item['kind']=='external' else 'core_rules_llm']
        parsed,error=parse_output(result,part['output_schema'])
        if parsed and parsed.get('pair_id',parsed.get('case_id'))!=item['id']:error='IdentifierMismatch'
        finish=getattr(last,'finish_reason',None)
        if finish=='length':error='OutputTokenLimit'
        if generation_error:error=generation_error
        row={'kind':item['kind'],'id':item['id'],'raw_output':result,'parsed':parsed,'error':error,
             'input_tokens':len(tokens) if tokens is not None else None,'generated_tokens':getattr(last,'generation_tokens',None),
             'finish_reason':finish,'seconds':time.monotonic()-begin,
             'evidence_checks':evidence_check(parsed,item['packet']) if parsed else []}
        rows.append(row)
        with (dest/'predictions.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        if n%8==0 or n==len(items):print(args.model,n,'/',len(items),'seconds',round(time.monotonic()-start,1),flush=True)
        mx.clear_cache()
    save(dest/'summary.json',summarize(rows,plan))
    manifest.update(completed_at_utc=now(),n=len(rows),seconds=time.monotonic()-start,
                    predictions_sha256=sha(dest/'predictions.jsonl'))
    save(dest/'run_manifest.json',manifest)
    del model,tok;gc.collect();mx.clear_cache()
    print('COMPLETED',args.model,flush=True)


if __name__=='__main__':main()

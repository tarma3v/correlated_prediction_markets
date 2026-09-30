from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, concurrent.futures
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
SERIES=['KXCPIYOY','KXLCPIMAXYOY','KXCPI','KXCPICOREYOY','KXCPICORE','KXPLATINUMH','KXPALLADIUMH']
def now(): return datetime.now(timezone.utc).isoformat()
def fetch(url,name):
    start=now(); p=ROOT/name
    proc=subprocess.run(['curl','-L','--silent','--show-error','--max-time','45','-o',str(p),'-w','%{http_code}\n%{url_effective}\n',url],capture_output=True,text=True)
    lines=proc.stdout.strip().splitlines()
    record=dict(url=url,path=name,requested_at_utc=start,fetched_at_utc=now(),curl_exit=proc.returncode,http_status=lines[0] if lines else None,final_url=lines[1] if len(lines)>1 else None,error=proc.stderr or None)
    if p.exists(): record.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
    return record
records=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    records=list(pool.map(lambda s:fetch(f'https://external-api.kalshi.com/trade-api/v2/series/{s}',f'metadata_{s}_current.json'),SERIES))
jobs=[]
for s,record in zip(SERIES,records):
    if record['http_status']=='200':
        d=json.loads((ROOT/record['path']).read_text())['series']
        for field,suffix in [('contract_terms_url','terms'),('contract_url','certification')]:
            if d.get(field): jobs.append((d[field],f'{s}_{suffix}.pdf'))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    fetched=list(pool.map(lambda x:fetch(*x),jobs))
records+=fetched
for r in fetched:
    p=ROOT/r['path']
    if r['http_status']=='200' and p.read_bytes().startswith(b'%PDF'):
        reader=PdfReader(p)
        txt='\n'.join(f'\n--- PDF PAGE {i+1} ---\n'+(page.extract_text() or '') for i,page in enumerate(reader.pages))
        p.with_suffix('.txt').write_text(txt)
        r['pages']=len(reader.pages)
        r['extracted_text_path']=p.with_suffix('.txt').name
inputs=[]
for name in ['review_cases.json']:
    p=REPO/'pilot/results'/name
    inputs.append(dict(path=str(p.relative_to(REPO)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
for s in SERIES[:2]:
    p=REPO/'pilot/raw'/f'metadata_{s}.json'
    inputs.append(dict(path=str(p.relative_to(REPO)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
manifest=dict(created_at_utc=now(),scope='Current official terms retrieved separately; not proof of historical document version. Original pilot unchanged.',inputs=inputs,downloads=records)
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for r in records: print(r['path'],r['http_status'],r.get('bytes'),r.get('pages'))

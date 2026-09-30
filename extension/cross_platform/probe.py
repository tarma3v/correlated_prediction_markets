import datetime,hashlib,json,pathlib,requests
from concurrent.futures import ThreadPoolExecutor
ROOT=pathlib.Path(__file__).resolve().parent
URLS=[('polymarket_core_cpi_market','https://polymarket.com/event/core-cpi-yoy-september-2026/will-core-cpi-yoy-be-2pt3-in-september-2026'),('polymarket_core_cpi_event','https://polymarket.com/event/core-cpi-yoy-september-2026'),('polymarket_macro','https://polymarket.com/economy/macro-indicators')]
def fetch(item):
 name,url=item;entry={'name':name,'url':url,'requested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  r=requests.get(url,timeout=25);entry.update(status_code=r.status_code,final_url=r.url,fetched_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),content_type=r.headers.get('content-type'),byte_count=len(r.content));r.raise_for_status()
  (ROOT/(name+'.html')).write_bytes(r.content);entry.update(file=name+'.html',sha256=hashlib.sha256(r.content).hexdigest())
 except requests.RequestException as e:entry['error']=f'{type(e).__name__}: {e}'
 return entry
if __name__=='__main__':
 results=list(ThreadPoolExecutor(max_workers=3).map(fetch,URLS));(ROOT/'probe_manifest.json').write_text(json.dumps({'requests':results,'request_count':len(URLS)},indent=2)+'\n');print(json.dumps(results,indent=2))

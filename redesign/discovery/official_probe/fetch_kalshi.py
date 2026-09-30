from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,pathlib,requests
ROOT=pathlib.Path(__file__).resolve().parent
SERIES=['KXRECSSNBER','KXQRECESS','KXNBERRECESSQ','KXFEDHIKE','KXRATEHIKE','KXU3MAX','KXCANRECESSION']
def fetch(series):
 url='https://external-api.kalshi.com/trade-api/v2/markets';params={'series_ticker':series,'limit':15,'status':'open','mve_filter':'exclude'}
 e={'series':series,'requested_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  r=requests.get(url,params=params,timeout=20);e.update(url=r.url,status_code=r.status_code,fetched_at_utc=datetime.now(timezone.utc).isoformat());r.raise_for_status();f='markets_'+series+'.json';(ROOT/f).write_bytes(r.content);e.update(file=f,sha256=hashlib.sha256(r.content).hexdigest());d=r.json();e['count']=len(d['markets'])
  for m in d['markets'][:3]:print(series,m['ticker'],m['title'],'\nPRIMARY',m['rules_primary'],'\nSECONDARY',m['rules_secondary'],flush=True)
 except requests.RequestException as x:e['error']=str(x)
 return e
if __name__=='__main__':
 requests_=list(ThreadPoolExecutor(max_workers=3).map(fetch,SERIES));(ROOT/'kalshi_market_manifest.json').write_text(json.dumps({'requests':requests_},indent=2)+'\n');print('COUNTS',[(r['series'],r.get('count',r.get('error'))) for r in requests_])

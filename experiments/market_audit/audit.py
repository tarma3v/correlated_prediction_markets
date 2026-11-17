"""Offline analysis of archived top-of-book fields and realized CPI payouts. Python >=3.9."""
import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import mean, median

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
E02 = ROOT / 'experiments/e02/acquisition/2026-11-14'
PILOT = ROOT / 'pilot'
EPS = 1e-8


def read(p):
    return json.loads(p.read_text())


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def clean(x):
    return round(x, 8) if isinstance(x, float) else x


def field(m, k):
    v = m.get(k)
    return None if v in (None, '') else float(v)


def quote(m, venue):
    if venue == 'kalshi':
        bid, ask = (field(m,'yes_' + s + '_dollars') for s in ('bid','ask'))
        bs, sz = (field(m,'yes_' + s + '_size_fp') for s in ('bid','ask'))
        vol, day = field(m, 'volume_fp'), field(m, 'volume_24h_fp')
    else:
        bid, ask = field(m,'bestBid'), field(m,'bestAsk')
        bs = sz = None
        vol, day = field(m,'volume'), field(m,'volume24hr')
    bv = bid is not None and 0 < bid < 1 and (venue != 'kalshi' or bs is not None and bs > 0)
    av = ask is not None and 0 < ask < 1 and (venue != 'kalshi' or sz is not None and sz > 0)
    good = bool(bv and av and bid <= ask)
    return dict(bid=bid, ask=ask, bid_size=bs, ask_size=sz, valid_bid=bv, valid_ask=av,
                two_sided=good, mid=(bid+ask)/2 if good else None,
                spread=ask-bid if good else None, volume=vol, day_volume=day)


def describe(rows):
    def stat(vals):
        if not vals:
            return dict(n=0)
        vs = sorted(vals)
        def pct(p):
            i = (len(vs)-1)*p
            j = int(i)
            return vs[j] if j==len(vs)-1 else vs[j]+(vs[j+1]-vs[j])*(i-j)
        return {k:clean(v) for k,v in dict(n=len(vs),min=min(vs),p25=pct(.25),
                                           median=median(vs),p75=pct(.75),max=max(vs),sum=sum(vs)).items()}
    return dict(n=len(rows),two_sided=sum(q['two_sided'] for q in rows),
                no_24h_trades=sum(q['day_volume']==0 for q in rows),
                volume=stat([q['volume'] for q in rows if q['volume'] is not None]),
                volume24h=stat([q['day_volume'] for q in rows if q['day_volume'] is not None]),
                spread_cents=stat([q['spread']*100 for q in rows if q['two_sided']]))


def cond_coeffs(kind,k):
    # constant and coefficients on YES contracts paying 1[X>k/10], given one common release.
    if kind=='le':
        return 1, {k:-1}
    if kind=='ge':
        return 0, {k-1:1}
    if kind == 'eq':
        return 0, {k-1:1,k:-1}
    raise ValueError(f'Unknown bucket {kind}')


def interval(kquotes,constant,terms):
    # Signed portfolio bid from sale of long legs + repurchase of shorts; ask reverses.
    out=[]
    for side in ('bid','ask'):
        value=constant
        for level,weight in terms.items():
            legside = side if weight>0 else ('ask' if side=='bid' else 'bid')
            q=kquotes[level]
            if not q['valid_'+legside]:
                value=None
                break
            value+=q[legside]*weight
        out.append(value)
    return out


def fee_directions(p,threshold,terms,bid,ask,pm_rate,kalshi_rate):
    directions=[]
    for selling_pm,synthetic in [(True,ask),(False,bid)]:
        if synthetic is None:
            continue
        pm_price=p['bid' if selling_pm else 'ask']
        edge=pm_price-synthetic if selling_pm else synthetic-pm_price
        fees=pm_rate*pm_price*(1-pm_price)
        caps=[]
        for level,weight in terms.items():
            buy_leg=(weight>0)==selling_pm
            side='ask' if buy_leg else 'bid'
            q=threshold[level]
            leg_price=q[side]
            fees+=abs(weight)*kalshi_rate*leg_price*(1-leg_price)
            caps.append(q[side+'_size']/abs(weight))
        directions.append((edge-fees,min(caps),selling_pm))
    return directions


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def main(output=OUT):
    output.mkdir(parents=True, exist_ok=True)
    captured_at = {}
    sources = []
    def verified(manifest,base,entry,filename,expected):
        data=base/filename
        sha=hashlib.sha256(data.read_bytes()).hexdigest()
        if sha!=expected:
            raise ValueError(f'Input hash failed for {data}')
        sources.append(dict(path=str(data.relative_to(ROOT)),sha256=sha,
                            manifest=str(manifest.relative_to(ROOT)),url=entry.get('url',entry.get('request_url')),
                            fetched=entry.get('received_at_utc',entry.get('fetched_at_utc'))))
        return read(data)

    obs = {}
    pman=PILOT/'manifest.json'
    for ent in read(pman)['requests']:
        if not ent['file'].startswith('raw/kalshi_'):
            continue
        data=verified(pman,PILOT,ent,ent['file'],ent['sha256'])
        group='sep_recent' if 'recent' in ent['file'] else 'sep_economics'
        for m in data['response']['markets']:
            obs[group,m['ticker']]=m
            captured_at[group,m['ticker']] = ent['fetched_at_utc']
    eman=E02/'manifest.json'
    er={}
    for ent in read(eman)['requests']:
        er[ent['name']]=verified(eman,E02,ent,ent['raw_file'],ent['raw_sha256'])
    markets=er['kalshi_markets']['markets']
    for m in markets:
        if m['status']=='active':
            obs['nov_core_active',m['ticker']]=m
    poly=er['polymarket_event']['markets']
    bookrows=[]
    for (group,ident),m in obs.items():
        bookrows.append(dict(group=group,venue='kalshi',id=ident,**quote(m,'kalshi')))
    bookrows.extend(dict(group='nov_core_pm',venue='polymarket',id=m['id'],**quote(m,'pm')) for m in poly)
    write_csv(output / 'quotes.csv',[{k:clean(v) for k,v in q.items()} for q in bookrows])
    summary={'snapshots':{group:describe([q for q in bookrows if q['group']==group])
                          for group in sorted({q['group'] for q in bookrows})}}

    # Within an event accept only a common payout text after masking the numeric strike in %.
    groups=defaultdict(list)
    for (group,ident),m in obs.items():
        if group=='sep_recent' or m['strike_type'] not in ('greater','greater_or_equal'):
            continue
        template=re.sub(r'-?\d+(?:\.\d+)?(?=%)', '<k>',m['rules_primary'])
        key=(group,m['event_ticker'],m['strike_type'],template,m.get('rules_secondary'))
        groups[key].append(m)
    nesting=[]
    for (group,event,*_),ms in sorted(groups.items()):
        for low,hi in combinations(sorted(ms,key=lambda m:m['floor_strike']),2):
            if low['floor_strike']==hi['floor_strike']:
                continue
            a,b=quote(low,'kalshi'),quote(hi,'kalshi')
            mid=b['mid']-a['mid'] if a['two_sided'] and b['two_sided'] else None
            edge=b['bid']-a['ask'] if b['valid_bid'] and a['valid_ask'] else None
            nesting.append(dict(sample=group, event=event,low=low['ticker'],high=hi['ticker'],
                                mid_inversion_cents=clean(100*mid) if mid is not None else None,
                                bid_high_minus_ask_low_cents=clean(100*edge) if edge is not None else None))
    write_csv(output / 'nesting.csv',nesting)
    def comparison(rows,mid,edge):
        return dict(n=len(rows),mid_eligible=sum(x[mid] is not None for x in rows),
                    mid_positive=sum(x[mid] is not None and x[mid]>EPS for x in rows),
                    quote_eligible=sum(x[edge] is not None for x in rows),
                    quote_positive=sum(x[edge] is not None and x[edge]>EPS for x in rows))
    summary['nesting']={g:comparison([r for r in nesting if r['sample']==g],
                                     'mid_inversion_cents','bid_high_minus_ask_low_cents')
                        for g in sorted(set(r['sample'] for r in nesting))}

    threshold={round(m['floor_strike']*10):quote(m,'kalshi') for m in markets if m['event_ticker']=='KXCPICORE-26NOV'}
    series=er['kalshi_series']['series']
    assert series['fee_type']=='quadratic'
    kalshi_rate=.07*float(series['fee_multiplier'])
    cross=[]
    for m in poly:
        p=quote(m,'pm')
        label=m['groupItemTitle']
        k=round(float(re.search(r'\d+\.\d+',label).group())*10)
        kind='le' if '≤' in label else ('ge' if '+' in label else 'eq')
        constant,terms=cond_coeffs(kind,k)
        for name,base,legs in [('same_number',0,{k:1}),('ordinary_release',constant,terms)]:
            bid,ask=interval(threshold,base,legs)
            gap=abs(p['mid']-(bid+ask)/2)*100 if p['two_sided'] and bid is not None and ask is not None else None
            # Each feasible direction uses only the required quote side.
            if not p['two_sided']:
                raise ValueError('Expected two-sided PM snapshot')
            edges=[x for x in (p['bid']-ask if ask is not None else None,
                               bid-p['ask'] if bid is not None else None) if x is not None]
            e=max(edges) if edges else None
            assert m['feesEnabled'] and m['feeSchedule']['exponent']==1
            net_dirs=fee_directions(p,threshold,legs,bid,ask,m['feeSchedule']['rate'],kalshi_rate)
            best_net=max(net_dirs,key=lambda row:row[0]) if net_dirs else (None,None,None)
            size100=max((v for v,size,_ in net_dirs if size>=100),default=None)
            cross.append(dict(rule=name,label=label,polymarket_id=m['id'],constant=base,
                              kalshi_terms=' '.join(f'{w:+d}*T{x/10:.1f}' for x,w in legs.items()),
                              pm_bid=p['bid'],pm_ask=p['ask'],kalshi_bid=clean(bid),kalshi_ask=clean(ask),
                              abs_mid_gap_cents=clean(gap),best_bid_minus_ask_cents=clean(100*e) if e is not None else None,
                              unrounded_net_cents=clean(100*best_net[0]) if best_net[0] is not None else None,
                              best_net_sell_pm=best_net[2],kalshi_size_at_best_net=best_net[1],
                              net_if_kalshi_size100_cents=clean(100*size100) if size100 is not None else None))
    write_csv(output / 'november_cross_venue.csv',cross)
    summary['cross_venue']={}
    for name in ('same_number','ordinary_release'):
        rows=[q for q in cross if q['rule']==name]
        counts=comparison(rows,'abs_mid_gap_cents','best_bid_minus_ask_cents')
        for fee in (1,2,5):
            counts[f'greater_than_{fee}_cent_total_cost']=sum(x['best_bid_minus_ask_cents'] is not None and x['best_bid_minus_ask_cents']>fee+EPS for x in rows)
        for col in ('unrounded_net_cents','net_if_kalshi_size100_cents'):
            values=[x[col] for x in rows if x[col] is not None]
            counts[col]=dict(n=len(values),n_positive=sum(x>EPS for x in values),max=max(values))
        summary['cross_venue'][name]=counts

    # Polymarket's displayed winners and the BLS observation were transcribed
    # separately. Check their consistency without using either as the Kalshi leg.
    settled = []
    settlement_input = OUT / 'settlements.csv'
    with settlement_input.open() as f:
        for event in csv.DictReader(f):
            month=event['month']
            actual={round(m['floor_strike']*10):int(float(m['settlement_value_dollars']))
                    for m in markets if m['event_ticker']=='KXCPICORE-'+month and m['status']=='finalized'}
            if len(actual)!=11:
                raise ValueError(f'Expected 11 settled thresholds for {month}')
            labels = event['labels_in_order'].split('|')
            payouts = list(map(int, event['payouts_in_order'].split('|')))
            if len(labels) != len(payouts) or len(set(labels)) != len(labels) or sum(payouts) != 1:
                raise ValueError(f'Invalid bucket settlement vector for {month}')
            release = round(float(event['core_cpi_pct']) * 10)
            for label, y in zip(labels, payouts):
                k=round(float(label[2:])*10);kind=label[:2]
                documented = {'le': release <= k, 'eq': release == k, 'ge': release >= k}[kind]
                if y != documented:
                    raise ValueError(f'BLS and displayed Polymarket payout disagree: {month}/{label}')
                c,terms=cond_coeffs(kind,k)
                rep=c+sum(w*actual[level] for level,w in terms.items())
                settled.append(dict(month=month,label=label,pm_yes=int(y),kalshi_same_number=actual[k],
                                    kalshi_mapped_payout=rep))
    write_csv(output / 'settlement_comparisons.csv',settled)
    summary['settlements']=dict(months=len({r['month'] for r in settled}),n=len(settled),same_number_mismatch=sum(r['pm_yes']!=r['kalshi_same_number'] for r in settled),
                                mapped_mismatch=sum(r['pm_yes']!=r['kalshi_mapped_payout'] for r in settled))
    # September top of book, future outcomes joined by the immutable Kalshi ticker.
    # Scores grouped by release; thresholds for a given month share one realization.
    resolved={m['ticker']:m for m in markets if m['status']=='finalized'}
    score=[]
    for (group,ticker),m in obs.items():
        if group!='sep_economics' or ticker not in resolved:
            continue
        q=quote(m,'kalshi')
        snapshot_time = captured_at[group,ticker]
        settlement = resolved[ticker]
        if not (parse_time(snapshot_time) < parse_time(m['close_time']) <= parse_time(settlement['settlement_ts'])):
            raise ValueError(f'Forecast must precede close and settlement: {ticker}')
        outcome = int(float(settlement['settlement_value_dollars']))
        score.append(dict(market=ticker,event=m['event_ticker'],captured_utc=snapshot_time,
                          closed_utc=m['close_time'],settled_utc=settlement['settlement_ts'],
                          outcome=outcome,mid=clean(q['mid']),
                          brier=clean((q['mid']-outcome)**2) if q['mid'] is not None else None))
    write_csv(output / 'september_forward_scores.csv',score)
    summary['september_forecasts']={}
    for event in sorted(set(q['event'] for q in score)):
        rows=[q for q in score if q['event']==event]
        good=[q for q in rows if q['mid'] is not None]
        summary['september_forecasts'][event]=dict(n=len(rows),two_sided=len(good),
             yes=sum(q['outcome'] for q in good),brier=clean(mean(q['brier'] for q in good)) if good else None,
             always_no=clean(mean(q['outcome'] for q in good)) if good else None,half=0.25 if good else None)
    summary['settlement_input_sha256'] = hashlib.sha256(settlement_input.read_bytes()).hexdigest()
    summary['sources']=sources
    (output/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='sources'},indent=2))

if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    main(parser.parse_args().output)

#!/usr/bin/env python3
"""Bounded public metadata collection and offline lexical candidate retrieval.
No authentication, private endpoints, orders, LLM calls or inferred gold labels.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

BASE = Path(__file__).resolve().parent
KALSHI = 'https://external-api.kalshi.com/trade-api/v2'
SERIES = ['KXCPI', 'KXCPIYOY', 'KXCPICORE', 'KXCPICOREYOY', 'KXU3', 'KXFEDRATEMIN', 'KXLCPIMAXYOY']


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def input_digest(record):
    fields = ['venue', 'id', 'event_id', 'title', 'subtitle', 'primary', 'secondary', 'resolution_source', 'source_api_url', 'close_time', 'expected_expiration_time', 'floor_strike', 'cap_strike', 'strike_type']
    canonical = json.dumps({k: record.get(k) for k in fields}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return digest(canonical.encode('utf-8'))


def fetch(url, params, name, root):
    import requests
    request = requests.Request('GET', url, params=params).prepare()
    entry = {'request_url': request.url, 'requested_at_utc': now(), 'file': f'raw/{name}.json'}
    try:
        response = requests.get(url, params=params, timeout=25)
        entry.update(status_code=response.status_code, fetched_at_utc=now())
        response.raise_for_status()
        data = response.json()
        envelope = {**entry, 'response': data}
        write_json(root / entry['file'], envelope)
        entry['sha256'] = digest((root / entry['file']).read_bytes())
        print(name, 'OK', flush=True)
        return data, entry
    except (requests.RequestException, ValueError) as exc:
        entry.update(error=f'{type(exc).__name__}: {exc}', fetched_at_utc=now())
        write_json(root / entry['file'], entry)
        entry['sha256'] = digest((root / entry['file']).read_bytes())
        print(name, 'FAILED', entry['error'][:150], flush=True)
        return None, entry


def collect(args):
    root = args.root
    if (root / 'manifest.json').exists() and not args.overwrite:
        raise SystemExit('Snapshot exists. Use a new --root to preserve it, or explicit --overwrite.')
    entries, normalized = [], {}
    plans = [('kalshi_recent', KALSHI + '/markets', {'limit': 80, 'status': 'open', 'mve_filter': 'exclude'})]
    plans += [(f'kalshi_{s}', KALSHI + '/markets', {'limit': 40, 'status': 'open', 'mve_filter': 'exclude', 'series_ticker': s}) for s in SERIES]
    plans += [(f'metadata_{s}', KALSHI + '/series/' + s, {}) for s in ['KXCPIYOY', 'KXLCPIMAXYOY']]
    plans += [('polymarket_open', 'https://gamma-api.polymarket.com/markets', {'limit': 100, 'closed': 'false', 'order': 'volumeNum', 'ascending': 'false'})]
    for name, url, params in plans:
        data, entry = fetch(url, params, name, root)
        entries.append(entry)
        if data is None or name.startswith('metadata_'):
            continue
        records = data.get('markets', []) if name.startswith('kalshi') else data
        for m in records:
            if name.startswith('kalshi'):
                rec = {'venue': 'kalshi', 'id': m['ticker'], 'event_id': m.get('event_ticker'), 'title': m.get('title', ''),
                       'primary': m.get('rules_primary', ''), 'secondary': m.get('rules_secondary', ''),
                       'subtitle': m.get('yes_sub_title', ''), 'source_api_url': KALSHI + '/markets/' + m['ticker'],
                       'close_time': m.get('close_time'), 'expected_expiration_time': m.get('expected_expiration_time'),
                       'floor_strike': m.get('floor_strike'), 'cap_strike': m.get('cap_strike'), 'strike_type': m.get('strike_type')}
            else:
                rec = {'venue': 'polymarket', 'id': str(m['id']), 'event_id': ','.join(str(e['id']) for e in m.get('events', [])),
                       'title': m.get('question', ''), 'primary': m.get('description', ''), 'secondary': '',
                       'subtitle': m.get('groupItemTitle', ''), 'source_api_url': 'https://gamma-api.polymarket.com/markets/' + str(m['id']),
                       'resolution_source': m.get('resolutionSource'), 'close_time': m.get('endDate')}
            rec['raw_file'] = entry['file']
            rec['fetched_at_utc'] = entry['fetched_at_utc']
            rec['text_sha256'] = digest((rec['primary'] + '\n' + rec['secondary']).encode())
            rec['input_sha256'] = input_digest(rec)
            normalized[(rec['venue'], rec['id'])] = rec
    write_json(root / 'markets.json', list(normalized.values()))
    write_json(root / 'manifest.json', {'normalized_file': 'markets.json', 'markets_sha256': digest((root / 'markets.json').read_bytes()), 'collected_at_utc': now(), 'selection': 'convenience sample: latest 80 non-combo open Kalshi markets and first 40 open markets for seven named economic series; first 100 Polymarket open markets by volume if reachable. No full pagination.', 'requests': entries})
    print('unique_markets', len(normalized), flush=True)


def analyze(args):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    root = args.root
    manifest = json.loads((root / 'manifest.json').read_text())
    if digest((root / 'markets.json').read_bytes()) != manifest['markets_sha256']:
        raise ValueError('Normalized markets hash mismatch')
    records = json.loads((root / 'markets.json').read_text())
    for record in records:
        if input_digest(record) != record['input_sha256']:
            raise ValueError('Normalized record input hash mismatch: ' + record['id'])
    if len({(r['venue'], r['id']) for r in records}) != len(records):
        raise ValueError('Duplicate market identifiers')
    for entry in json.loads((root / 'manifest.json').read_text())['requests']:
        if digest((root / entry['file']).read_bytes()) != entry['sha256']:
            raise ValueError('Raw snapshot hash mismatch: ' + entry['file'])
    variants = {'title': lambda r: r['title'], 'rules': lambda r: r['primary'] + '\n' + r['secondary'],
                'title_rules': lambda r: r['title'] + '\n' + r['primary'] + '\n' + r['secondary']}
    scores, candidates, stat = {}, {}, {}
    for name, fn in variants.items():
        texts = [fn(r) for r in records]
        # Keep digits and punctuation-bearing numbers as character features.
        word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r'(?u)\b\w+\b').fit_transform(texts)
        char = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True).fit_transform(texts)
        sim = (0.5 * (word @ word.T) + 0.5 * (char @ char.T)).toarray()
        np.fill_diagonal(sim, -1.0)
        scores[name] = sim
        edges = set()
        for i in range(len(records)):
            # Stable tie break by corpus order. No randomness.
            for j in np.argsort(-sim[i], kind='stable')[:args.top_k]:
                if sim[i, j] > 0:
                    pair = tuple(sorted((i, int(j))))
                    edges.add(pair)
                    candidates.setdefault(pair, set()).add(name)
        stat[name] = {'candidate_pairs': len(edges), 'cross_event_pairs': sum(records[i]['event_id'] != records[j]['event_id'] for i,j in edges)}
    pair_rows = []
    for (i,j), methods in sorted(candidates.items()):
        a,b = records[i], records[j]
        pair_rows.append({'a': a['id'], 'b': b['id'], 'venue_a': a['venue'], 'venue_b': b['venue'], 'same_event': a['event_id'] == b['event_id'],
                          'title_a': a['title'], 'title_b': b['title'], 'retrieved_by': sorted(methods),
                          **{f'sim_{k}': round(float(s[i,j]), 6) for k,s in scores.items()}})
    pair_rows.sort(key=lambda r: (-r['sim_title_rules'], r['a'], r['b']))
    write_json(root / 'results/candidates.json', pair_rows)
    title_groups = Counter(r['title'].strip().lower() for r in records)
    possible = len(records) * (len(records) - 1) // 2
    summary = {'generated_at_utc': now(), 'input_markets_sha256': manifest['markets_sha256'], 'python': platform.python_version(), 'dependencies': {p: importlib.metadata.version(p) for p in ['requests', 'numpy', 'scikit-learn']},
               'markets': len(records), 'venues': dict(Counter(r['venue'] for r in records)), 'events': len({(r['venue'], r['event_id']) for r in records}),
               'missing_primary': sum(not r['primary'].strip() for r in records), 'missing_secondary': sum(not r['secondary'].strip() for r in records),
               'identical_title_groups': sum(v > 1 for v in title_groups.values()), 'possible_pairs': possible, 'top_k': args.top_k,
               'candidate_union_pairs': len(pair_rows), 'union_fraction_of_all_pairs': len(pair_rows)/possible if possible else 0,
               'retrievers': stat, 'interpretation': 'Engineering and descriptive results only. No gold labels, accuracy, recall or tradable arbitrage measurements.'}
    write_json(root / 'results/summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=BASE)
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('collect'); c.add_argument('--overwrite', action='store_true'); c.set_defaults(func=collect)
    a = sub.add_parser('analyze'); a.add_argument('--top-k', type=int, default=5); a.set_defaults(func=analyze)
    args = parser.parse_args()
    if hasattr(args, 'top_k') and args.top_k < 1: parser.error('--top-k must be positive')
    args.func(args)

if __name__ == '__main__': main()

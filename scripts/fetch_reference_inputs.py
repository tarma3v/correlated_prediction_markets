"""Fetch the pinned upstream fixture and reconstruct ignored retrieval inputs.

No third-party license is inferred. Exact snapshots are downloaded from their
original publisher and kept out of Git; the expected SHA-256 is mandatory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    source = json.loads((ROOT/'redesign/datasets/source.json').read_text())
    raw_path = ROOT/'redesign/datasets/rawsamples/nl2992_endorsed_fixture.txt'
    if raw_path.exists():
        content = raw_path.read_bytes()
    elif args.offline:
        raise SystemExit('Pinned fixture unavailable locally; rerun without --offline.')
    else:
        context = ssl.create_default_context()
        try:
            import certifi
        except ImportError:
            pass
        else:
            context.load_verify_locations(certifi.where())
        request = urllib.request.Request(source['source_url'], headers={'User-Agent':'resolution-research-reproduction'})
        with urllib.request.urlopen(request, context=context, timeout=60) as response:
            content = response.read()
    if hashlib.sha256(content).hexdigest() != source['sha256']:
        raise SystemExit('Source SHA-256 mismatch; inputs were not written.')
    data = json.loads(content)
    pairs, markets = {}, {'poly': {}, 'kalshi': {}}
    for subset in ['signal_subset', 'stratified_subset']:
        for row in data[subset]:
            key = row['poly_id'], row['kalshi_ticker']
            if key in pairs:
                assert pairs[key]['label'] == row['label']
                pairs[key]['subsets'].append(subset)
            else:
                pairs[key] = dict(row, subsets=[subset])
            for venue, identity in [('poly', key[0]), ('kalshi', key[1])]:
                record = {'id': identity, 'title': row[venue+'_title'], 'event_title': row[venue+'_event_title']}
                assert identity not in markets[venue] or markets[venue][identity] == record
                markets[venue][identity] = record
    assert len(pairs) == 493
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(content)
    raw_path.with_name('nl2992_pinned_audit.json').write_bytes(content)
    save(ROOT/'redesign/retrieval/markets.json', {v:[m[k] for k in sorted(m)] for v,m in markets.items()})
    save(ROOT/'redesign/retrieval/reference_pairs.json', list(pairs.values()))
    manifest = json.loads((ROOT/'comparison/retrieval/run_manifest.json').read_text())
    for name in ['redesign/retrieval/markets.json','redesign/retrieval/reference_pairs.json']:
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == manifest['inputs_sha256'][name], name
    print('Verified upstream SHA-256 and reconstructed the two original retrieval inputs (493 pairs).')


if __name__ == '__main__':
    main()

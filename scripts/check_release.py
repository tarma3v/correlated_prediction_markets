#!/usr/bin/env python3
"""Read-only release inventory: paths/sizes/line numbers only, never source values.

Default scope is git's tracked + untracked, non-ignored candidate files. This is
not a secret-content scanner and does not establish dataset redistribution rights.
Public/private profiles change advisory source-data findings, not permissions.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CACHE_PARTS = {'.git', '.venv', 'venv', '__pycache__', '.ipynb_checkpoints',
               'node_modules', '.cache', 'hf_cache', 'tmp'}
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.json', '.jsonl', '.ipynb', '.yml',
                 '.yaml', '.toml', '.sh', '.cfg', '.ini', '.csv', '.tsv'}
BINARY_SUFFIXES = {'.pdf', '.png', '.jpg', '.jpeg', '.npz', '.npy', '.parquet',
                   '.zip', '.gz', '.pkl', '.pickle', '.bin', '.pt', '.safetensors'}
LOCAL_PATH = re.compile(r'(?<![\w:/])/(?:Users|home)/[A-Za-z0-9_.-]+(?:/[^\s<>"\x27)]*)?')
URL = re.compile(r'https?://[^\s<>"\x27]+')
# Known fetched corpora with no explicit dataset reuse license in saved metadata.
UNKNOWN_LICENSE_PREFIXES = ('redesign/datasets/rawsamples/nl2992_',
                            'redesign/datasets/rawsamples/kalshibench_')
UNKNOWN_LICENSE_FILES = {'redesign/datasets/author_audit_pairs_unique.json',
                         'redesign/datasets/author_audit_negative_pairs.json',
                         'redesign/datasets/kalshi_author_audit_markets.json',
                         'redesign/datasets/polymarket_author_audit_markets.json',
                         'redesign/retrieval/markets.json',
                         'redesign/retrieval/reference_pairs.json',
                         'redesign/retrieval/results.json'}


def credential_name(path: Path) -> bool:
    n = path.name.lower()
    if n in {'.env.example', '.env.sample', '.env.template'}:
        return False
    return (n == '.env' or n.startswith('.env.') or
            n in {'.netrc', '.npmrc', '.pypirc', 'id_rsa', 'id_ed25519',
                  'credentials', 'credentials.json', 'credentials.yaml',
                  'service-account.json', 'secrets.json', 'secrets.toml',
                  'token.json', 'tokens.json', 'auth.json'} or
            path.suffix.lower() in {'.p12', '.pfx', '.key'} or
            any(part in {'.ssh', '.aws', '.kube'} for part in path.parts))


def candidate_paths(args):
    if args.files:
        raw = args.files.read_text(encoding='utf-8')
        values = json.loads(raw) if raw.lstrip().startswith('[') else raw.splitlines()
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError('--files must contain a JSON string list or one relative path per line')
    else:
        command = ['git', '-C', str(ROOT), 'ls-files', '-z', '--cached']
        if not args.tracked_only:
            command += ['--others', '--exclude-standard']
        result = subprocess.run(command, capture_output=True, check=True)
        values = [v.decode('utf-8') for v in result.stdout.split(b'\0') if v]
    return sorted(set(v for v in values if v))


def inspect(args):
    paths = candidate_paths(args)
    findings, artifacts = [], []
    cache_roots = {}
    total = 0
    def add(path, code, severity, **details):
        # Findings deliberately contain no matching text or credential values.
        findings.append({'path': path, 'code': code, 'severity': severity, **details})
    for relative in paths:
        rel = PurePosixPath(relative)
        if rel.is_absolute() or '..' in rel.parts:
            add('<invalid candidate path>', 'outside_repository', 'block')
            continue
        path = ROOT / relative
        cache_index = next((i for i, part in enumerate(rel.parts)
                            if part in CACHE_PARTS or part.startswith(('.venv-', '.venv_', 'venv-'))), None)
        if cache_index is not None:
            cache_root = '/'.join(rel.parts[:cache_index + 1])
            record = cache_roots.setdefault(cache_root, {'files': 0, 'size_bytes': 0})
            record['files'] += 1
            if path.is_file() and not path.is_symlink():
                size = path.stat().st_size
                record['size_bytes'] += size
                total += size
            continue  # Third-party packages/examples/certificates are not project secrets.
        if path.is_symlink():
            add(relative, 'symlink_review', 'review')
            continue
        if not path.is_file():
            add(relative, 'missing_candidate', 'review')
            continue
        size = path.stat().st_size
        total += size
        if credential_name(rel):
            add(relative, 'credential_like_filename', 'block')
            continue  # Never read contents of credential-named files.
        if path.suffix.lower() == '.pem':
            add(relative, 'certificate_or_key_material', 'review')
            continue
        if size >= 100 * 1024**2:
            add(relative, 'github_file_size_limit', 'block', size_bytes=size)
        elif size >= args.large_mb * 1024**2:
            add(relative, 'large_file', 'review', size_bytes=size)
        if path.suffix.lower() in BINARY_SUFFIXES:
            artifacts.append({'path': relative, 'size_bytes': size})
        if args.profile == 'public':
            if relative in UNKNOWN_LICENSE_FILES or relative.startswith(UNKNOWN_LICENSE_PREFIXES):
                add(relative, 'third_party_license_unspecified', 'note')
            if (relative.startswith('extension/terms/') and path.suffix.lower() in {'.pdf', '.txt', '.png', '.html'}) or relative.startswith('redesign/discovery/') and path.suffix.lower() in {'.json', '.txt'}:
                add(relative, 'upstream_document_or_snapshot', 'note')
        if path.suffix.lower() not in TEXT_SUFFIXES or size > 20 * 1024**2:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeError, OSError):
            continue
        # Exclude HTTP URLs: an upstream URL containing /home/ is not a local path.
        for n, line in enumerate(text.splitlines(), 1):
            without_urls = URL.sub('', line)
            if LOCAL_PATH.search(without_urls):
                add(relative, 'literal_home_path', 'review', line=n)
            if path.suffix == '.py' and path.resolve() != Path(__file__).resolve() and ('/System/Library/Fonts/' in line or '/Library/Fonts/' in line or "'/System/Library/Fonts'" in line):
                add(relative, 'macos_font_dependency', 'review', line=n)
        if path.suffix == '.ipynb':
            try:
                nb = json.loads(text)
            except json.JSONDecodeError:
                add(relative, 'invalid_notebook_json', 'block')
                continue
            for index, cell in enumerate(nb.get('cells', []), 1):
                if any(o.get('output_type') == 'error' for o in cell.get('outputs', [])):
                    add(relative, 'notebook_error_output', 'review', cell=index)
    for cache_root, record in sorted(cache_roots.items()):
        add(cache_root, 'cache_or_environment', 'block', **record)
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'explicit_file_list' if args.files else ('git_tracked' if args.tracked_only else 'git_candidate_files'),
            'profile': args.profile, 'candidate_count': len(paths), 'total_bytes': total,
            'findings_by_code': dict(Counter(f['code'] for f in findings)),
            'findings': findings, 'binary_artifacts': artifacts,
            'limitations': ['No secret-value search; only credential-like filenames are checked.',
                           'No network access or package execution; no license permission inference.',
                           'Frozen source snapshots and recorded hashes are never modified.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['private', 'public'], default='private')
    parser.add_argument('--files', type=Path, help='JSON list or newline-separated repository-relative paths')
    parser.add_argument('--tracked-only', action='store_true')
    parser.add_argument('--large-mb', type=float, default=5.0)
    parser.add_argument('--json', type=Path, help='Optional JSON report path (only paths, sizes, categories)')
    parser.add_argument('--strict', action='store_true', help='Nonzero for review findings too; default only block findings')
    args = parser.parse_args()
    report = inspect(args)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Checked {report['candidate_count']} candidate files; {report['total_bytes'] / 1024**2:.1f} MiB; profile={args.profile}")
    for code, count in sorted(report['findings_by_code'].items()):
        print(f'{code}: {count}')
    print('No source text or credential values are logged.')
    severities = {'block', 'review'} if args.strict else {'block'}
    return int(any(f['severity'] in severities for f in report['findings']))


if __name__ == '__main__':
    sys.exit(main())

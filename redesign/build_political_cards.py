"""Preserve three explicitly provisional, source-grounded political case cards."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'cards'


def source(name, relative, url, provenance, locator):
    path = ROOT / relative
    obj = json.loads(path.read_text())
    result = {'source_id': name, 'provenance': provenance, 'url': url,
        'retrieved_at_utc': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        'upstream_timestamp': None, 'local_path': relative,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'locator': locator,
        'coverage_note': ('Public ClearMarket copy of venue rules_raw. Editorial fields are excluded. '
                          'Direct Gamma version not verified; fetched time derived from saved-file mtime.'
                          if provenance == 'curated_snapshot' else
                          'Official current market API primary/secondary fields; series/rulebook not fetched for this case.')}
    return result, obj


def main():
    OUT.mkdir(exist_ok=True)
    sources, contracts, raw_rules = {}, {}, {}
    for name, slug, relative in [
        ('resign', 'will-trump-resign-by-december-31-2026', 'discovery/clearmarket/will-trump-resign-by-december-31-2026.json'),
        ('out', 'trump-out-as-president-before-2027', 'discovery/clearmarket/trump-out-as-president-before-2027.json'),
        ('impeach', 'will-trump-be-impeached-by-december-31-2026', 'discovery/political/impeachment.json')]:
        src, obj = source(name, relative, 'https://api.clearmarket.fyi/v1/events/'+slug,
                          'curated_snapshot', '/markets/0/resolution/rules_raw')
        market = obj['markets'][0]
        src['upstream_timestamp'] = market.get('last_checked_at')
        sources[name] = src
        contracts[name] = {'platform': 'polymarket', 'market_id': market['platform_market_id'],
            'title': market['question'], 'market_url': 'https://polymarket.com/event/'+slug,
            'source_ids': [name], 'yes_proposition': None, 'proposition_status': 'unavailable'}
        raw_rules[name] = market['resolution']['rules_raw']
    ticker = 'KXTRUMPOUT27-27-DJT'
    sources['kalshi_out'], obj = source('kalshi_out', 'discovery/political/kalshi_out.json',
        'https://external-api.kalshi.com/trade-api/v2/markets/'+ticker,
        'official_api', '/market/rules_primary and /market/rules_secondary')
    market = obj['market']
    contracts['kalshi_out'] = {'platform': 'kalshi', 'market_id': ticker,
        'event_id': market['event_ticker'], 'title': market['title'],
        'market_url': sources['kalshi_out']['url'], 'source_ids': ['kalshi_out'],
        'yes_proposition': None, 'proposition_status': 'unavailable'}
    raw_rules['kalshi_out'] = market['rules_primary']+'\n'+market['rules_secondary']
    props = {
        'resign': 'By December 31, 2026, 11:59 PM ET, Donald Trump announces that he has resigned or will resign the presidency, before an event makes such an announcement impossible.',
        'out': 'By December 31, 2026, 11:59 PM ET, Donald Trump permanently ceases to be US President, or his resignation or permanent removal is announced; sustained Section 4 removal qualifies and impeachment without removal does not.',
        'impeach': 'Between July 24, 2025 and December 31, 2026, 11:59 PM ET, the US House passes at least one article of impeachment of Donald Trump by a simple majority.'}
    for name, prop in props.items():
        contracts[name].update(yes_proposition=prop, proposition_status='faithful_under_scope')
    now = datetime.now(timezone.utc).isoformat()

    def evidence(name, support):
        return {'source_id': name, 'locator': sources[name]['locator'], 'support': support}

    def card(pid, a, b, mechanism):
        return {'schema_version': '1.0', 'pair_id': pid, 'domain': 'politics',
            'mechanism': mechanism,
            'selection': {'selected_at_utc': now, 'selection_reason': mechanism,
                'template_family': pid, 'within_event_control': False,
                'prior_model_output_seen': False},
            'contracts': {'A': contracts[a], 'B': contracts[b]},
            'sources': [sources[a], sources[b]],
            'scope': {'binary_regime': 'Logical reading of the saved resolution texts with mutually consistent reports; ordinary binary settlement only.',
                'assumptions': ['The saved rules apply unchanged.', 'Reports agree on stipulated facts and announcements.',
                                'The deadline is interpreted identically as written.'],
                'excluded_branches': ['Oracle disputes and subsequent rule changes.'],
                'source_coverage': 'resolution_text_only',
                'missing_information': ['Direct current Gamma confirmation of the third-party copy.']},
            'comparison': [], 'worlds': {}, 'conclusion': '',
            'review': {'status': 'ai_assisted_provisional',
                'method': 'AI-assisted clause reading; not independent human gold. No learned pair classifier used for card selection.',
                'counterexample_search': ''}}

    c = card('politics_resignation_departure', 'resign', 'out', 'Narrow event versus broader event, including announcement clauses.')
    e1 = evidence('resign', 'Announcement is sufficient even if resignation never takes effect.')
    e2 = evidence('out', 'Announcement of resignation/removal by the deadline immediately qualifies.')
    c['comparison'] = [{'dimension': 'predicate', 'finding': 'Both cover announced resignation; departure also covers other permanent removal.', 'evidence': [e1,e2]}]
    reasons = {'00': ('witness','No qualifying resignation announcement, departure, or removal by the deadline.'),
        '01': ('witness','Permanent removal by other means occurs with no resignation announcement; resignation then becomes impossible.'),
        '10': ('forbidden','A qualifying resignation announcement under A is explicitly a qualifying announcement under B, within the declared common-report scope.'),
        '11': ('witness','Trump announces a permanent resignation before the deadline while still able to do so.')}
    c['worlds'] = {w:{'status':s,'reason':r,'evidence':[e1,e2]} for w,(s,r) in reasons.items()}
    c['conclusion'] = 'Conditional A⇒B, not equivalence. The conclusion applies to the saved textual predicates under the stated reporting assumptions.'
    c['review']['counterexample_search'] = 'Resignation announced for a later effective date does not defeat implication because B also expressly counts announcements.'
    cards = [c]

    c = card('politics_impeachment_departure', 'impeach', 'out', 'Similar political event, but impeachment and removal are distinct predicates.')
    e1 = evidence('impeach', 'Senate trial, conviction and removal are not necessary for YES.')
    e2 = evidence('out', 'Impeachment without removal does not count; resignation and other permanent departures do.')
    c['comparison'] = [{'dimension':'predicate','finding':'House impeachment and permanent departure do not imply one another.','evidence':[e1,e2]}]
    scenarios = {'00':'Neither impeachment nor a qualifying departure occurs.',
        '01':'A resignation is announced; no House article of impeachment is passed in the specified window.',
        '10':'The House passes impeachment; Trump remains President without a qualifying departure announcement.',
        '11':'Impeachment is followed by a qualifying permanent removal, both within the window.'}
    c['worlds'] = {w:{'status':'witness','reason':r,'evidence':[e1,e2]} for w,r in scenarios.items()}
    c['conclusion'] = 'All four states have textual witnesses in the declared scope: no strict logical relation. This says nothing about statistical correlation.'
    c['review']['counterexample_search'] = 'Both implication directions have explicit scenarios; the two contracts can also both resolve YES.'
    cards.append(c)

    c = card('politics_crossvenue_departure', 'out', 'kalshi_out', 'Near-identical cross-venue titles conceal a nonbinary settlement branch.')
    c['scope']['binary_regime'] = 'No global binary model asserted: Kalshi explicitly has a last-traded-price/fair-allocation branch.'
    c['scope']['source_coverage'] = 'partial_or_conflicting'
    c['scope']['excluded_branches'] = []
    c['scope']['missing_information'].append('Applicable Kalshi series terms/rulebook and exact interpretation of exceptional branches.')
    e1 = evidence('kalshi_out', 'Departure solely because of death triggers last-traded-price settlement or committee fair allocation, rather than a guaranteed binary YES/NO.')
    e2 = evidence('out', 'The saved text specifies YES/NO on qualifying departure and announcements; it does not state the same price-settlement exception.')
    c['comparison'] = [{'dimension':'cancellation','finding':'Payout domain differs in an explicit Kalshi branch. A binary-equivalence detector must stop or expand its payout model.','evidence':[e1,e2]},
        {'dimension':'time','finding':'Kalshi counts an announcement of departure within the next year; the Polymarket announcement clause states no matching effective-date cap.','evidence':[evidence('kalshi_out','Announcement of leaving within the next year qualifies.'),evidence('out','Announcement qualifies regardless of when it takes effect.')]}]
    c['worlds'] = {w:{'status':'unknown','reason':'The ordinary binary subset was not assessed separately in this card. This is not a claim that binary witnesses are impossible or inherently unknowable. The global payout domain includes an explicit nonbinary branch.','evidence':[e1]} for w in ['00','01','10','11']}
    c['conclusion'] = 'Binary equivalence is unsupported. The concrete obstruction is a payout-domain mismatch, in addition to an announcement-horizon difference.'
    c['review']['counterexample_search'] = 'Tested exceptional departure and an announcement effective more than a year later; only the payout branch is directly established without additional factual assumptions.'
    cards.append(c)

    import jsonschema
    schema = json.loads((ROOT/'schema.json').read_text())
    for card_ in cards:
        jsonschema.validate(card_, schema)
        (OUT/(card_['pair_id']+'.json')).write_text(json.dumps(card_,ensure_ascii=False,indent=2)+'\n')
    (OUT/'political_inputs.json').write_text(json.dumps(raw_rules,ensure_ascii=False,indent=2)+'\n')
    print('Validated',len(cards),'provisional cards. No inference performed.')


if __name__ == '__main__':
    main()

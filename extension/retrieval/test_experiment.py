"""Meaningful boundary tests; synthetic inputs, no accuracy claims."""
import unittest
from experiment import exact_decimal, extract, generate_threshold_candidates, implies


def fixture(ticker, threshold, comparator='above', **changes):
    result={'id':ticker,'venue':'synthetic','event_id':'same-event',
            'primary':f'If the measured rate is {comparator} {threshold}% in October 2026, then the market resolves to Yes.',
            'secondary':'Use the initial official release, not revisions.','resolution_source':'Official source A',
            'close_time':'2026-11-01T00:00:00Z','expected_expiration_time':'2026-11-02T00:00:00Z','floor_strike':None}
    result.update(changes);return result


class ImplicationBoundaryTests(unittest.TestCase):
    def test_all_operator_combinations_higher_implies_lower(self):
        for a in ['>','>=']:
            for b in ['>','>=']:
                with self.subTest(a=a,b=b):
                    self.assertTrue(implies(a,'100',b,'90'))
                    self.assertFalse(implies(a,'90',b,'100'))

    def test_equal_threshold_strictness(self):
        self.assertTrue(implies('>','100','>=','100.00'))
        self.assertFalse(implies('>=','100.00','>','100'))
        self.assertTrue(implies('>','100','>','100.00'))
        self.assertTrue(implies('>=','100','>=','100.00'))

    def test_decimal_exactness_negative_and_signed_zero(self):
        self.assertTrue(implies('>=','0.1000000000000000001','>','0.1'))
        self.assertFalse(implies('>=','0.1','>','0.1000000000000000001'))
        self.assertTrue(implies('>=','-2','>','-3'))
        self.assertFalse(implies('>=','-0.000','>','0'))

    def test_no_float_nonfinite_or_unknown_operator(self):
        for v in [0.1,'NaN','Infinity','-Infinity','bad','1,5','1,00,000']:
            with self.subTest(v=v),self.assertRaises(ValueError):exact_decimal(v)
        with self.assertRaises(ValueError):implies('<','1','>','2')


class ExtractionAndCompatibilityTests(unittest.TestCase):
    def test_lexical_extraction_preserves_decimal_and_operator(self):
        r=extract(fixture('A','0.1000000000000000001','at least'))
        self.assertEqual(r['operator'],'>=')
        self.assertEqual(r['threshold'],'0.1000000000000000001')
        self.assertEqual(r['primary_evidence'][slice(*r['threshold_span'])],r['threshold_lexical'])
        self.assertIn('full_contract_terms_not_reviewed',r['certification_abstain_reasons'])

    def test_threshold_only_pair_and_direction(self):
        records=[fixture('A','0.9'),fixture('B','0.8')]
        _,pairs,_=generate_threshold_candidates(records,{})
        self.assertEqual(len(pairs),1)
        self.assertTrue(pairs[0]['a_implies_b']);self.assertFalse(pairs[0]['b_implies_a'])
        self.assertEqual(pairs[0]['certification'],'abstain_full_contract_guarantee')

    def test_incompatible_templates_sources_dates_secondary_or_event(self):
        base=fixture('A','0.9')
        changes=[{'event_id':'other-event'},
                 {'secondary':'Use the revised official release.'},
                 {'resolution_source':'Official source B'},
                 {'close_time':'2026-11-03T00:00:00Z'},
                 {'primary':fixture('B','0.8')['primary'].replace('October','November')},
                 {'primary':fixture('B','0.8')['primary'].replace('%','basis points')},
                 {'primary':fixture('B','0.8')['primary'].replace('measured rate','different measure')}]
        for change in changes:
            with self.subTest(change=change):
                _,pairs,_=generate_threshold_candidates([base,fixture('B','0.8',**change)],{})
                self.assertEqual(pairs,[])

    def test_known_series_source_conflict_prevents_group(self):
        _,pairs,_=generate_threshold_candidates([fixture('SA-A','0.9'),fixture('SB-B','0.8')],
                                                {'SA':[{'name':'A'}],'SB':[{'name':'B'}]})
        self.assertEqual(pairs,[])

    def test_ambiguous_multiple_or_unsupported_numeric_comparisons_abstain(self):
        samples=['If the rate is not above 0.9%, then the market resolves to Yes.',
                 'If the rate is above 0.9% and employment is above 2%, then the market resolves to Yes.',
                 'If the rate is between 0.5% and 0.9%, then the market resolves to Yes.',
                 'If the rate is above 1,5%, then the market resolves to Yes.',
                 'If the rate is above 1e3%, then the market resolves to Yes.']
        for text in samples:
            with self.subTest(text=text):self.assertEqual(extract(fixture('A','0.9',primary=text))['status'],'abstain')

    def test_conflicting_structured_strike_abstains(self):
        x=extract(fixture('A','0.9',floor_strike=0.8))
        self.assertEqual(x['status'],'abstain');self.assertIn('floor_strike_disagrees_with_text',x['abstain_reasons'])

    def test_operator_wording_not_canonicalized_into_same_group(self):
        _,pairs,_=generate_threshold_candidates([fixture('A','1','above'),fixture('B','1','at least')],{})
        self.assertEqual(pairs,[])

    def test_missing_source_never_certifies_full_contract(self):
        _,pairs,_=generate_threshold_candidates([fixture('A','0.9',resolution_source=None),fixture('B','0.8',resolution_source=None)],{})
        self.assertEqual(len(pairs),1)
        self.assertIn('source_incomplete',pairs[0]['certification_abstain_reasons'])


if __name__=='__main__':unittest.main()

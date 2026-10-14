"""Evaluator mechanics tests; these are not comparison-arm implementations."""
import copy
import math
import types
import unittest
import acceptance as a

class EvaluatorTests(unittest.TestCase):
    def test_inventory(self):
        self.assertEqual(len(a.PLAN['case_families']),26)
        self.assertEqual([sum(c['introduced_stage']<=s for c in a.PLAN['case_families'])*2+4 for s in (0,1,2)],[40,48,56])
    def test_all_mutations_construct(self):
        for case in a.PLAN['case_families']:
            for ambient in ('5','25'):
                self.assertEqual(len(a.case_inputs(case,ambient)),5)
    def test_nan_safe_and_type_strict(self):
        source={'a':[float('nan'),True,0.0]}
        self.assertTrue(a.same(source,copy.deepcopy(source)))
        changed=copy.deepcopy(source);changed['a'][1]=1
        self.assertFalse(a.same(source,changed))
        changed=copy.deepcopy(source);changed['a'][0]=0
        self.assertFalse(a.same(source,changed))
    def test_mutations_are_isolated(self):
        args=a.case_inputs('NONFINITE','5')
        self.assertTrue(any(math.isnan(x) for p in args[3] for x in p['fields'].values()))
        self.assertTrue(all(math.isfinite(x) for p in a.case_inputs('BASE','5')[3] for x in p['fields'].values()))
    def test_immutable_even_exception(self):
        def mutate(x): x.append(1);raise ValueError('original')
        with self.assertRaisesRegex(AssertionError,'mutated'): a.checked_call(mutate,[])
    def test_oracle_all_versions(self):
        for v in (1,2,3):
            for ambient in ('5','25'):
                expected=a.expected_result(v,ambient)
                self.assertEqual(len(expected['boundaries']),7)
                for cls,ids in a.QUERY_IDS.items():
                    self.assertEqual([r['boundary_id'] for r in expected['boundaries'] if cls in r['canonical_ancestors']],ids)
                for record in expected['boundaries']:
                    self.assertEqual(record['producer']['schema_version'],f'{v}.0')
                    self.assertEqual(record['consumer']['schema_version'],f'{v}.0')
    def test_records_reject_corruption(self):
        expected=a.expected_result(3,'25')['boundaries']
        bad=copy.deepcopy(expected);bad[0]['consumer']['namespace']='wrong'
        with self.assertRaises(AssertionError): a.check_records(bad,expected)
        bad=copy.deepcopy(expected);bad[0]['T']=True
        with self.assertRaises(AssertionError): a.check_records(bad,expected)
        bad=copy.deepcopy(expected);bad[0]['w']['H2O']+=2e-8
        with self.assertRaises(AssertionError): a.check_records(bad,expected)
        a.check_records(list(reversed(expected)),expected)
        with self.assertRaises(AssertionError): a.check_records(list(reversed(expected)),expected,ordered=True)
    def test_extra_descriptive_metadata(self):
        expected=a.expected_result(1,'5')['boundaries']
        actual=copy.deepcopy(expected)
        actual[0]['description']='extra metadata'
        actual[0]['producer']['provenance']['T']['description']='extra metadata'
        a.check_records(actual,expected)
        a.check_rejected({'status':'rejected','error':{'code':'INVALID_VALUE','detail':'bad','description':'extra'},'description':'extra'},'INVALID_VALUE')
        actual[0]['w']['unexpected_species']=0.0
        with self.assertRaises(AssertionError): a.check_records(actual,expected)
    def test_rejection_no_partial(self):
        r={'status':'rejected','error':{'code':'INVALID_VALUE','detail':'bad'}}
        a.check_rejected(r,'INVALID_VALUE')
        r['boundaries']=[]
        with self.assertRaises(AssertionError): a.check_rejected(r,'INVALID_VALUE')
    def test_reports_failures_without_abort(self):
        def broken(*args): raise RuntimeError('sentinel')
        m=types.SimpleNamespace(integrate=broken,normalize_quantity=broken)
        for stage,count in enumerate((40,48,56)):
            r=a.evaluate(m,stage)
            self.assertEqual(r['case_count'],count)
            self.assertEqual(r['passed'],0)
            self.assertTrue(all(row['failure']['detail']=='sentinel' for row in r['records']))

if __name__=='__main__':unittest.main()

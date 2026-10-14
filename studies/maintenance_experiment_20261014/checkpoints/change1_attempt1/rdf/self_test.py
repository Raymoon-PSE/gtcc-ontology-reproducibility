import copy
import unittest
from adapter import adapt
from stores import RDFStore


def facts(units=('K', 'kPa', 'kg/s', 'kJ/kg'), names=('temperature', 'pressure', 'flow', 'enthalpy')):
    return [('stream', 'version', '2')] + [triple for f, u, n in zip(('T','P','m_dot','h'), units, names) for triple in [('stream', 'field_'+f, n), ('stream', 'unit_'+f, u)]]


def record():
    return {'version':'2', 'values':dict(zip(('temperature','pressure','flow','enthalpy'), (300, 2000, 2, -3))), 'units':dict(zip(('temperature','pressure','flow','enthalpy'), ('K','kPa','kg/s','kJ/kg'))), 'composition':{'a':0.2, 'b':0.8}}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.config = RDFStore(facts()).dumps()

    def test_conversion_and_copy(self):
        r = record(); before = copy.deepcopy(r)
        got = adapt(r, self.config)
        self.assertAlmostEqual(got['T'],26.85)
        self.assertEqual({k:got[k] for k in ('P','m_dot','h','w')}, {'P':2,'m_dot':7200,'h':-3000,'w':r['composition']})
        self.assertEqual(r,before)
        self.assertIsNot(got['w'],r['composition'])
        self.assertEqual(set(got),{'T','P','m_dot','h','w'})

    def test_bad_records(self):
        changes = [lambda r:r.update(extra=0), lambda r:r.pop('units'), lambda r:r.update(version=2), lambda r:r.update(version='1'), lambda r:r['values'].update(extra=1), lambda r:r['units'].update(pressure='MPa'), lambda r:r.update(composition={}), lambda r:r.update(composition={'a':0.9}), lambda r:r.update(composition={'a':True}), lambda r:r.update(composition={'a':float('nan')}), lambda r:r.update(composition={'a':-0.1,'b':1.1})]
        for change in changes:
            r=record(); change(r)
            with self.subTest(r=r), self.assertRaises(ValueError): adapt(r,self.config)
        for field, values in {'temperature':[0,-1,True,float('nan'),float('inf'),'300'], 'pressure':[0,-1], 'flow':[-1,1e308], 'enthalpy':[float('inf'),1e308]}.items():
            for value in values:
                r=record(); r['values'][field]=value
                with self.subTest(field=field,value=value), self.assertRaises(ValueError): adapt(r,self.config)

    def test_bad_schema(self):
        cases = [facts()[:-1], facts()+[('stream','unit_T','degC')], facts()+[('stream','field_X','x')], facts()+[('stream','field_P','temperature')], [('stream','version','3')]+facts()[1:]]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError): adapt(record(),RDFStore(case).dumps())
        with self.assertRaises(ValueError): adapt(record(),'not turtle')

    def test_fresh_runtime_schema(self):
        adapt(record(),self.config)
        names=('a','b','c','d'); units=('degC','Pa','kg/hr','J/kg')
        r={'version':'2','values':dict(zip(names,(30,1e6,3600,123))), 'units':dict(zip(names,units)), 'composition':{'N2':1}}
        self.assertEqual(adapt(r,RDFStore(facts(units,names)).dumps()),dict(T=30,P=1,m_dot=3600,h=123,w={'N2':1}))
        with self.assertRaises(ValueError): adapt(r,self.config)

if __name__ == '__main__': unittest.main()

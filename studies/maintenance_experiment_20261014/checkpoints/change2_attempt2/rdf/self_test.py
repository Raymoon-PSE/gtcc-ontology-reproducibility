import copy
import unittest
from adapter import adapt, PublicationSession, BOUNDARIES, CONSUMERS
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

    def test_empty_wire_alias(self):
        names=('', 'pressure', 'flow', 'enthalpy')
        r=record()
        r['values']['']=r['values'].pop('temperature')
        r['units']['']=r['units'].pop('temperature')
        result=adapt(r,RDFStore(facts(names=names)).dumps())
        self.assertAlmostEqual(result['T'],26.85)
        duplicate_names=('', '', 'flow', 'enthalpy')
        with self.assertRaises(ValueError):
            adapt(r,RDFStore(facts(names=duplicate_names)).dumps())

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

def publication_config(extra=()):
    units = {'dashboard':('degC','MPa','kg/hr','J/kg'), 'report':('K','Pa','kg/s','kJ/kg'), 'diagnostics':('K','kPa','kg/hr','J/kg')}
    return RDFStore(facts() + [(c,'unit_'+f,u) for c in CONSUMERS for f,u in zip(('T','P','m_dot','h'),units[c])] + list(extra)).dumps()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.session=PublicationSession()
        self.records={b:record() for b in BOUNDARIES}
        self.config=publication_config()

    def test_all_consumers_and_defensive_copies(self):
        original=copy.deepcopy(self.records)
        self.session.begin('one')
        self.session.publish('one',self.records,self.config)
        snap=self.session.snapshot()
        self.assertEqual(set(snap),{'revision','consumers'})
        self.assertEqual(set(snap['consumers']),set(CONSUMERS))
        for consumer in snap['consumers'].values():
            self.assertEqual(set(consumer['streams']),set(BOUNDARIES))
        stream=snap['consumers']['report']['streams']['gt_exhaust']
        self.assertEqual(stream,dict(T=300,P=2000000,m_dot=2,h=-3,w={'a':.2,'b':.8}))
        self.assertEqual(self.records,original)
        stream['w']['a']=100
        self.records['gt_exhaust']['composition']['a']=200
        hist=self.session.history(); hist['one']['revision']='changed'
        fresh=self.session.snapshot()
        self.assertEqual(fresh['consumers']['report']['streams']['gt_exhaust']['w']['a'],.2)
        self.assertEqual(self.session.history()['one']['revision'],'one')

    def test_revision_lifecycle_and_retry(self):
        with self.assertRaises(ValueError): self.session.snapshot()
        for revision in ('',None,1):
            with self.assertRaises(ValueError): self.session.begin(revision)
        self.session.begin('one'); self.session.publish('one',self.records,self.config)
        accepted=self.session.snapshot()
        with self.assertRaises(ValueError): self.session.begin('one')
        with self.assertRaises(ValueError): self.session.publish('one',self.records,self.config)
        self.assertEqual(self.session.snapshot(),accepted)
        self.session.begin('two')
        with self.assertRaises(ValueError): self.session.snapshot()
        with self.assertRaises(ValueError): self.session.publish('one',self.records,self.config)
        bad=copy.deepcopy(self.records); bad['condensate']['values']['pressure']=-1
        with self.assertRaises(ValueError): self.session.publish('two',bad,self.config)
        with self.assertRaises(ValueError): self.session.snapshot()
        self.assertEqual(self.session.history(),{'one':accepted})
        self.session.publish('two',self.records,self.config)
        self.assertEqual(set(self.session.history()),{'one','two'})
        self.session.begin('three'); self.session.begin('four')
        with self.assertRaises(ValueError): self.session.publish('three',self.records,self.config)
        with self.assertRaises(ValueError): self.session.begin('three')
        self.session.publish('four',self.records,self.config)

    def test_consumer_failures_atomic_and_fresh(self):
        self.session.begin('x')
        bad_configs=[RDFStore(facts()).dumps(),publication_config([('diagnostics','unit_P','Pa')]),publication_config([('report','unit_h','K')])]
        for conf in bad_configs:
            with self.assertRaises(ValueError): self.session.publish('x',self.records,conf)
            with self.assertRaises(ValueError): self.session.snapshot()
            self.assertEqual(self.session.history(),{})
        overflow=copy.deepcopy(self.records)
        for r in overflow.values():
            r['values']['pressure']=1e308
        with self.assertRaises(ValueError): self.session.publish('x',overflow,self.config)
        bad=copy.deepcopy(self.records); bad.pop('condensate')
        with self.assertRaises(ValueError): self.session.publish('x',bad,self.config)
        self.session.publish('x',self.records,self.config)
        self.session.begin('y')
        changed=self.config.replace('"Pa"','"MPa"')
        self.session.publish('y',self.records,changed)
        self.assertEqual(self.session.snapshot()['consumers']['report']['streams']['gt_exhaust']['P'],2)


if __name__ == '__main__': unittest.main()

"""Whole-process simulated data integration, independent of agent self-tests."""
from pathlib import Path
import json,copy,math

CONSUMERS={'dashboard':{'T':'degC','P':'kPa','m_dot':'kg/s','h':'kJ/kg'},
           'report':{'T':'degC','P':'MPa','m_dot':'kg/hr','h':'J/kg'},
           'diagnostics':{'T':'K','P':'Pa','m_dot':'kg/s','h':'J/kg'}}

def checks(module,cls):
 data=json.loads((Path(__file__).resolve().parents[1]/'fixtures/whole_cycle.json').read_text())
 ff=[('stream','version','2')]
 for key,unit in [('T','K'),('P','Pa'),('m_dot','kg/s'),('h','kJ/kg')]:ff.extend([('stream','field_'+key,'v_'+key),('stream','unit_'+key,unit)])
 for c,us in CONSUMERS.items():ff.extend((c,'unit_'+k,u) for k,u in us.items())
 config=cls(ff).dumps()
 def records(ambient):
  return {name:{'version':'2','values':{'v_T':s['T']+273.15,'v_P':s['P']*1e6,'v_m_dot':s['m_dot']/3600.,'v_h':s['h']/1000.},
          'units':{'v_T':'K','v_P':'Pa','v_m_dot':'kg/s','v_h':'kJ/kg'},'composition':copy.deepcopy(s['w'])} for name,s in data[str(ambient)]['streams'].items()}
 def compare(snapshot,ambient):
  for c in CONSUMERS:
   assert snapshot['consumers'][c]['units']==CONSUMERS[c]
   out=snapshot['consumers'][c]['streams'];source=data[str(ambient)]['streams'];assert out.keys()==source.keys()
   for boundary,s in source.items():
    expected={k:s[k] for k in ['T','P','m_dot','h']}
    if c=='dashboard':expected.update(P=s['P']*1000,m_dot=s['m_dot']/3600.,h=s['h']/1000.)
    if c=='diagnostics':expected.update(T=s['T']+273.15,P=s['P']*1e6,m_dot=s['m_dot']/3600.)
    for k,v in expected.items():assert math.isclose(out[boundary][k],v,rel_tol=1e-12,abs_tol=1e-8),(c,boundary,k)
    assert out[boundary]['w']==s['w']
 def case(ambient):
  session=module.PublicationSession();session.begin('fresh');session.publish('fresh',records(ambient),config);compare(session.snapshot(),ambient)
 def transition():
  session=module.PublicationSession();session.begin('A');a=records(5);session.publish('A',a,config)
  session.begin('B');session.publish('B',records(25),config);compare(session.snapshot(),25)
  try:session.publish('A',a,config)
  except ValueError:pass
  else:raise AssertionError('Old completion overwrote B')
  compare(session.snapshot(),25);compare(session.history()['A'],5)
  assert abs(data['5']['W_net_kW']-data['25']['W_net_kW'])>1
 rows=[]
 for name,fn in [('F01_real_5C',lambda:case(5)),('F02_real_25C',lambda:case(25)),('F03_real_A_to_B',transition)]:
  try:fn();rows.append({'id':name,'passed':True,'error':None})
  except Exception as e:rows.append({'id':name,'passed':False,'error':type(e).__name__+': '+str(e)})
 return rows

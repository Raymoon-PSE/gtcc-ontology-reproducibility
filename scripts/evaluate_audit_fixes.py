"""Regression and conventional-query comparison, introduced after the audit.

Not a holdout study. Run after evaluate_revision.py and reproduce_integrity.py.
"""
from pathlib import Path
import sys, json, math, warnings, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from eklm.kas.legacy_bridge.graph import load_graph, PM
from eklm.kas.legacy_bridge.integrity import IntegrityError
from eklm.kas.legacy_bridge.bayesian import (
    diagnose_bayesian, threshold_exceeded, THRESHOLD_ABS_TOL,
    THRESHOLD_REL_TOL, FAULT_LIBRARY)
from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP
from eklm.vdt.gui_adapter import run_gtcc
from conventional_control import query_records
from rdflib import Graph
warnings.filterwarnings('ignore')
OUT=ROOT/'outputs/audit_fixes';OUT.mkdir(parents=True,exist_ok=True)
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False))
policy={'status':'Each of six contracted devices requires exactly one FULL/PARTIAL/NONE declaration. Missing does not mean disabled.',
        'threshold':'Strict directional exceedance outside math.isclose equality tolerance; equality is a non-match.',
        'absolute_tolerance':THRESHOLD_ABS_TOL,'relative_tolerance':THRESHOLD_REL_TOL,
        'scope':'Numerical roundoff handling, not measurement uncertainty or calibrated alarm thresholds.',
        'design':'Audit-driven development regressions, not blinded or independently sourced holdout cases.',
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
save('protocol.json',policy)
boundary=[]
for fault in FAULT_LIBRARY:
    for channel,symptom in fault.symptoms.items():
        t=symptom['threshold']; direction=symptom['direction']
        tolerance=max(THRESHOLD_ABS_TOL, THRESHOLD_REL_TOL*abs(t))
        for label,offset,expected in [('below',-100*tolerance,False),('near_below',-.01*tolerance,False),('equal',0,False),('near_above',.01*tolerance,False),('above',100*tolerance,True)]:
            deviation=(t+offset)*(-1 if direction=='down' else 1)
            actual=threshold_exceeded(deviation,t,direction)
            assert actual==expected,(fault.id,channel,label)
            boundary.append({'fault':fault.id,'channel':channel,'threshold':t,'direction':direction,'case':label,'deviation':deviation,'matched':actual,'expected':expected})
save('threshold_checks.json',boundary)
_,r=run_gtcc({'eta_comp':.825})
scores=[]
for eta in [.825-1e-12,.825,.825+1e-12]:
    score=next(x.posterior for x in diagnose_bayesian(r,params={'eta_comp':eta,'eta_turb':.876,'mech_comp_surge_margin_pct':15}) if x.fault_id=='F-01')
    scores.append({'eta':eta,'F01':score})
assert max(x['F01'] for x in scores)-min(x['F01'] for x in scores)<1e-12
save('fixed_process_scores.json',scores)
lifecycle=[]
for device in ['COMP-001','COMB-001','EXP-001','HPSH-001','RH-001','HPTURB']:
    for mode in ['missing_status','missing_device']:
        g=load_graph()
        run_gtcc({'ontology_runtime':True,'ontology_graph':g})
        g.remove((PM[device],PM.mech_hasDataStatus,None) if mode=='missing_status' else (PM[device],None,None))
        try:
            run_gtcc({'ontology_runtime':True,'ontology_graph':g})
        except IntegrityError as exc:
            assert any(f.code=='data_status' and f.subject==str(PM[device]) for f in exc.findings)
            assert not any(list(g.triples((None,p,None))) for p in set(_PROP_MAP.values()))
            assert not list(g.triples((None,PM.runtime_posterior,None)))
            assert not list(g.triples((None,PM.runtime_value,None)))
            lifecycle.append({'device':device,'mode':mode,'rejected':True,'evidence_cleared':True})
        else:
            raise AssertionError((device,mode))
save('omission_lifecycle.json',lifecycle)
# Preserve all relation values: JSON joins receive the same populated snapshot.
# Export/class-resolution effort is excluded; this isolates retrieval capability.
g=Graph().parse(ROOT/'outputs/revision/query_graph.nt',format='nt')
rows={}
for s,p,o in g:
    rows.setdefault(str(s),{}).setdefault(str(p),[]).append(str(o))
for props in rows.values():
    for values in props.values():values.sort()
save('query_input.json',rows)
actual=query_records(rows)
expected=json.loads((ROOT/'outputs/revision/queries.json').read_text())
def canonical(items):return sorted(json.dumps(x,sort_keys=True) for x in items)
for key in expected:
    assert canonical(actual[key])==canonical(expected[key]),key
save('query_results.json',actual)
summary={'threshold_checks':len(boundary),'threshold_checks_passed':True,
         'fixed_process_F01':scores,'omission_lifecycle_checks':len(lifecycle),
         'omission_lifecycle_passed':True,'conventional_query_rows':{k:len(v) for k,v in actual.items()},
         'all_query_bindings_equal':True,
         'query_comparison_limit':'Identical graph-exported relation snapshot. Conventional joins use no RDF library; export, initial integration effort, human time and broad schema portability are not measured.'}
save('summary.json',summary);print(json.dumps(summary,indent=2))

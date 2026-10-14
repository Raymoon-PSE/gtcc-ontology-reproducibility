#!/usr/bin/env python3
"""Matched hierarchy ablation: capability control, not a weak main baseline."""
import sys,json
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from benchmark.stores import STORES
from benchmark.scenarios import scenario_facts

def main():
    facts=scenario_facts({'task':'S1','variant':'compatible'})
    rows=[]
    for backend,cls in STORES.items():
        for mode,expected in [('transitive',True),('asserted_only',False),('prematerialized_assertions',True)]:
            source=facts+([('EXP-001','type','GT_Turbine')] if mode=='prematerialized_assertions' else [])
            store=cls.loads(cls(source).dumps())
            if mode!='transitive':store.ancestors=lambda c:{c}
            observed=store.instance_of('EXP-001','GT_Turbine')
            assert observed==expected
            rows.append(dict(backend=backend,mode=mode,expected=expected,observed=observed))
    path=ROOT/'results/semantic_control.json'
    path.write_text(json.dumps({'rows':rows,'interpretation':'Both representations require ancestry traversal or explicitly materialized type information. This isolates hierarchy capability, not RDF superiority.'},indent=2))
    print('Matched semantic controls: 6/6 expected outcomes')
if __name__=='__main__':main()

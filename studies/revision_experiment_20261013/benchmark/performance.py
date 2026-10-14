"""Matched metadata-only performance. Not full plant scalability or human effort."""
import gc
import json
import statistics
import time
import tracemalloc
from pathlib import Path
from .stores import STORES,RELATIONS
from .contracts import base_facts,BOUNDARIES,ContractError


def scaled_facts(n):
    facts=base_facts()
    facts=[f for f in facts if f[:2]!=('EXP-001','type')]
    facts += [('EXP-001','type','AdvancedExpander'),('AdvancedExpander','subclass','IntermediateExpander'),
              ('IntermediateExpander','subclass','GT_Turbine')]
    return [(f'{i}/{s}',p,f'{i}/{o}' if p in RELATIONS else o) for i in range(n) for s,p,o in facts]


def workload(store,n):
    count=0
    for i in range(n):
        prefix=f'{i}/'
        if not store.instance_of(prefix+'EXP-001',prefix+'GT_Turbine'):raise ContractError('missing inherited type')
        if store.one(prefix+'EXP-001','binding')!=prefix+'GT_Turbine':raise ContractError('binding')
        for name,(source,target) in BOUNDARIES.items():
            subject=prefix+name
            if store.one(subject,'source')!=prefix+source or store.one(subject,'target')!=prefix+target:raise ContractError('endpoint')
            if store.one(subject,'version')!='1':raise ContractError('version')
            for field,unit in [('T','degC'),('P','MPa'),('m_dot','kg/hr'),('h','J/kg')]:
                if store.one(subject,'unit_'+field)!=unit:raise ContractError('unit')
            count+=1
    return count


def run_performance(dest,scales=(1,10,100,1000),cold_reps=6,warm_reps=20):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    if (dest/'summary.json').exists():raise RuntimeError('Preserve completed performance results; choose another directory')
    spec={'scales':list(scales),'cold_reps':cold_reps,'warm_reps':warm_reps,
          'cold':'parse native in-memory serialized artifact and construct queryable representation; no disk I/O or physics',
          'warm':'transitive expander subtype lookup plus binding and seven boundary endpoint/version/unit checks per replicated configuration',
          'memory':'tracemalloc peak Python allocations during cold parse; excludes preexisting payload, interpreter, native allocations and physics',
          'order':'balanced RDF/JSON alternation; GC enabled; serial process; two untimed warmups',
          'scope':'synthetically replicated metadata only; repetitions are timing samples, not independent engineering tasks'}
    (dest/'specification.json').write_text(json.dumps(spec,indent=2))
    rows=[];summaries=[]
    for scale in scales:
        facts=scaled_facts(scale);payload={b:c(facts).dumps() for b,c in STORES.items()}
        prepared={b:STORES[b].loads(p) for b,p in payload.items()}
        for b,s in prepared.items():
            assert workload(s,scale)==7*scale
            workload(s,scale)
            (dest/f'config_{scale}.{ "ttl" if b=="rdf" else "json"}').write_text(payload[b])
        for phase,reps in [('cold',cold_reps),('warm',warm_reps)]:
            for rep in range(reps):
                for b in (['rdf','json'] if rep%2==0 else ['json','rdf']):
                    value=None  # release previous sample outside measured interval
                    gc.collect()
                    start=time.perf_counter_ns()
                    if phase=='cold':value=STORES[b].loads(payload[b])
                    else:value=workload(prepared[b],scale)
                    elapsed=time.perf_counter_ns()-start
                    rows.append(dict(scale=scale,facts=len(facts),backend=b,phase=phase,repeat=rep,ns=elapsed))
                    if phase=='cold':assert workload(value,scale)==7*scale
        for b in ['rdf','json']:
            parsed=None  # release prior allocation sample before tracing
            gc.collect();tracemalloc.start()
            parsed=STORES[b].loads(payload[b]);current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            assert workload(parsed,scale)==7*scale
            summary={'scale':scale,'facts':len(facts),'backend':b,'serialized_bytes':len(payload[b].encode()),
                     'peak_python_allocated_bytes':peak}
            for phase in ['cold','warm']:
                values=[r['ns']/1e6 for r in rows if r['scale']==scale and r['backend']==b and r['phase']==phase]
                summary[phase+'_median_ms']=statistics.median(values)
                summary[phase+'_min_ms']=min(values);summary[phase+'_max_ms']=max(values)
            summaries.append(summary)
        print('Metadata performance scale',scale,'complete',flush=True)
        (dest/'raw_timings.json').write_text(json.dumps(rows,indent=2))
        (dest/'partial_summary.json').write_text(json.dumps(summaries,indent=2))
    (dest/'summary.json').write_text(json.dumps(summaries,indent=2))
    return summaries

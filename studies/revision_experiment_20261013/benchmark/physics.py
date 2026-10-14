"""Isolated linked-cycle boundary harness; never modifies frozen source files.

Callbacks run on actual solver inputs, including both tear streams on each
iteration. They must return a canonical Stream (C, MPa, kg/hr, J/kg). This is
an experimental adapter layer, not a claim of pre-existing RDF scheduling.
Use only in an isolated, single-threaded benchmark interpreter.
"""
from copy import deepcopy
from dataclasses import asdict
import math
from threading import RLock

BOUNDARIES = ('gt_exhaust', 'hp_steam', 'hot_reheat', 'lp_steam',
              'st_exhaust', 'cold_reheat', 'condensate')
_LOCK = RLock()
_ACTIVE = False


def run_physics(ambient=15, boundary_transform=None):
    """Return original GUI output and raw result with OperatingPoint attached.

    The callback receives independent copies. Exceptions propagate; bindings
    are restored even on callback or numerical failure. Concurrent use of this
    harness is serialized, and recursive invocation is explicitly rejected.
    This does not make unrelated EKLM calls in other threads safe.
    """
    from eklm.vdt import gui_adapter
    from eklm.vdt.analysis import gtcc_loop
    from eklm.vdt.data.streams import Stream
    global _ACTIVE
    with _LOCK:
        if _ACTIVE:
            raise RuntimeError('Recursive physics harness invocation is unsupported')
        _ACTIVE = True
        originals = {k: getattr(gtcc_loop, k) for k in
                     ('hrsg_solve', 'st_solve', 'condenser_solve')}
        calls = {name: 0 for name in BOUNDARIES}

        def transform(name, stream):
            calls[name] += 1
            value = deepcopy(stream)
            if boundary_transform is not None:
                value = boundary_transform(name, value)
            if not isinstance(value, Stream):
                raise TypeError(f'{name}: transform must return canonical Stream')
            for key in ('T', 'P', 'm_dot'):
                if not math.isfinite(getattr(value, key)):
                    raise ValueError(f'{name}: nonfinite {key}')
            return value

        def hrsg(gas, cold, condensate, params):
            return originals['hrsg_solve'](
                transform('gt_exhaust', gas), transform('cold_reheat', cold),
                transform('condensate', condensate), params)

        def steam(hp, hot, lp, params):
            return originals['st_solve'](transform('hp_steam', hp),
                transform('hot_reheat', hot), transform('lp_steam', lp), params)

        def condenser(exhaust, params):
            return originals['condenser_solve'](transform('st_exhaust', exhaust), params)

        try:
            gtcc_loop.hrsg_solve = hrsg
            gtcc_loop.st_solve = steam
            gtcc_loop.condenser_solve = condenser
            output, result = gui_adapter.run_gtcc({
                'T_amb': ambient, 'hrsg_thermal_mode': 'linked',
                'ontology_runtime': False,
            })
            output['benchmark_boundary_calls'] = calls
            return output, result
        finally:
            for name, original in originals.items():
                setattr(gtcc_loop, name, original)
            _ACTIVE = False


def summarize(output, result):
    """Deterministic JSON-native physical evidence; no plots/session artifacts."""
    streams = dict(gt_exhaust=result.s7, hp_steam=result.m2.s_is01,
                   hot_reheat=result.m2.s_is03, lp_steam=result.m2.s_is05,
                   st_exhaust=result.m3.s28, cold_reheat=result.is02,
                   condensate=result.is06)
    return {
        'converged': bool(result.converged),
        'iterations': int(result.iterations),
        'residual': float(result.residual),
        'W_GT_kW': float(result.W_GT), 'W_ST_kW': float(result.m3.W_ST),
        'W_net_kW': float(result.W_net), 'Q_fuel_kW': float(result.Q_fuel),
        'eta_net': float(result.eta_net), 'T_stack_C': float(result.m2.T_stack),
        'Q_condenser_kW': float(result.m4.Q_cond),
        'streams': {name: asdict(stream) for name, stream in streams.items()},
        'operating_point': asdict(result.operating_point),
        'cycle_water_audit': deepcopy(output['cycle_water_audit']),
        'validation_scope': deepcopy(output['validation_scope']),
        'hrsg_local_balances_passed': bool(output['hrsg_thermal_audit']['local_balances_passed']),
        'hrsg_endpoint_screen_passed': bool(output['hrsg_thermal_audit']['endpoint_screen_passed']),
        'boundary_calls': dict(output.get('benchmark_boundary_calls', {})),
    }

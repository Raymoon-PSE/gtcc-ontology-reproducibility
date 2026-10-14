"""Independent local balances and necessary endpoint feasibility checks.

Positive endpoint approaches are necessary, not sufficient: internal pinch,
finite area, pressure losses, and a validated equipment layout remain outside
this screen. No temperatures or duties are fitted to make the screen pass.
"""
import math
from eklm.vdt.data.species import h_mix


def heat_exchanger_audit(name, gas_in, gas_out, water_in, water_out, duty):
    q_gas = gas_in.m_dot*(h_mix(gas_in.T+273.15,gas_in.w)-h_mix(gas_out.T+273.15,gas_out.w))/3.6e6
    q_water = (water_out.m_dot*water_out.h-water_in.m_dot*water_in.h)/3.6e6
    hot = gas_in.T-water_out.T
    cold = gas_out.T-water_in.T
    finite = all(math.isfinite(x) for x in (q_gas,q_water,duty,hot,cold,
        gas_in.m_dot,gas_out.m_dot,water_in.m_dot,water_out.m_dot))
    tolerance=max(.01,1e-7*abs(duty)) if finite else .01
    balanced=bool(finite and max(abs(q_gas-duty),abs(q_water-duty))<=tolerance
        and abs(gas_in.m_dot-gas_out.m_dot)<1e-6
        and abs(water_in.m_dot-water_out.m_dot)<1e-6)
    endpoint_ok=bool(finite and duty>=0 and q_gas>=0 and q_water>=0
        and hot>=0 and cold>=0 and (duty<=1e-8 or min(hot,cold)>0))
    return dict(unit=name,Q_gas_kW=q_gas,Q_water_kW=q_water,Q_reported_kW=duty,
        energy_residual_kW=q_gas-q_water,
        gas_duty_residual_kW=q_gas-duty,water_duty_residual_kW=q_water-duty,
        hot_end_approach_C=hot,cold_end_approach_C=cold,
        local_balance_passed=balanced,endpoint_screen_passed=endpoint_ok)


def summarize_audits(rows):
    return dict(scope="local_balances_and_counterflow_endpoint_screen",
        full_physical_validation=False,
        local_balances_passed=all(r['local_balance_passed'] for r in rows),
        endpoint_screen_passed=all(r['endpoint_screen_passed'] for r in rows),
        units=rows)

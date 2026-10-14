"""Energy/endpoint-limited steam heating; not a calibrated UA model."""
import math
from eklm.vdt.data.properties import h_water, T_from_PH_water
from eklm.vdt.data.species import h_mix


def limited_outlet_temperature(gas, steam_in, pressure, requested_T, approach):
    if not all(math.isfinite(v) for v in (gas.T,gas.m_dot,steam_in.T,steam_in.h,
        steam_in.m_dot,pressure,requested_T,approach)):
        raise ValueError("Heat-exchanger inputs must be finite")
    if min(gas.m_dot,steam_in.m_dot,pressure,approach)<=0:
        raise ValueError("Heat-exchanger flows, pressure and approach must be positive")
    hot_limit_T=gas.T-approach
    if hot_limit_T<=steam_in.T:
        raise ValueError("Insufficient hot-gas temperature for steam heating")
    h_target=h_water(min(requested_T,hot_limit_T),pressure)
    requested_q=steam_in.m_dot*(h_target-steam_in.h)/3.6e6
    gas_capacity=gas.m_dot*(h_mix(gas.T+273.15,gas.w)
        -h_mix(steam_in.T+approach+273.15,gas.w))/3.6e6
    q=min(requested_q,gas_capacity)
    if q<=0:
        raise ValueError("Steam heating target must require positive feasible duty")
    return T_from_PH_water(pressure,steam_in.h+q*3.6e6/steam_in.m_dot)

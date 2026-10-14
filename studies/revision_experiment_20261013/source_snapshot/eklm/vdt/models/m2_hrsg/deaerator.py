"""Unit 2-14: Deaerator.

Receives preheated condensate S^(23) from LP Eco and distributes to
HP/IP/LP BFP circuits. Operates at LP drum pressure (P_LP).
Feedwater exits at T_sat(P_LP) (saturated liquid, degassed).

Outlet-state assumption only. No extraction steam, vent, or heater model.
The separate audit reports the external energy needed to sustain this state.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import T_sat_water, h_sat_liq_water



@dataclass
class DeaeratorOutput:
    """Unit 2-14 outputs."""

    T_da: float         # Deaerator operating temperature, C
    P_da: float         # Deaerator operating pressure, MPa
    h_da: float         # Feedwater enthalpy at DA outlet, J/kg


def deaerator(P_LP: float = 0.655) -> DeaeratorOutput:
    """Calculate deaerator conditions.

    Deaerator operates at LP drum pressure. Feedwater exits as
    saturated liquid at T_sat(P_LP).

    Args:
        P_LP: Deaerator operating pressure, MPa. Default 0.655.

    Returns:
        DeaeratorOutput with DA temperature and enthalpy.
    """
    T_da = T_sat_water(P_LP)
    h_da = h_sat_liq_water(P_LP)

    return DeaeratorOutput(T_da=T_da, P_da=P_LP, h_da=h_da)


def mix_deaerator(water_in, steam_in, pressure):
    """Adiabatic open-heater state from inlet mass and energy, with no reset.

    Saturated-liquid operation is a feasibility constraint, not extra heat.
    Upstream preheat/extraction must satisfy it; otherwise reject the case.
    """
    import math
    from eklm.vdt.data.properties import T_from_PH_water
    values=(water_in.m_dot,steam_in.m_dot,water_in.h,steam_in.h,pressure)
    if any(x is None or not math.isfinite(x) for x in values) or min(values[:2])<0 or pressure<=0:
        raise ValueError('Invalid DA inlet boundaries')
    mass=water_in.m_dot+steam_in.m_dot
    if mass<=0:raise ValueError('DA requires positive inlet mass')
    h=(water_in.m_dot*water_in.h+steam_in.m_dot*steam_in.h)/mass
    if abs(h-h_sat_liq_water(pressure))>1.:
        raise ValueError('DA inlet energy does not support saturated liquid outlet')
    return DeaeratorOutput(T_from_PH_water(pressure,h),pressure,h)

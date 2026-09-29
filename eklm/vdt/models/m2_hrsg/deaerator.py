"""Unit 2-14: Deaerator.

Receives preheated condensate S^(23) from LP Eco and distributes to
HP/IP/LP BFP circuits. Operates at LP drum pressure (P_LP).
Feedwater exits at T_sat(P_LP) (saturated liquid, degassed).

Phase 1: simple mass/energy balance. No extraction steam modeling
(deaerator heating assumed via LP system integration).
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import T_sat_water, h_sat_liq_water
from eklm.vdt.data.streams import Stream

from CoolProp.CoolProp import PropsSI


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

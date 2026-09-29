"""Unit 3-1: HP Turbine.

Reference: ST_Module_Math_Model v1.0 Unit 3-1.

Expands HP main steam (IS-01) through the HP turbine. Isentropic efficiency
model with CoolProp Water. Phase 1: bleed extracted at exit conditions
(DR-M3-01).
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import (
    h_from_PS_water,
    T_from_PH_water,
    s_from_PH_water,
)
from eklm.vdt.data.streams import Stream


@dataclass
class HPTurbineOutput:
    """Unit 3-1 outputs."""

    s25: Stream         # HP turbine exit -> Unit 3-2 CRH
    W_hpt: float        # HP turbine mechanical power, kW
    eta_hpt: float      # Isentropic efficiency used


def hp_turbine(
    s_is01: Stream,
    P_25: float,
    eta_hpt: float,
    m_dot_bleed: float = 16_429.0,
) -> HPTurbineOutput:
    """Calculate HP Turbine expansion.

    Args:
        s_is01: HP Main Steam from M2 -- IS-01.
        P_25: HP turbine exit pressure, MPa.
            Derived from IS-02 tear stream: P^(25) = P^(IS-02) + dP_crh.
        eta_hpt: HP turbine isentropic efficiency.
        m_dot_bleed: HP bleed mass flow, kg/hr. Default 16,429 (NETL).

    Returns:
        HPTurbineOutput with exit stream, power, and efficiency.
    """
    # Isentropic reference
    s_ref = s_is01.s
    h_ref = h_from_PS_water(P_25, s_ref)

    # Actual exit enthalpy
    h25 = s_is01.h - eta_hpt * (s_is01.h - h_ref)

    # Exit state (CoolProp)
    T25 = T_from_PH_water(P_25, h25)
    s25 = s_from_PH_water(P_25, h25)

    # Mass balance (bleed extracted at exit)
    m_dot_25 = s_is01.m_dot - m_dot_bleed

    # Power: full inlet flow expands, bleed extracted at exit (DR-M3-01)
    # m_dot [kg/hr] * dh [J/kg] / 3.6e6 = kW
    W_hpt = s_is01.m_dot * (s_is01.h - h25) / 3.6e6

    s25_stream = Stream(
        T=T25, P=P_25, m_dot=m_dot_25,
        w={"H2O": 1.0}, h=h25, s=s25,
    )

    return HPTurbineOutput(s25=s25_stream, W_hpt=W_hpt, eta_hpt=eta_hpt)

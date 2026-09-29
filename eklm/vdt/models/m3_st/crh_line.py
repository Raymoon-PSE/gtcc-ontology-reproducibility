"""Unit 3-2: Cold Reheat Line.

Reference: ST_Module_Math_Model v1.0 Unit 3-2.

Adiabatic pipe with frictional pressure drop. Isenthalpic (h conserved).
Produces IS-02 (secondary tear stream output of M3).
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import T_from_PH_water, s_from_PH_water
from eklm.vdt.data.streams import Stream


@dataclass
class CRHLineOutput:
    """Unit 3-2 outputs."""

    s_is02: Stream      # Cold Reheat -> M2 HRSG Reheater (tear stream)


def crh_line(
    s25: Stream,
    dP_crh: float = 0.0,
) -> CRHLineOutput:
    """Calculate Cold Reheat Line (adiabatic pipe).

    Args:
        s25: HP turbine exit -- S^(25).
        dP_crh: CRH pressure drop, MPa. Default 0.0 (DR-M3-03).

    Returns:
        CRHLineOutput with IS-02 stream.
    """
    P_is02 = s25.P - dP_crh
    h_is02 = s25.h  # isenthalpic
    T_is02 = T_from_PH_water(P_is02, h_is02)
    s_is02 = s_from_PH_water(P_is02, h_is02)

    s_is02_stream = Stream(
        T=T_is02, P=P_is02, m_dot=s25.m_dot,
        w={"H2O": 1.0}, h=h_is02, s=s_is02,
    )

    return CRHLineOutput(s_is02=s_is02_stream)

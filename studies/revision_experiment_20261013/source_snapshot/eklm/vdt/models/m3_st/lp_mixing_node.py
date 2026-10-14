"""Node 3-M: LP Inlet Mixing.

Reference: ST_Module_Math_Model v1.0 Node 3-M.

Mixes IP turbine exhaust S^(26) with throttled IS-05 (LP steam) to form
S^(27) (LP turbine inlet). IS-05 undergoes isenthalpic throttling from
P_LP to P^(26) before mixing (DR-M3-04).
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import T_from_PH_water, s_from_PH_water
from eklm.vdt.data.streams import Stream


@dataclass
class LPMixingNodeOutput:
    """Node 3-M outputs."""

    s27: Stream         # LP turbine inlet


def lp_mixing_node(
    s26: Stream,
    s_is05: Stream,
) -> LPMixingNodeOutput:
    """Throttle IS-05 and mix with IP exhaust.

    Args:
        s26: IP turbine exhaust -- S^(26).
        s_is05: LP steam from M2 -- IS-05.

    Returns:
        LPMixingNodeOutput with S^(27) stream.
    """
    # Step 1: IS-05 throttling (isenthalpic to cross-over pressure)
    h_is05_th = s_is05.h  # isenthalpic
    P_is05_th = s26.P     # throttle to cross-over pressure

    # Step 2: Adiabatic mixing
    m_dot_27 = s26.m_dot + s_is05.m_dot
    h27 = (s26.m_dot * s26.h + s_is05.m_dot * h_is05_th) / m_dot_27
    P27 = s26.P

    # State from (P, h)
    T27 = T_from_PH_water(P27, h27)
    s27 = s_from_PH_water(P27, h27)

    s27_stream = Stream(
        T=T27, P=P27, m_dot=m_dot_27,
        w={"H2O": 1.0}, h=h27, s=s27,
    )

    return LPMixingNodeOutput(s27=s27_stream)

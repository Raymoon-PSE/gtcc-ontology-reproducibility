"""Node 2-4M: IP Mixing Node.

Reference: HRSG_Module_Math_Model v1.6 § 2-4M.

Mixes S^(24) (Reheated Cold Reheat from Unit 2-4) with IS-04 (IP Steam
from Unit 2-5) to form IS-03 (Hot Reheat Steam → M3 IP Turbine).
Calculated after Unit 2-5 completes.
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import T_from_PH_water, s_from_PH_water
from eklm.vdt.data.streams import Stream


@dataclass
class IPMixingNodeOutput:
    """Node 2-4M outputs."""

    s_is03: Stream      # Hot Reheat Steam → M3 IP Turbine


def ip_mixing_node(
    s24: Stream,
    s_is04: Stream,
) -> IPMixingNodeOutput:
    """Adiabatic mixing of Reheated Cold Reheat and IP Steam.

    Args:
        s24: Reheated Cold Reheat — from Unit 2-4.
        s_is04: IP Superheated Steam — from Unit 2-5.

    Returns:
        IPMixingNodeOutput with IS-03 stream.
    """
    # Step 1: Mass balance
    m_dot_is03 = s24.m_dot + s_is04.m_dot

    # Step 2: Energy balance (adiabatic)
    h_is03 = (s24.m_dot * s24.h + s_is04.m_dot * s_is04.h) / m_dot_is03

    # Step 3: Pressure (Phase 1 — lower of the two)
    P_is03 = min(s24.P, s_is04.P)

    # Step 4: T and s from (P, h) via CoolProp
    T_is03 = T_from_PH_water(P_is03, h_is03)
    s_is03 = s_from_PH_water(P_is03, h_is03)

    s_is03_stream = Stream(
        T=T_is03, P=P_is03, m_dot=m_dot_is03,
        w={"H2O": 1.0}, h=h_is03, s=s_is03,
    )

    return IPMixingNodeOutput(s_is03=s_is03_stream)

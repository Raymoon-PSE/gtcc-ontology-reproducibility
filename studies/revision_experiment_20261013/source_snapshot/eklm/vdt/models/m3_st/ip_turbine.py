"""Unit 3-3: IP Turbine.

Reference: ST_Module_Math_Model v1.0 Unit 3-3.

Expands Hot Reheat steam (IS-03) through the IP turbine. Isentropic
efficiency model with CoolProp Water. Phase 1: no IP extraction.
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
class IPTurbineOutput:
    """Unit 3-3 outputs."""

    s26: Stream         # IP turbine exit -> Node 3-M
    W_ipt: float        # IP turbine mechanical power, kW


def ip_turbine(
    s_is03: Stream,
    P_26: float = 0.507,
    eta_ipt: float = 0.85,
) -> IPTurbineOutput:
    """Calculate IP Turbine expansion.

    Args:
        s_is03: Hot Reheat Steam from M2 -- IS-03.
        P_26: IP turbine exit pressure (cross-over), MPa. Default 0.507.
        eta_ipt: IP turbine isentropic efficiency. Default 0.85.

    Returns:
        IPTurbineOutput with exit stream and power.
    """
    # Isentropic reference
    s_ref = s_is03.s
    h_ref = h_from_PS_water(P_26, s_ref)

    # Actual exit enthalpy
    h26 = s_is03.h - eta_ipt * (s_is03.h - h_ref)

    # Exit state (CoolProp)
    T26 = T_from_PH_water(P_26, h26)
    s26 = s_from_PH_water(P_26, h26)

    # Mass balance (no extraction in Phase 1)
    m_dot_26 = s_is03.m_dot

    # Power
    W_ipt = s_is03.m_dot * (s_is03.h - h26) / 3.6e6

    s26_stream = Stream(
        T=T26, P=P_26, m_dot=m_dot_26,
        w={"H2O": 1.0}, h=h26, s=s26,
    )

    return IPTurbineOutput(s26=s26_stream, W_ipt=W_ipt)

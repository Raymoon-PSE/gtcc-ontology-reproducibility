"""Unit 3-4: LP Turbine.

Reference: ST_Module_Math_Model v1.0 Unit 3-4.

Expands mixed steam S^(27) to condenser pressure. LP exhaust is expected
to be in the wet steam region (x < 1). Steam quality x^(28) is computed
as a design reference (DR-M3-05).
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import (
    h_from_PS_water,
    T_from_PH_water,
    s_from_PH_water,
    x_from_PH_water,
)
from eklm.vdt.data.streams import Stream


@dataclass
class LPTurbineOutput:
    """Unit 3-4 outputs."""

    s28: Stream         # ST exhaust -> M4 Condenser
    W_lpt: float        # LP turbine mechanical power, kW
    x_28: float         # Exhaust steam quality (-1 if superheated)


def lp_turbine(
    s27: Stream,
    P_28: float = 0.00677,
    eta_lpt: float = 0.85,
) -> LPTurbineOutput:
    """Calculate LP Turbine expansion.

    Args:
        s27: LP turbine inlet from Node 3-M -- S^(27).
        P_28: LP turbine exit pressure (condenser), MPa. Default 0.00677.
        eta_lpt: LP turbine isentropic efficiency. Default 0.85.

    Returns:
        LPTurbineOutput with exit stream, power, and steam quality.
    """
    # Isentropic reference
    s_ref = s27.s
    h_ref = h_from_PS_water(P_28, s_ref)

    # Actual exit enthalpy
    h28 = s27.h - eta_lpt * (s27.h - h_ref)

    # Exit state (CoolProp -- handles two-phase)
    T28 = T_from_PH_water(P_28, h28)
    s28 = s_from_PH_water(P_28, h28)

    # Steam quality
    x_28 = x_from_PH_water(P_28, h28)

    # Mass balance (no extraction in Phase 1)
    m_dot_28 = s27.m_dot

    # Power
    W_lpt = s27.m_dot * (s27.h - h28) / 3.6e6

    s28_stream = Stream(
        T=T28, P=P_28, m_dot=m_dot_28,
        w={"H2O": 1.0}, h=h28, s=s28,
    )

    return LPTurbineOutput(s28=s28_stream, W_lpt=W_lpt, x_28=x_28)

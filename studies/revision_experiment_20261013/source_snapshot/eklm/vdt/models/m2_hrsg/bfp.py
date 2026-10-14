"""Units 2-12 / 2-13: Boiler Feed Pumps (HP BFP and IP BFP).

Raises feedwater pressure from deaerator (P_LP) to drum pressure (P_HP or P_IP).
Liquid pump model: W = m_dot * v * dP / (eta * 3.6e6) [kW].

Constant inlet specific volume approximation; outlet state comes from P/h.
"""

from dataclasses import dataclass
import math

from CoolProp.CoolProp import PropsSI

from eklm.vdt.data.properties import T_from_PH_water, s_from_PH_water
from eklm.vdt.data.streams import Stream


@dataclass
class BFPOutput:
    """BFP output."""

    s_out: Stream       # Feedwater at drum pressure
    W_bfp: float        # BFP power consumption, kW


def bfp(
    T_in: float,
    P_in: float,
    P_out: float,
    m_dot: float,
    eta_bfp: float = 0.80,
) -> BFPOutput:
    """Calculate boiler feed pump.

    Args:
        T_in: Inlet temperature (deaerator outlet), C.
        P_in: Inlet pressure (deaerator), MPa.
        P_out: Outlet pressure (drum), MPa.
        m_dot: Feedwater mass flow, kg/hr.
        eta_bfp: Pump isentropic efficiency. Default 0.80.

    Returns:
        BFPOutput with outlet stream and power.
    """
    if not all(math.isfinite(x) for x in (T_in, P_in, P_out, m_dot, eta_bfp)):
        raise ValueError("BFP inputs must be finite")
    if P_in <= 0 or P_out < P_in or m_dot < 0 or not 0 < eta_bfp <= 1:
        raise ValueError("BFP requires positive inlet pressure, nonnegative head/flow and 0 < efficiency <= 1")
    # Inlet density and specific volume
    # At deaerator outlet, T = T_sat(P_in) exactly → use Q=0 to avoid
    # CoolProp saturation boundary error
    T_sat_in = PropsSI("T", "P", P_in * 1e6, "Q", 0, "Water") - 273.15
    if T_in > T_sat_in + 1e-6:
        raise ValueError("BFP requires liquid inlet water")
    if abs(T_in - T_sat_in) <= 1e-6:
        # At saturation — use Q=0
        rho_in = PropsSI("D", "P", P_in * 1e6, "Q", 0, "Water")
        h_in = PropsSI("H", "P", P_in * 1e6, "Q", 0, "Water")
    else:
        rho_in = PropsSI("D", "T", T_in + 273.15, "P", P_in * 1e6, "Water")
        h_in = PropsSI("H", "T", T_in + 273.15, "P", P_in * 1e6, "Water")
    v_in = 1.0 / rho_in
    dP = (P_out - P_in) * 1e6  # Pa
    h_out = h_in + v_in * dP / eta_bfp

    # Preserve shaft-work enthalpy rise; recover both properties at that state.
    T_out = T_from_PH_water(P_out, h_out)
    s_out = s_from_PH_water(P_out, h_out)

    # Power: m_dot [kg/hr] * v [m3/kg] * dP [Pa] / (eta * 3.6e6) = kW
    W_bfp = m_dot * v_in * dP / (eta_bfp * 3.6e6)

    s_out_stream = Stream(
        T=T_out, P=P_out, m_dot=m_dot,
        w={"H2O": 1.0}, h=h_out, s=s_out,
    )

    return BFPOutput(s_out=s_out_stream, W_bfp=W_bfp)

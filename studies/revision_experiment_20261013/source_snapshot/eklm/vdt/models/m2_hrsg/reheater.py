"""Unit 2-4: Reheater.

Reference: HRSG_Module_Math_Model v1.6 § 2.

Reheats HP Turbine exhaust (Cold Reheat, IS-02) using GT exhaust gas heat.
Second unit in the flue gas path — receives gas from HP Superheater.
Output S^(24) goes to Node 2-4M where it mixes with IS-04.
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import h_water, s_water
from eklm.vdt.data.species import T_from_H_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream


@dataclass
class ReheaterOutput:
    """Unit 2-4 outputs."""

    s9: Stream          # Gas outlet → Unit 2-2 HP Evaporator
    s24: Stream         # Reheated Cold Reheat → Node 2-4M
    Q_dot: float        # Heat duty, kW
    dT_fg: float        # Gas-side temperature drop, °C
    TTD_hot: float      # T^(8) − T^(24), °C
    TTD_cold: float     # T^(9) − T^(IS-02), °C (pinch side)


def reheater(
    s8: Stream,
    s_is02: Stream,
    T_24: float = 565.6,
    dP_fg: float = 0.0,
    dP_st: float = 0.310,
) -> ReheaterOutput:
    """Calculate Reheater heat exchange.

    Args:
        s8: Gas from Unit 2-1 HP SH — S^(8).
        s_is02: Cold Reheat steam — IS-02 (secondary tear stream).
            First iteration: NETL {308.8 °C, 2.689 MPa, 376,455 kg/hr}.
        T_24: Reheater steam outlet temperature, °C. Default 565.6.
        dP_fg: Gas-side pressure drop, MPa. Default 0.
        dP_st: Steam-side pressure drop, MPa. Default 0.310 (NETL).

    Returns:
        ReheaterOutput with all streams and KPIs.
    """
    # Step 1: Gas outlet pressure
    P9 = s8.P - dP_fg

    # Step 2: Steam outlet pressure
    P24 = s_is02.P - dP_st

    # Step 3: IS-02 inlet properties (CoolProp)
    h_is02 = h_water(s_is02.T, s_is02.P)
    s_is02_val = s_water(s_is02.T, s_is02.P)

    # Step 4: S(24) outlet properties (superheated, CoolProp)
    h24 = h_water(T_24, P24)
    s24 = s_water(T_24, P24)

    # Step 5: Steam-side heat duty (kW)
    Q_dot = s_is02.m_dot * (h24 - h_is02) / 3.6e6

    # Step 6: Gas outlet enthalpy
    h8 = h_mix(s8.T + 273.15, s8.w)
    h9 = h8 - Q_dot * 3.6e6 / s8.m_dot

    # Step 7: Gas outlet T and s (NASA-7)
    T9_K = T_from_H_mix(h9, s8.w)
    T9 = T9_K - 273.15
    s9 = s_mix(T9_K, P9 * 1e6, s8.w)

    # Step 8: Mass balances
    m_dot_9 = s8.m_dot
    m_dot_24 = s_is02.m_dot

    # Step 9: KPIs
    dT_fg = s8.T - T9
    TTD_hot = s8.T - T_24
    TTD_cold = T9 - s_is02.T

    # Build output streams
    s9_stream = Stream(T=T9, P=P9, m_dot=m_dot_9, w=dict(s8.w), h=h9, s=s9)
    s24_stream = Stream(
        T=T_24, P=P24, m_dot=m_dot_24,
        w={"H2O": 1.0}, h=h24, s=s24,
    )

    return ReheaterOutput(
        s9=s9_stream,
        s24=s24_stream,
        Q_dot=Q_dot,
        dT_fg=dT_fg,
        TTD_hot=TTD_hot,
        TTD_cold=TTD_cold,
    )

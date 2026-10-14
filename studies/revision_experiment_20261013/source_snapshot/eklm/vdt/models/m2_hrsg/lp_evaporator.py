"""Unit 2-8: LP Evaporator.

Reference: HRSG_Module_Math_Model v1.6 § 8.

Evaporates LP feedwater to saturated vapor (IS-05). Eighth unit in the
flue gas path.

Unlike HP/IP Evaporators (gas-limited, PTD constraint), LP Evaporator is
**water-limited**: LP flow (7,708 kg/hr) is tiny relative to gas flow
(3,230,636 kg/hr), so the gas barely cools. T_lp_fw is a Phase 1 parameter
(spec §8.2: "Phase 1 파라미터로 처리"). PTD becomes a calculated result.

All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import (
    T_sat_water,
    h_sat_vap_water,
    h_water,
    s_sat_vap_water,
    s_water,
)
from eklm.vdt.data.species import T_from_H_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream


@dataclass
class LPEvaporatorOutput:
    """Unit 2-8 outputs."""

    s15: Stream         # Gas outlet → Unit 2-9 LP Economizer
    s_is05: Stream      # LP saturated vapor → M3 LP Turbine
    s_lp_fw: Stream     # LP feedwater inlet (specified parameter)
    Q_dot: float        # Heat duty, kW
    PTD: float          # Pinch temperature difference (calculated), °C
    dT_sub: float       # Subcooling: T_sat − T^(LP_fw), °C


def lp_evaporator(
    s14: Stream,
    m_dot_lp: float = 7_708.0,
    P_LP: float = 0.655,
    T_lp_fw: float = 149.0,
    dP_fg: float = 0.0,
    dP_st: float = 0.0,
) -> LPEvaporatorOutput:
    """Calculate LP Evaporator heat exchange (water-limited mode).

    Args:
        s14: Gas from Unit 2-7 IP Economizer — S^(14).
        m_dot_lp: LP steam mass flow ṁ^(IS-05), kg/hr. NETL: 7,708.
        P_LP: LP steam pressure, MPa. Default 0.655 (95 psia).
        T_lp_fw: LP feedwater inlet temperature, °C. Default 149 (NETL).
        dP_fg: Gas-side pressure drop, MPa. Default 0.
        dP_st: Steam-side pressure drop (drum), MPa. Default 0.

    Returns:
        LPEvaporatorOutput with all streams and KPIs.
    """
    # Pressures
    P15 = s14.P - dP_fg
    P_is05 = P_LP - dP_st
    P_lp_fw = P_LP

    # LP saturation state
    T_sat = T_sat_water(P_LP)
    h_is05 = h_sat_vap_water(P_LP)
    s_is05 = s_sat_vap_water(P_LP)

    # LP feedwater inlet state (specified T, CoolProp)
    h_lp_fw = h_water(T_lp_fw, P_LP)
    s_lp_fw = s_water(T_lp_fw, P_LP)

    # Steam-side heat duty (kW)
    Q_dot = m_dot_lp * (h_is05 - h_lp_fw) / 3.6e6

    # Gas outlet from energy balance
    h14 = h_mix(s14.T + 273.15, s14.w)
    h15 = h14 - Q_dot * 3.6e6 / s14.m_dot

    # Gas outlet T and s (NASA-7)
    T15_K = T_from_H_mix(h15, s14.w)
    T15 = T15_K - 273.15
    s15 = s_mix(T15_K, P15 * 1e6, s14.w)

    # Validity
    if T_lp_fw >= T_sat:
        raise ValueError(
            f"LP Evap: T_lp_fw = {T_lp_fw:.1f} >= T_sat = {T_sat:.1f}. "
            "Feedwater must be subcooled."
        )
    if T15 <= T_sat:
        raise ValueError(
            f"LP Evap: T^(15) = {T15:.1f} <= T_sat = {T_sat:.1f}. "
            "Gas outlet below saturation — insufficient gas heat."
        )

    # KPIs
    PTD = T15 - T_sat
    dT_sub = T_sat - T_lp_fw

    # Build streams
    s15_stream = Stream(T=T15, P=P15, m_dot=s14.m_dot, w=dict(s14.w), h=h15, s=s15)
    s_is05_stream = Stream(
        T=T_sat, P=P_is05, m_dot=m_dot_lp,
        w={"H2O": 1.0}, h=h_is05, s=s_is05,
    )
    s_lp_fw_stream = Stream(
        T=T_lp_fw, P=P_lp_fw, m_dot=m_dot_lp,
        w={"H2O": 1.0}, h=h_lp_fw, s=s_lp_fw,
    )

    return LPEvaporatorOutput(
        s15=s15_stream, s_is05=s_is05_stream, s_lp_fw=s_lp_fw_stream,
        Q_dot=Q_dot, PTD=PTD, dT_sub=dT_sub,
    )

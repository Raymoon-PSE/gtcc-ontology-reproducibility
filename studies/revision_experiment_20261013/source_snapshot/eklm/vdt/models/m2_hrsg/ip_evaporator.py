"""Unit 2-6: IP Evaporator.

Reference: HRSG_Module_Math_Model v1.6 § 6.

Evaporates IP feedwater to saturated vapor. EVA pattern — same as Unit 2-2,
at IP pressure level. S^(21) is back-calculated for Unit 2-7 target.
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import (
    T_sat_water,
    h_sat_liq_water,
    h_sat_vap_water,
    s_sat_vap_water,
    T_from_PH_water,
    s_from_PH_water,
)
from eklm.vdt.data.species import T_from_H_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream


@dataclass
class IPEvaporatorOutput:
    """Unit 2-6 outputs."""

    s13: Stream         # Gas outlet → Unit 2-7 IP Economizer
    s22: Stream         # IP saturated vapor → Unit 2-5 IP SH
    s21: Stream         # IP subcooled water inlet (back-calculated) → Unit 2-7 target
    Q_dot: float        # Heat duty, kW
    PTD: float          # Pinch temperature difference, °C
    dT_sub: float       # Subcooling: T_sat − T^(21), °C


def ip_evaporator(
    s12: Stream,
    m_dot_ip: float,
    P_IP: float = 2.482,
    PTD_IP: float = 10.0,
    dP_fg: float = 0.0,
    dP_st: float = 0.0,
) -> IPEvaporatorOutput:
    """Calculate IP Evaporator heat exchange.

    Args:
        s12: Gas from Unit 2-3 HP Economizer — S^(12).
        m_dot_ip: IP steam mass flow ṁ^(IS-04), kg/hr. NETL: 77,895.
        P_IP: IP steam pressure, MPa. Default 2.482.
        PTD_IP: Pinch Temperature Difference, °C. Default 10.
        dP_fg: Gas-side pressure drop, MPa. Default 0.
        dP_st: Steam-side pressure drop (drum), MPa. Default 0.

    Returns:
        IPEvaporatorOutput with all streams and KPIs.
    """
    # Step 1: Pressures
    P13 = s12.P - dP_fg
    P22 = P_IP - dP_st
    P21 = P_IP

    # Step 3: IP saturation state
    T_sat = T_sat_water(P_IP)
    h22 = h_sat_vap_water(P_IP)
    s22 = s_sat_vap_water(P_IP)

    # Step 4: Pinch constraint — gas outlet
    T13 = T_sat + PTD_IP
    h13 = h_mix(T13 + 273.15, s12.w)
    s13 = s_mix(T13 + 273.15, P13 * 1e6, s12.w)

    # Step 5: Gas-side heat duty
    h12 = h_mix(s12.T + 273.15, s12.w)
    Q_dot = s12.m_dot * (h12 - h13) / 3.6e6

    # Step 6: Back-calculate S^(21)
    h21 = h22 - Q_dot * 3.6e6 / m_dot_ip

    # Preserve both sides of the heat balance when steam capacity binds.
    h_liq = h_sat_liq_water(P_IP)
    if h21 < h_liq:
        h21 = h_liq
        Q_dot = m_dot_ip * (h22 - h21) / 3.6e6
        h13 = h12 - Q_dot * 3.6e6 / s12.m_dot
        T13_K = T_from_H_mix(h13, s12.w)
        T13 = T13_K - 273.15
        s13 = s_mix(T13_K, P13 * 1e6, s12.w)
    if h21 >= h22:
        raise ValueError("IP Evap: insufficient gas heat for positive evaporation")

    T21 = T_from_PH_water(P21, h21)
    s21 = s_from_PH_water(P21, h21)

    # KPIs
    dT_sub = T_sat - T21

    # Build streams
    s13_stream = Stream(T=T13, P=P13, m_dot=s12.m_dot, w=dict(s12.w), h=h13, s=s13)
    s22_stream = Stream(T=T_sat, P=P22, m_dot=m_dot_ip, w={"H2O": 1.0}, h=h22, s=s22)
    s21_stream = Stream(T=T21, P=P21, m_dot=m_dot_ip, w={"H2O": 1.0}, h=h21, s=s21)

    return IPEvaporatorOutput(
        s13=s13_stream, s22=s22_stream, s21=s21_stream,
        Q_dot=Q_dot, PTD=T13-T_sat, dT_sub=dT_sub,
    )

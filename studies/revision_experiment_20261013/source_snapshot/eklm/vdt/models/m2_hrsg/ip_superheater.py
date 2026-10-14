"""Unit 2-5: IP Superheater.

Reference: HRSG_Module_Math_Model v1.6 § 4.

Superheats IP saturated vapor using GT exhaust gas heat.
Fourth unit in the flue gas path. Same SH pattern as Unit 2-1.
Output IS-04 goes to Node 2-4M.
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
class IPSuperheaterOutput:
    """Unit 2-5 outputs."""

    s11: Stream         # Gas outlet → Unit 2-3 HP Economizer
    s_is04: Stream      # IP superheated steam → Node 2-4M
    s22: Stream         # IP saturated vapor inlet (cross-check)
    Q_dot: float        # Heat duty, kW
    dT_fg: float        # Gas-side temperature drop, °C
    TTD_hot: float      # T^(10) − T^(IS-04), °C
    TTD_cold: float     # T^(11) − T^(22), °C (pinch side)


def ip_superheater(
    s10: Stream,
    m_dot_ip: float,
    P_IP: float = 2.482,
    T_is04: float = 568.3,
    dP_fg: float = 0.0,
    dP_st: float = 0.0,
) -> IPSuperheaterOutput:
    """Calculate IP Superheater heat exchange.

    Args:
        s10: Gas from Unit 2-2 HP Evaporator — S^(10).
        m_dot_ip: IP steam mass flow ṁ^(IS-04), kg/hr.
            NETL init: 77,895.
        P_IP: IP steam pressure, MPa. Default 2.482.
        T_is04: IP steam outlet temperature target, °C. Default 568.3.
        dP_fg: Gas-side pressure drop, MPa. Default 0.
        dP_st: Steam-side pressure drop, MPa. Default 0.

    Returns:
        IPSuperheaterOutput with all streams and KPIs.
    """
    # Step 1: Gas outlet pressure
    P11 = s10.P - dP_fg

    # Step 2: Steam outlet pressure
    P_is04 = P_IP - dP_st

    # Step 3: IP saturated vapor inlet (state is f(P_IP) only)
    T22 = T_sat_water(P_IP)
    h22 = h_sat_vap_water(P_IP)
    s22 = s_sat_vap_water(P_IP)

    # Step 4: IP steam outlet (superheated)
    h_is04 = h_water(T_is04, P_is04)
    s_is04 = s_water(T_is04, P_is04)

    # Step 5: Steam-side heat duty (kW)
    Q_dot = m_dot_ip * (h_is04 - h22) / 3.6e6

    # Step 6: Gas outlet enthalpy
    h10 = h_mix(s10.T + 273.15, s10.w)
    h11 = h10 - Q_dot * 3.6e6 / s10.m_dot

    # Step 7: Gas outlet T and s (NASA-7)
    T11_K = T_from_H_mix(h11, s10.w)
    T11 = T11_K - 273.15
    s11 = s_mix(T11_K, P11 * 1e6, s10.w)

    # Step 8: Mass balances
    m_dot_11 = s10.m_dot
    m_dot_is04 = m_dot_ip

    # Step 9: KPIs
    dT_fg = s10.T - T11
    TTD_hot = s10.T - T_is04
    TTD_cold = T11 - T22

    # Build output streams
    s11_stream = Stream(T=T11, P=P11, m_dot=m_dot_11, w=dict(s10.w), h=h11, s=s11)
    s_is04_stream = Stream(
        T=T_is04, P=P_is04, m_dot=m_dot_is04,
        w={"H2O": 1.0}, h=h_is04, s=s_is04,
    )
    s22_stream = Stream(
        T=T22, P=P_IP, m_dot=m_dot_ip,
        w={"H2O": 1.0}, h=h22, s=s22,
    )

    return IPSuperheaterOutput(
        s11=s11_stream,
        s_is04=s_is04_stream,
        s22=s22_stream,
        Q_dot=Q_dot,
        dT_fg=dT_fg,
        TTD_hot=TTD_hot,
        TTD_cold=TTD_cold,
    )

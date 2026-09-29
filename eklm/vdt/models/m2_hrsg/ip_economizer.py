"""Unit 2-7: IP Economizer.

Reference: HRSG_Module_Math_Model v1.6 § 7.

Preheats IP feedwater using GT exhaust gas heat. ECO pattern — same as
Unit 2-3, at IP pressure level. S^(21) target from Unit 2-6.
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import h_water, s_water
from eklm.vdt.data.species import T_from_H_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream


@dataclass
class IPEconomizerOutput:
    """Unit 2-7 outputs."""

    s14: Stream         # Gas outlet → Unit 2-8 LP Evaporator
    s20: Stream         # IP feedwater inlet (from IP BFP)
    Q_dot: float        # Heat duty, kW
    dT_fg: float        # Gas-side temperature drop, °C
    dT_cold: float      # Cold-end approach: T^(14) − T^(20), °C


def ip_economizer(
    s13: Stream,
    s21: Stream,
    m_dot_ip: float,
    T_20: float = 150.0,
    P_IP: float = 2.482,
    dP_fg: float = 0.0,
) -> IPEconomizerOutput:
    """Calculate IP Economizer heat exchange.

    Args:
        s13: Gas from Unit 2-6 IP Evaporator — S^(13).
        s21: Subcooled IP water outlet target — from Unit 2-6 (back-calculated).
        m_dot_ip: IP water mass flow ṁ^(IS-04), kg/hr.
        T_20: IP feedwater inlet temperature (BFP outlet), °C. Default 150.
        P_IP: IP steam pressure (= water-side pressure), MPa. Default 2.482.
        dP_fg: Gas-side pressure drop, MPa. Default 0.

    Returns:
        IPEconomizerOutput with all streams and KPIs.
    """
    # Step 1: Gas outlet pressure
    P14 = s13.P - dP_fg

    # Step 2: Water-side pressure
    P20 = P_IP

    # Step 3: IP feedwater inlet state (CoolProp, subcooled)
    h20 = h_water(T_20, P_IP)
    s20 = s_water(T_20, P_IP)

    # Step 4: Water-side heat duty
    Q_dot = m_dot_ip * (s21.h - h20) / 3.6e6

    # Step 5: Gas outlet enthalpy
    h13 = h_mix(s13.T + 273.15, s13.w)
    h14 = h13 - Q_dot * 3.6e6 / s13.m_dot

    # Step 6: Gas outlet T and s (NASA-7)
    T14_K = T_from_H_mix(h14, s13.w)
    T14 = T14_K - 273.15
    s14 = s_mix(T14_K, P14 * 1e6, s13.w)

    # Step 7: Mass balances
    m_dot_14 = s13.m_dot

    # Validity (warnings for off-design tolerance)
    if T_20 >= s21.T:
        import warnings
        warnings.warn(f"IP Eco: T^(20) = {T_20:.1f} >= T^(21) = {s21.T:.1f}")
    if T14 <= T_20:
        import warnings
        warnings.warn(f"IP Eco: T^(14) = {T14:.1f} <= T^(20) = {T_20:.1f}")

    # KPIs
    dT_fg = s13.T - T14
    dT_cold = T14 - T_20

    # Build streams
    s14_stream = Stream(T=T14, P=P14, m_dot=m_dot_14, w=dict(s13.w), h=h14, s=s14)
    s20_stream = Stream(T=T_20, P=P20, m_dot=m_dot_ip, w={"H2O": 1.0}, h=h20, s=s20)

    return IPEconomizerOutput(
        s14=s14_stream, s20=s20_stream,
        Q_dot=Q_dot, dT_fg=dT_fg, dT_cold=dT_cold,
    )

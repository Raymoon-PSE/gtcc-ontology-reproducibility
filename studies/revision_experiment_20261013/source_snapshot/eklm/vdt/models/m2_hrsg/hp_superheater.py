"""Unit 2-1: HP Superheater.

Reference: HRSG_Module_Math_Model v1.6 § 1.

Superheats HP saturated vapor from HP Evaporator using GT exhaust gas heat.
First unit in the flue gas calculation path — receives the hottest gas.
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
class HPSuperheaterOutput:
    """Unit 2-1 outputs."""

    s8: Stream          # Gas outlet → Unit 2-4 Reheater
    s_is01: Stream      # HP Main Steam → M3 HP Turbine
    s19: Stream         # HP saturated vapor inlet (for cross-check)
    Q_dot: float        # Heat duty, kW
    dT_fg: float        # Gas-side temperature drop, °C
    TTD_hot: float      # T^(7) − T^(IS-01), °C
    TTD_cold: float     # T^(8) − T^(19), °C (pinch side)


def hp_superheater(
    s7: Stream,
    m_dot_hp: float,
    P_HP: float = 16.65,
    T_is01: float = 565.6,
    dP_fg: float = 0.0,
    dP_st: float = 0.0,
) -> HPSuperheaterOutput:
    """Calculate HP Superheater heat exchange.

    Args:
        s7: GT exhaust gas stream S^(7) — from M1.
        m_dot_hp: HP steam mass flow ṁ^(IS-01), kg/hr.
            Supplied by SM convergence loop (NETL init: 392,884).
        P_HP: HP steam pressure, MPa. Default 16.65.
        T_is01: HP steam outlet temperature target, °C. Default 565.6.
        dP_fg: Gas-side pressure drop, MPa. Default 0.
        dP_st: Steam-side pressure drop, MPa. Default 0.

    Returns:
        HPSuperheaterOutput with all streams and KPIs.
    """
    # Step 1: Gas outlet pressure
    P8 = s7.P - dP_fg

    # Step 2: Steam outlet pressure
    P_is01 = P_HP - dP_st

    # Step 3: HP saturated vapor inlet (from Unit 2-2, state is f(P_HP) only)
    T19 = T_sat_water(P_HP)
    h19 = h_sat_vap_water(P_HP)
    s19 = s_sat_vap_water(P_HP)

    # Step 4: HP steam outlet (superheated, specified T and P)
    h_is01 = h_water(T_is01, P_is01)
    s_is01 = s_water(T_is01, P_is01)

    # Step 5: Steam-side heat duty (kW)
    # ṁ [kg/hr] × Δh [J/kg] / 3.6e6 = kW
    Q_dot = m_dot_hp * (h_is01 - h19) / 3.6e6

    # Step 6: Gas outlet enthalpy
    # Q_dot [kW] × 3.6e6 / ṁ_gas [kg/hr] = Δh [J/kg]
    h7 = h_mix(s7.T + 273.15, s7.w)
    h8 = h7 - Q_dot * 3.6e6 / s7.m_dot

    # Step 7: Gas outlet T and s (NASA-7)
    T8_K = T_from_H_mix(h8, s7.w)
    T8 = T8_K - 273.15
    s8 = s_mix(T8_K, P8 * 1e6, s7.w)

    # Step 8: Mass balances
    m_dot_8 = s7.m_dot
    m_dot_is01 = m_dot_hp

    # Step 9: KPIs
    dT_fg = s7.T - T8
    TTD_hot = s7.T - T_is01
    TTD_cold = T8 - T19

    # Build output streams
    s8_stream = Stream(T=T8, P=P8, m_dot=m_dot_8, w=dict(s7.w), h=h8, s=s8)
    s_is01_stream = Stream(
        T=T_is01, P=P_is01, m_dot=m_dot_is01,
        w={"H2O": 1.0}, h=h_is01, s=s_is01,
    )
    s19_stream = Stream(
        T=T19, P=P_HP, m_dot=m_dot_hp,
        w={"H2O": 1.0}, h=h19, s=s19,
    )

    return HPSuperheaterOutput(
        s8=s8_stream,
        s_is01=s_is01_stream,
        s19=s19_stream,
        Q_dot=Q_dot,
        dT_fg=dT_fg,
        TTD_hot=TTD_hot,
        TTD_cold=TTD_cold,
    )

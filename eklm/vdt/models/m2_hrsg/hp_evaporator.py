"""Unit 2-2: HP Evaporator.

Reference: HRSG_Module_Math_Model v1.6 § 3.

Evaporates HP feedwater to saturated vapor using GT exhaust gas heat.
Drum-type evaporator: subcooled water → saturated vapor (x=1).
Design constraint = Pinch Temperature Difference (PTD).

Key: S^(18) state is **back-calculated** by this unit and passed to
Unit 2-3 (HP Economizer) as the steam-side outlet target.
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
class HPEvaporatorOutput:
    """Unit 2-2 outputs."""

    s10: Stream         # Gas outlet → Unit 2-5 IP Superheater
    s19: Stream         # HP saturated vapor → Unit 2-1 HP SH
    s18: Stream         # HP subcooled water inlet (back-calculated) → Unit 2-3 target
    Q_dot: float        # Heat duty, kW
    PTD: float          # Pinch temperature difference (= T^(10) − T_sat), °C
    dT_sub: float       # Subcooling at eco exit: T_sat − T^(18), °C
    dh_vap: float       # Latent heat of vaporization, J/kg


def hp_evaporator(
    s9: Stream,
    m_dot_hp: float,
    P_HP: float = 16.65,
    PTD_HP: float = 10.0,
    dP_fg: float = 0.0,
    dP_st: float = 0.0,
) -> HPEvaporatorOutput:
    """Calculate HP Evaporator heat exchange.

    Args:
        s9: Gas from Unit 2-4 Reheater — S^(9).
        m_dot_hp: HP steam mass flow ṁ^(IS-01), kg/hr.
        P_HP: HP steam pressure, MPa. Default 16.65.
        PTD_HP: Pinch Temperature Difference, °C. Default 10.
        dP_fg: Gas-side pressure drop, MPa. Default 0.
        dP_st: Steam-side pressure drop (drum), MPa. Default 0.

    Returns:
        HPEvaporatorOutput with all streams and KPIs.
    """
    # Step 1: Gas outlet pressure
    P10 = s9.P - dP_fg

    # Step 2: Steam/water pressures
    P19 = P_HP - dP_st
    P18 = P_HP

    # Step 3: HP saturation state (CoolProp)
    T_sat = T_sat_water(P_HP)
    h19 = h_sat_vap_water(P_HP)
    s19 = s_sat_vap_water(P_HP)

    # Step 4: Pinch constraint — gas outlet temperature
    T10 = T_sat + PTD_HP
    h10 = h_mix(T10 + 273.15, s9.w)
    s10 = s_mix(T10 + 273.15, P10 * 1e6, s9.w)

    # Step 5: Gas-side heat duty (kW)
    h9 = h_mix(s9.T + 273.15, s9.w)
    Q_dot = s9.m_dot * (h9 - h10) / 3.6e6

    # Step 6: Back-calculate S^(18) water inlet state
    h18 = h19 - Q_dot * 3.6e6 / m_dot_hp

    # Energy-conserving cap on HP-Evap duty.
    #
    # The gas-side PTD constraint can demand more heat than the steam side
    # can absorb at the prescribed m_dot_hp (latent + small subcool margin).
    # Earlier versions silently clamped h18 to h_sat_liq, but kept Q_dot
    # and T10 at their gas-side over-allocated values — so the "excess"
    # ~25 MW vanished from the energy balance and downstream HP-Eco saw a
    # gas T cooler than physical.
    #
    # Correct treatment: when steam-side becomes the binding constraint,
    # recompute Q_dot from the steam side and re-derive gas outlet T10.
    # The residual gas heat (above PTD) now flows on to downstream sections
    # and is recovered there, conserving energy across the HRSG.
    h_liq_hp = h_sat_liq_water(P_HP)
    if h18 < h_liq_hp:
        # Steam side saturates at h_sat_liq; recompute Q_dot from there.
        h18 = h_liq_hp
        Q_dot = m_dot_hp * (h19 - h18) / 3.6e6
        # Re-derive gas outlet
        h10 = h9 - Q_dot * 3.6e6 / s9.m_dot
        T10_K = T_from_H_mix(h10, s9.w)
        T10 = T10_K - 273.15
        s10 = s_mix(T10_K, P10 * 1e6, s9.w)

    T18 = T_from_PH_water(P18, h18)
    s18 = s_from_PH_water(P18, h18)

    # Step 7: Mass balances
    m_dot_10 = s9.m_dot

    # Step 8: Validity check (subcooled inlet)
    h_liq = h_sat_liq_water(P_HP)
    if h18 >= h19:
        raise ValueError(
            f"HP Evap: h^(18) = {h18:.0f} >= h_sat_vap = {h19:.0f} J/kg. "
            "Check PTD_HP or m_dot_hp."
        )

    # Step 9: KPIs
    dT_sub = T_sat - T18
    dh_vap = h19 - h_liq

    # Build output streams
    s10_stream = Stream(T=T10, P=P10, m_dot=m_dot_10, w=dict(s9.w), h=h10, s=s10)
    s19_stream = Stream(
        T=T_sat, P=P19, m_dot=m_dot_hp,
        w={"H2O": 1.0}, h=h19, s=s19,
    )
    s18_stream = Stream(
        T=T18, P=P18, m_dot=m_dot_hp,
        w={"H2O": 1.0}, h=h18, s=s18,
    )

    return HPEvaporatorOutput(
        s10=s10_stream,
        s19=s19_stream,
        s18=s18_stream,
        Q_dot=Q_dot,
        PTD=PTD_HP,
        dT_sub=dT_sub,
        dh_vap=dh_vap,
    )

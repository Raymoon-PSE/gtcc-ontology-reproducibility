"""Unit 2-3: HP Economizer.

Reference: HRSG_Module_Math_Model v1.6 § 5.

Preheats HP feedwater using GT exhaust gas heat. Subcooled liquid only.
Fifth unit in the flue gas path. ECO pattern: T^(17) specified as inlet,
S^(18) target from Unit 2-2 HP Evaporator (already determined).
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import T_sat_water, h_water, s_water
from eklm.vdt.data.species import T_from_H_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream


@dataclass
class HPEconomizerOutput:
    """Unit 2-3 outputs."""

    s12: Stream         # Gas outlet → Unit 2-6 IP Evaporator
    s17: Stream         # HP feedwater inlet (from HP BFP)
    Q_dot: float        # Heat duty, kW
    dT_fg: float        # Gas-side temperature drop, °C
    dT_cold: float      # Cold-end approach: T^(12) − T^(17), °C
    dT_sub: float       # Subcooling margin: T_sat − T^(18), °C


def hp_economizer(
    s11: Stream,
    s18: Stream,
    m_dot_hp: float,
    T_17: float = 150.0,
    P_HP: float = 16.65,
    dP_fg: float = 0.0,
) -> HPEconomizerOutput:
    """Calculate HP Economizer heat exchange.

    Args:
        s11: Gas from Unit 2-5 IP Superheater — S^(11).
        s18: Subcooled HP water outlet target — from Unit 2-2 (back-calculated).
        m_dot_hp: HP water mass flow ṁ^(IS-01), kg/hr.
        T_17: HP feedwater inlet temperature (BFP outlet), °C. Default 150.
        P_HP: HP steam pressure (= water-side pressure), MPa. Default 16.65.
        dP_fg: Gas-side pressure drop, MPa. Default 0.

    Returns:
        HPEconomizerOutput with all streams and KPIs.
    """
    # Step 1: Gas outlet pressure
    P12 = s11.P - dP_fg

    # Step 2: Water-side pressure (BFP supplies drum pressure)
    P17 = P_HP

    # Step 3: HP feedwater inlet state (CoolProp, subcooled liquid)
    h17 = h_water(T_17, P_HP)
    s17 = s_water(T_17, P_HP)

    # Step 4: Water-side heat duty (kW)
    Q_dot = m_dot_hp * (s18.h - h17) / 3.6e6

    # Step 5: Gas outlet enthalpy
    h11 = h_mix(s11.T + 273.15, s11.w)
    h12 = h11 - Q_dot * 3.6e6 / s11.m_dot

    # Step 6: Gas outlet T and s (NASA-7)
    T12_K = T_from_H_mix(h12, s11.w)
    T12 = T12_K - 273.15
    s12 = s_mix(T12_K, P12 * 1e6, s11.w)

    # Step 7: Mass balances
    m_dot_12 = s11.m_dot

    # Step 8: Validity checks (warnings, not errors — allow C-CS sweep)
    # Off-design conditions (e.g., H2 blend) can violate these constraints
    if T_17 >= s18.T:
        import warnings
        warnings.warn(f"HP Eco: T^(17) = {T_17:.1f} >= T^(18) = {s18.T:.1f}")
    if T12 <= T_17:
        import warnings
        warnings.warn(f"HP Eco: T^(12) = {T12:.1f} <= T^(17) = {T_17:.1f}")

    # Step 9: KPIs
    dT_fg = s11.T - T12
    dT_cold = T12 - T_17
    dT_sub = T_sat_water(P_HP) - s18.T

    # Build output streams
    s12_stream = Stream(T=T12, P=P12, m_dot=m_dot_12, w=dict(s11.w), h=h12, s=s12)
    s17_stream = Stream(
        T=T_17, P=P17, m_dot=m_dot_hp,
        w={"H2O": 1.0}, h=h17, s=s17,
    )

    return HPEconomizerOutput(
        s12=s12_stream,
        s17=s17_stream,
        Q_dot=Q_dot,
        dT_fg=dT_fg,
        dT_cold=dT_cold,
        dT_sub=dT_sub,
    )

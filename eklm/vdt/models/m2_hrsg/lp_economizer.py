"""Unit 2-9: LP Economizer.

Reference: HRSG_Module_Math_Model v1.6 § 9.

Preheats total condensate (IS-06) using GT exhaust gas. Last unit in the
flue gas path. STACK-ECO pattern: T^(16) (stack temperature) is the design
parameter; condensate outlet S^(23) is calculated from energy balance.

Phase 1 note: IS-06 arrives at condenser vacuum (0.00690 MPa), but a
condensate pump raises pressure before LP Eco entry. Water-side pressure
P_eco defaults to P_LP (0.655 MPa) to keep water subcooled through heating.
All explicit. No iteration.
"""

from dataclasses import dataclass

from eklm.vdt.data.properties import h_water, s_water, T_from_PH_water, s_from_PH_water
from eklm.vdt.data.species import T_from_H_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream


@dataclass
class LPEconomizerOutput:
    """Unit 2-9 outputs."""

    s16: Stream         # Stack Gas → plant boundary
    s23: Stream         # Preheated condensate → Deaerator/BFP
    Q_dot: float        # Heat duty, kW
    dT_fg: float        # Gas-side temperature drop, °C
    T_23: float         # Condensate outlet temperature, °C (NETL: ~149°C)


def lp_economizer(
    s15: Stream,
    s_is06: Stream,
    T_16: float = 106.0,
    P_eco: float = 0.655,
    dP_fg: float = 0.0,
) -> LPEconomizerOutput:
    """Calculate LP Economizer heat exchange.

    Args:
        s15: Gas from Unit 2-8 LP Evaporator — S^(15).
        s_is06: Condensate — IS-06 (primary tear stream).
            NETL init: {38.4 °C, 0.00690 MPa, 514,240 kg/hr}.
        T_16: Stack Gas temperature (design target), °C. Default 106.
        P_eco: Water-side pressure after condensate pump, MPa.
            Default 0.655 (= P_LP). Keeps water subcooled through heating.
        dP_fg: Gas-side pressure drop, MPa. Default 0.

    Returns:
        LPEconomizerOutput with all streams and KPIs.
    """
    # Pressures
    P16 = s15.P - dP_fg
    P23 = P_eco

    # IS-06 inlet properties at pumped pressure (CoolProp, subcooled liquid)
    h_is06 = h_water(s_is06.T, P_eco)
    s_is06_val = s_water(s_is06.T, P_eco)

    # Stack gas outlet (specified temperature, NASA-7)
    h16 = h_mix(T_16 + 273.15, s15.w)
    s16 = s_mix(T_16 + 273.15, P16 * 1e6, s15.w)

    # Gas-side heat duty
    h15 = h_mix(s15.T + 273.15, s15.w)
    Q_dot = s15.m_dot * (h15 - h16) / 3.6e6

    # Condensate outlet
    h23 = h_is06 + Q_dot * 3.6e6 / s_is06.m_dot
    T23 = T_from_PH_water(P23, h23)
    s23 = s_from_PH_water(P23, h23)

    # Validity
    if T23 <= s_is06.T:
        raise ValueError(
            f"LP Eco: T^(23) = {T23:.1f} <= T^(IS-06) = {s_is06.T:.1f}."
        )
    if T23 >= s15.T:
        raise ValueError(
            f"LP Eco: T^(23) = {T23:.1f} >= T^(15) = {s15.T:.1f}. "
            "Temperature cross."
        )

    # KPIs
    dT_fg = s15.T - T_16

    # Build streams
    s16_stream = Stream(T=T_16, P=P16, m_dot=s15.m_dot, w=dict(s15.w), h=h16, s=s16)
    s23_stream = Stream(T=T23, P=P23, m_dot=s_is06.m_dot, w={"H2O": 1.0}, h=h23, s=s23)

    return LPEconomizerOutput(
        s16=s16_stream, s23=s23_stream,
        Q_dot=Q_dot, dT_fg=dT_fg, T_23=T23,
    )

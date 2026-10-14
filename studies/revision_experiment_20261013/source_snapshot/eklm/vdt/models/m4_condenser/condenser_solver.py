"""M4 Condenser + CWS module solver.

Reference: Condenser_CWS_Math_Model v1.0.

6 units in sequential order:
    4-1 Main Condenser (steam side + condensate pump sub-calc)
    4-2 Vacuum System (parametric)
    4-3 CWP (CW flow + pump power)
    4-4 Cooling Tower (evaporation, blowdown, makeup)
    4-5 Auxiliary Cooling (parametric)
    4-6 Makeup Water (total raw water)

IS-06 is defined at condensate pump outlet conditions (Option A, Open Issue #19).
All explicit. No internal iteration.
"""

from dataclasses import dataclass, field
import math

from CoolProp.CoolProp import PropsSI

from eklm.vdt.data.properties import (
    T_sat_water,
    h_sat_liq_water,
    h_water,
    s_water,
    T_from_PH_water,
    s_from_PH_water,
)
from eklm.vdt.data.streams import Stream


@dataclass
class CondenserOutput:
    """M4 Condenser module outputs."""

    # Module boundary output
    s_is06: Stream      # Condensate -> M2 HRSG LP Eco (primary tear stream)

    # KPIs
    Q_cond: float       # Condenser duty, kW
    W_cp: float         # Condensate pump power, kW
    W_cwp: float        # CW pump power, kW
    W_vac: float        # Vacuum system power, kW
    W_ct_fan: float     # CT fan power, kW
    W_auxc: float       # Auxiliary cooling pump power, kW
    W_CWS: float        # Total CWS auxiliary power, kW

    # CW system
    m_dot_cw: float     # CW circulation rate, kg/hr
    m_dot_evap: float   # CT evaporation rate, kg/hr
    m_dot_blow: float   # CT blowdown rate, kg/hr
    m_dot_muw: float    # Total raw water withdrawal, kg/hr

    # Internal streams (diagnostics)
    s32: Stream         # Hot CW from condenser -> CT
    s_is06_hw: Stream   # Hot well state (pre-pump, saturated liquid)
    water_audit: dict = field(default_factory=dict)


@dataclass
class CondenserParams:
    """M4 Condenser design parameters."""

    # Unit 4-1: Main Condenser
    P_cond: float = 0.00677         # Condenser pressure, MPa
    m_dot_gsc: float = 635.0        # GSC condensate flow, kg/hr (gland-seal)
    h_gsc: float = 160_700.0        # GSC condensate enthalpy, J/kg (sat liq)
    m_dot_cond_muw: float = 5_138.0 # Condenser makeup flow, kg/hr
    # Steam-seal regulator + continuous-blowdown return drains. NETL HMB
    # Exhibit 5-11 shows ~10,969 lb/hr through the steam-seal regulator
    # plus various smaller cycle drains. Combined ≈ 11,845 kg/hr.
    m_dot_ssr: float = 11_845.0     # Steam-seal regulator + drains, kg/hr
    h_ssr: float = 160_700.0        # Drain enthalpy ≈ sat liq at P_cond
    P_cp_out: float = 0.896         # Condensate pump outlet pressure, MPa
    eta_cp: float = 0.80            # Condensate pump efficiency

    # Unit 4-2: Vacuum System
    W_vac: float = 100.0            # Vacuum system power, kW

    # Unit 4-3: CWP
    T_cw_in: float = 18.3           # CW supply temperature, C
    dT_cw: float = 17.0             # CW temperature rise, C
    P_cw_s: float = 0.101           # CW suction pressure, MPa
    P_cw_d: float = 0.35            # CW discharge pressure, MPa
    eta_cwp: float = 0.85           # CWP efficiency

    # Unit 4-4: Cooling Tower
    f_evap: float = 0.80            # Evaporation fraction
    COC: float = 5.0                # Cycles of concentration
    f_drift: float = 1e-4           # Drift loss fraction
    W_ct_fan: float = 500.0         # CT fan power, kW

    # Unit 4-5: Auxiliary Cooling
    W_auxc: float = 200.0           # Auxiliary cooling pump power, kW

    # Unit 4-6: Makeup Water
    T_muw: float = 15.0             # Raw water supply temperature, C
    P_muw: float = 0.101325         # Makeup supply pressure, MPa; isenthalpic admission


def condenser_solve(
    s28: Stream,
    params: CondenserParams | None = None,
) -> CondenserOutput:
    """Solve the Condenser + CWS module.

    Args:
        s28: ST exhaust from M3 -- S^(28), wet steam.
        params: Condenser design parameters. None -> NETL defaults.

    Returns:
        CondenserOutput with IS-06 and all KPIs.
    """
    if params is None:
        params = CondenserParams()
    p = params

    values = (s28.m_dot, s28.h, p.m_dot_gsc, p.h_gsc, p.m_dot_ssr,
              p.h_ssr, p.m_dot_cond_muw, p.T_muw, p.P_muw)
    if any(x is None or not math.isfinite(x) for x in values):
        raise ValueError("Condenser water boundary inputs must be finite")
    if min(s28.m_dot, p.m_dot_gsc, p.m_dot_ssr, p.m_dot_cond_muw) < 0:
        raise ValueError("Condenser water boundary flows must be nonnegative")
    if p.P_muw <= 0:
        raise ValueError("Makeup supply pressure must be positive")
    # Evaluate liquid makeup at its supply state, preserving enthalpy through
    # admission to vacuum. The inlet may flash; no forced liquid phase there.
    if p.T_muw >= T_sat_water(p.P_muw):
        raise ValueError("Condenser makeup supply must be subcooled liquid")
    h_muw = h_water(p.T_muw, p.P_muw)

    # == Unit 4-1: Main Condenser (steam side) ============================

    # IS-06 mass balance — LP exhaust + gland-seal + makeup + ssr drains
    m_dot_is06 = s28.m_dot + p.m_dot_gsc + p.m_dot_cond_muw + p.m_dot_ssr

    # Hot well state (saturated liquid at condenser pressure)
    T_hw = T_sat_water(p.P_cond)
    h_hw = h_sat_liq_water(p.P_cond)
    s_hw = PropsSI("S", "P", p.P_cond * 1e6, "Q", 0, "Water")

    s_is06_hw = Stream(
        T=T_hw, P=p.P_cond, m_dot=m_dot_is06,
        w={"H2O": 1.0}, h=h_hw, s=s_hw,
    )

    # Condenser duty includes heating the cold makeup as well as drain returns.
    Q_cond = (s28.m_dot * (s28.h - h_hw)
              + p.m_dot_gsc * (p.h_gsc - h_hw)
              + p.m_dot_ssr * (p.h_ssr - h_hw)
              + p.m_dot_cond_muw * (h_muw - h_hw)) / 3.6e6
    if Q_cond <= 0:
        raise ValueError("Condenser boundary requires positive heat rejection")

    # Condensate pump sub-calculation
    # Use Q=0 (sat liquid) to avoid CoolProp saturation boundary error
    rho_hw = PropsSI("D", "P", p.P_cond * 1e6, "Q", 0, "Water")
    v_hw = 1.0 / rho_hw  # m3/kg
    # W_cp [kW] = m_dot [kg/hr] * v [m3/kg] * dP [Pa] / (eta * 3600 [s/hr])
    dP_cp = (p.P_cp_out - p.P_cond) * 1e6  # Pa
    # m_dot [kg/hr] * v [m3/kg] * dP [Pa] / (eta * 3.6e6) = kW
    W_cp = m_dot_is06 * v_hw * dP_cp / (p.eta_cp * 3.6e6)

    # IS-06 at condensate pump outlet (Option A, Open Issue #19)
    h_is06 = h_hw + v_hw * dP_cp / p.eta_cp
    T_is06 = T_from_PH_water(p.P_cp_out, h_is06)
    s_is06 = s_from_PH_water(p.P_cp_out, h_is06)

    s_is06_stream = Stream(
        T=T_is06, P=p.P_cp_out, m_dot=m_dot_is06,
        w={"H2O": 1.0}, h=h_is06, s=s_is06,
    )

    # == Unit 4-3: CWP ===================================================

    cp_w = PropsSI("C", "T", p.T_cw_in + 273.15, "P", p.P_cw_s * 1e6, "Water")
    m_dot_cw = Q_cond * 3.6e6 / (cp_w * p.dT_cw)  # kg/hr

    rho_cw = PropsSI("D", "T", p.T_cw_in + 273.15, "P", p.P_cw_s * 1e6, "Water")
    v_cw = 1.0 / rho_cw
    h33 = h_water(p.T_cw_in, p.P_cw_s)
    dP_cwp = (p.P_cw_d - p.P_cw_s) * 1e6
    h31 = h33 + v_cw * dP_cwp / p.eta_cwp
    W_cwp = m_dot_cw * (h31 - h33) / 3.6e6  # kW

    # == Unit 4-1 CW side: S^(32) ========================================

    T32 = p.T_cw_in + p.dT_cw
    h32 = h_water(T32, p.P_cw_d)
    s32 = s_water(T32, p.P_cw_d)

    s32_stream = Stream(
        T=T32, P=p.P_cw_d, m_dot=m_dot_cw,
        w={"H2O": 1.0}, h=h32, s=s32,
    )

    # == Unit 4-4: Cooling Tower ==========================================

    T_avg = p.T_cw_in + p.dT_cw / 2.0
    h_fg = (PropsSI("H", "T", T_avg + 273.15, "Q", 1, "Water")
            - PropsSI("H", "T", T_avg + 273.15, "Q", 0, "Water"))
    m_dot_evap = p.f_evap * Q_cond * 3.6e6 / h_fg  # kg/hr
    m_dot_blow = m_dot_evap / (p.COC - 1)
    m_dot_drift = p.f_drift * m_dot_cw
    m_dot_muw_ct = m_dot_evap + m_dot_blow + m_dot_drift

    # == Unit 4-6: Makeup Water ===========================================

    m_dot_muw_total = m_dot_muw_ct + p.m_dot_cond_muw

    # == Total CWS auxiliary power ========================================

    W_CWS = W_cp + p.W_vac + W_cwp + p.W_ct_fan + p.W_auxc

    return CondenserOutput(
        s_is06=s_is06_stream,
        Q_cond=Q_cond,
        W_cp=W_cp,
        W_cwp=W_cwp,
        W_vac=p.W_vac,
        W_ct_fan=p.W_ct_fan,
        W_auxc=p.W_auxc,
        W_CWS=W_CWS,
        m_dot_cw=m_dot_cw,
        m_dot_evap=m_dot_evap,
        m_dot_blow=m_dot_blow,
        m_dot_muw=m_dot_muw_total,
        s32=s32_stream,
        s_is06_hw=s_is06_hw,
        water_audit={
            "scope": "local_condenser_water_and_condensate_pump",
            "inlet_flows_kg_hr": {"turbine_exhaust": s28.m_dot, "gland_return": p.m_dot_gsc,
                                   "makeup": p.m_dot_cond_muw, "other_drains": p.m_dot_ssr},
            "makeup_supply_enthalpy_J_kg": h_muw,
            "makeup_heat_contribution_kW": p.m_dot_cond_muw * (h_muw - h_hw) / 3.6e6,
            "mass_residual_kg_hr": m_dot_is06 - s_is06_hw.m_dot,
            "energy_residual_kW": (s28.m_dot*s28.h + p.m_dot_gsc*p.h_gsc
                                   + p.m_dot_ssr*p.h_ssr + p.m_dot_cond_muw*h_muw
                                   - s_is06_hw.m_dot*s_is06_hw.h) / 3.6e6 - Q_cond,
            "pump_energy_residual_kW": m_dot_is06*(h_is06-h_hw)/3.6e6-W_cp,
            "whole_cycle_closed": False,
            "limitations": ["Drain and gland flows are imposed boundaries, not linked upstream returns",
                            "Cooling tower and drum blowdown belong to separate water circuits"],
        },
    )

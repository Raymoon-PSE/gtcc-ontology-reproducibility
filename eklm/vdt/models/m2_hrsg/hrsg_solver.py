"""M2 HRSG module solver — sequential calculation of 9 heat exchanger units.

Reference: HRSG_Module_Math_Model v1.6, GTCC_HRSG_Convergence_Strategy §4.

Calculation order follows flue gas direction (hottest → coldest):
    2-1 HP SH → 2-4 Reheater → 2-2 HP Evap → 2-5 IP SH →
    2-3 HP Eco → 2-6 IP Evap → 2-7 IP Eco → 2-8 LP Evap → 2-9 LP Eco
Node 2-4M (IP Mixing) is computed after Unit 2-5.

Phase 1: No internal iteration. All units are explicit.
SM convergence loop (Wegstein) is external — handles IS-06 and IS-02 tear
streams across M2/M3/M4 modules.
"""

from dataclasses import dataclass

from eklm.vdt.models.m2_hrsg.hp_superheater import HPSuperheaterOutput, hp_superheater
from eklm.vdt.models.m2_hrsg.reheater import ReheaterOutput, reheater
from eklm.vdt.models.m2_hrsg.ip_mixing_node import IPMixingNodeOutput, ip_mixing_node
from eklm.vdt.models.m2_hrsg.hp_evaporator import HPEvaporatorOutput, hp_evaporator
from eklm.vdt.models.m2_hrsg.ip_superheater import IPSuperheaterOutput, ip_superheater
from eklm.vdt.models.m2_hrsg.hp_economizer import HPEconomizerOutput, hp_economizer
from eklm.vdt.models.m2_hrsg.ip_evaporator import IPEvaporatorOutput, ip_evaporator
from eklm.vdt.models.m2_hrsg.ip_economizer import IPEconomizerOutput, ip_economizer
from eklm.vdt.models.m2_hrsg.lp_evaporator import LPEvaporatorOutput, lp_evaporator
from eklm.vdt.models.m2_hrsg.lp_economizer import LPEconomizerOutput, lp_economizer
from eklm.vdt.models.m2_hrsg.deaerator import DeaeratorOutput, deaerator
from eklm.vdt.models.m2_hrsg.bfp import BFPOutput, bfp
from eklm.vdt.data.streams import Stream


@dataclass
class HRSGOutput:
    """M2 HRSG module outputs."""

    # Module boundary outputs
    s_is01: Stream      # HP Main Steam → M3 HP Turbine
    s_is03: Stream      # Hot Reheat Steam → M3 IP Turbine
    s_is05: Stream      # LP Steam → M3 LP Turbine
    s16: Stream         # Stack Gas → plant boundary

    # Internal outputs (for diagnostics / T-Q diagram)
    s23: Stream         # Preheated condensate → Deaerator/BFP

    # Per-unit results
    unit_21: HPSuperheaterOutput
    unit_24: ReheaterOutput
    node_24m: IPMixingNodeOutput
    unit_22: HPEvaporatorOutput
    unit_25: IPSuperheaterOutput
    unit_23: HPEconomizerOutput
    unit_26: IPEvaporatorOutput
    unit_27: IPEconomizerOutput
    unit_28: LPEvaporatorOutput
    unit_29: LPEconomizerOutput

    # Auxiliary unit results
    unit_da: DeaeratorOutput    # Deaerator
    unit_hp_bfp: BFPOutput      # HP BFP
    unit_ip_bfp: BFPOutput      # IP BFP

    # Module-level KPIs
    Q_total: float      # Total HRSG heat duty, kW
    T_stack: float      # Stack temperature, °C
    W_bfp_total: float  # Total BFP power, kW


@dataclass
class HRSGParams:
    """M2 HRSG design parameters."""

    P_HP: float = 16.65         # HP steam pressure, MPa
    P_IP: float = 2.482         # IP steam pressure, MPa
    P_LP: float = 0.655         # LP steam pressure, MPa
    T_is01: float = 565.6       # HP steam outlet temp, °C
    T_is04: float = 568.3       # IP steam outlet temp, °C
    T_24: float = 565.6         # Reheater outlet temp, °C
    T_16: float = 106.0         # Stack gas temp, °C
    T_lp_fw: float = 149.0      # LP feedwater inlet temp, °C
    PTD_HP: float = 10.0        # HP evap pinch, °C
    PTD_IP: float = 10.0        # IP evap pinch, °C
    m_dot_hp: float = 392_884.0 # HP steam flow, kg/hr
    m_dot_ip: float = 77_895.0  # IP steam flow, kg/hr
    m_dot_lp: float = 42_272.0  # LP steam flow, kg/hr (= 93,200 lb/hr per NETL HMB Exhibit 5-11)
    dP_rh_st: float = 0.067     # Reheater steam-side ΔP, MPa
    # ↑ 2.7 % of cold-reheat P (typical industrial reheater range 2-5 %).
    # Earlier 0.310 MPa (12.5 %) was too aggressive; NETL HMB Exhibit 5-11
    # shows cold reheat 360 psia → hot reheat ~360 psia (effectively
    # isobaric at HMB resolution). Setting 0.067 keeps a small physical
    # ΔP while bringing IS-03 P to ~2.42 MPa (within 3 % of NETL's 2.48).
    eta_bfp: float = 0.80       # BFP isentropic efficiency


def hrsg_solve(
    s7: Stream,
    s_is02: Stream,
    s_is06: Stream,
    params: HRSGParams | None = None,
) -> HRSGOutput:
    """Solve the HRSG module sequentially (flue gas direction).

    Args:
        s7: GT exhaust gas — from M1.
        s_is02: Cold Reheat steam — secondary tear stream from M3.
        s_is06: Condensate — primary tear stream from M4.
        params: HRSG design parameters. None → NETL defaults.

    Returns:
        HRSGOutput with all module boundary streams and per-unit results.
    """
    if params is None:
        params = HRSGParams()
    p = params

    # Auxiliary: Deaerator → determines feedwater temperature
    out_da = deaerator(P_LP=p.P_LP)
    T_da = out_da.T_da  # ~162 C at 0.655 MPa

    # Auxiliary: HP BFP (DA → HP drum pressure)
    out_hp_bfp = bfp(T_in=T_da, P_in=p.P_LP, P_out=p.P_HP,
                     m_dot=p.m_dot_hp, eta_bfp=p.eta_bfp)
    T_17 = out_hp_bfp.s_out.T  # HP feedwater inlet temperature

    # Auxiliary: IP BFP (DA → IP drum pressure)
    out_ip_bfp = bfp(T_in=T_da, P_in=p.P_LP, P_out=p.P_IP,
                     m_dot=p.m_dot_ip, eta_bfp=p.eta_bfp)
    T_20 = out_ip_bfp.s_out.T  # IP feedwater inlet temperature

    # Unit 2-1: HP Superheater
    out_21 = hp_superheater(s7, p.m_dot_hp, P_HP=p.P_HP, T_is01=p.T_is01)

    # Unit 2-4: Reheater
    out_24 = reheater(out_21.s8, s_is02, T_24=p.T_24, dP_st=p.dP_rh_st)

    # Unit 2-2: HP Evaporator
    out_22 = hp_evaporator(out_24.s9, p.m_dot_hp, P_HP=p.P_HP, PTD_HP=p.PTD_HP)

    # Unit 2-5: IP Superheater
    out_25 = ip_superheater(out_22.s10, p.m_dot_ip, P_IP=p.P_IP, T_is04=p.T_is04)

    # Node 2-4M: IP Mixing Node (after Unit 2-5)
    out_24m = ip_mixing_node(out_24.s24, out_25.s_is04)

    # Unit 2-3: HP Economizer (T_17 from HP BFP outlet)
    out_23 = hp_economizer(out_25.s11, out_22.s18, p.m_dot_hp,
                           T_17=T_17, P_HP=p.P_HP)

    # Unit 2-6: IP Evaporator
    out_26 = ip_evaporator(out_23.s12, p.m_dot_ip, P_IP=p.P_IP, PTD_IP=p.PTD_IP)

    # Unit 2-7: IP Economizer (T_20 from IP BFP outlet)
    out_27 = ip_economizer(out_26.s13, out_26.s21, p.m_dot_ip,
                           T_20=T_20, P_IP=p.P_IP)

    # Unit 2-8: LP Evaporator
    out_28 = lp_evaporator(out_27.s14, p.m_dot_lp, P_LP=p.P_LP,
                           T_lp_fw=p.T_lp_fw)

    # Unit 2-9: LP Economizer
    out_29 = lp_economizer(out_28.s15, s_is06, T_16=p.T_16, P_eco=p.P_LP)

    # Module-level KPIs
    Q_total = (out_21.Q_dot + out_24.Q_dot + out_22.Q_dot + out_25.Q_dot
               + out_23.Q_dot + out_26.Q_dot + out_27.Q_dot + out_28.Q_dot
               + out_29.Q_dot)
    W_bfp_total = out_hp_bfp.W_bfp + out_ip_bfp.W_bfp

    return HRSGOutput(
        s_is01=out_21.s_is01,
        s_is03=out_24m.s_is03,
        s_is05=out_28.s_is05,
        s16=out_29.s16,
        s23=out_29.s23,
        unit_21=out_21,
        unit_24=out_24,
        node_24m=out_24m,
        unit_22=out_22,
        unit_25=out_25,
        unit_23=out_23,
        unit_26=out_26,
        unit_27=out_27,
        unit_28=out_28,
        unit_29=out_29,
        unit_da=out_da,
        unit_hp_bfp=out_hp_bfp,
        unit_ip_bfp=out_ip_bfp,
        Q_total=Q_total,
        T_stack=out_29.s16.T,
        W_bfp_total=W_bfp_total,
    )

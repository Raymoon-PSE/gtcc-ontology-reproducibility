"""M3 ST module solver -- sequential calculation of 5 units + 1 mixing node.

Reference: ST_Module_Math_Model v1.0.

Calculation order:
    3-1 HP Turb -> 3-2 CRH -> 3-3 IP Turb -> Node 3-M -> 3-4 LP Turb -> 3-5 ST Gen

Includes eta back-calculation from NETL reference values (spec section 4).
"""

from dataclasses import dataclass

from scipy.optimize import brentq

from eklm.vdt.models.m3_st.hp_turbine import HPTurbineOutput, hp_turbine
from eklm.vdt.models.m3_st.crh_line import CRHLineOutput, crh_line
from eklm.vdt.models.m3_st.ip_turbine import IPTurbineOutput, ip_turbine
from eklm.vdt.models.m3_st.lp_mixing_node import LPMixingNodeOutput, lp_mixing_node
from eklm.vdt.models.m3_st.lp_turbine import LPTurbineOutput, lp_turbine
from eklm.vdt.models.m3_st.st_generator import st_generator
from eklm.vdt.data.properties import h_from_PS_water, h_water, s_water
from eklm.vdt.data.streams import Stream


@dataclass
class STOutput:
    """M3 ST module outputs."""

    # Module boundary outputs
    s_is02: Stream      # Cold Reheat -> M2 HRSG (secondary tear stream)
    s28: Stream         # ST exhaust -> M4 Condenser
    W_ST: float         # ST gross electrical output, kWe

    # Per-unit results
    unit_31: HPTurbineOutput
    unit_32: CRHLineOutput
    unit_33: IPTurbineOutput
    node_3m: LPMixingNodeOutput
    unit_34: LPTurbineOutput

    # KPIs
    W_shaft: float      # Total ST shaft power, kW
    W_hpt: float        # HP turbine power, kW
    W_ipt: float        # IP turbine power, kW
    W_lpt: float        # LP turbine power, kW
    x_28: float         # LP exhaust steam quality
    eta_hpt: float      # HP turbine efficiency (back-calc or given)
    eta_ipt: float      # IP turbine efficiency
    eta_lpt: float      # LP turbine efficiency


@dataclass
class STParams:
    """M3 ST design parameters."""

    P_26: float = 0.507         # IP turbine exit / cross-over pressure, MPa
    P_28: float = 0.00677       # Condenser pressure, MPa
    dP_crh: float = 0.0         # CRH pressure drop, MPa
    m_dot_bleed: float = 16_429.0   # HP bleed flow, kg/hr
    eta_stgen: float = 0.984    # ST generator efficiency
    # Turbine efficiencies -- None means back-calculate from NETL
    eta_hpt: float | None = None
    eta_ipt: float | None = None
    eta_lpt: float | None = None


def back_calc_eta_hpt(
    s_is01: Stream,
    P_25: float,
) -> float:
    """Back-calculate HP turbine isentropic efficiency from NETL.

    Uses NETL IS-01 and IS-02 reference values (spec section 4.1).
    """
    # NETL IS-02 (cold reheat): 587.9 °F = 308.8 °C, 360 psia = 2.482 MPa
    # (Exhibit 5-11 HMB; cold reheat header pressure equals IP drum.)
    h_is02 = h_water(308.8, 2.482)
    h_ref = h_from_PS_water(P_25, s_is01.s)
    return (s_is01.h - h_is02) / (s_is01.h - h_ref)


def back_calc_eta_common(
    s_is01: Stream,
    s_is03: Stream,
    s_is05: Stream,
    params: 'STParams',
    eta_hpt: float,
    W_ST_target: float = 202_500.0,
) -> float:
    """Back-calculate common IP/LP turbine efficiency from NETL total power.

    Uses Brent's method (spec section 4.2).
    """
    W_shaft_target = W_ST_target / params.eta_stgen

    # HP turbine power (fixed by eta_hpt)
    P_25 = _p25(s_is03, params)
    out_31 = hp_turbine(s_is01, P_25, eta_hpt, params.m_dot_bleed)
    W_hpt = out_31.W_hpt

    W_iplp_target = W_shaft_target - W_hpt

    def residual(eta_common: float) -> float:
        out_33 = ip_turbine(s_is03, params.P_26, eta_common)
        mn_out = lp_mixing_node(out_33.s26, s_is05)
        out_34 = lp_turbine(mn_out.s27, params.P_28, eta_common)
        return out_33.W_ipt + out_34.W_lpt - W_iplp_target

    eta_common, r = brentq(residual, 0.50, 0.99, full_output=True)
    return eta_common


def _p25(s_is03: Stream, params: 'STParams') -> float:
    """HP turbine exit pressure = IS-02 tear pressure + CRH dP.

    In the SM loop, IS-02 pressure comes from the tear stream.
    For back-calc, use NETL IS-02 P = 2.482 MPa (= 360 psia, matches
    NETL Case 13 HMB Exhibit 5-11 Cold Reheat header).
    """
    # Use IS-03 inlet pressure context: P_25 is set so that after CRH dP,
    # we get the IS-02 pressure. For Phase 1 with dP_crh=0, P_25 = P_IS02.
    return 2.482 + params.dP_crh


def st_solve(
    s_is01: Stream,
    s_is03: Stream,
    s_is05: Stream,
    params: STParams | None = None,
) -> STOutput:
    """Solve the ST module sequentially.

    Args:
        s_is01: HP Main Steam from M2.
        s_is03: Hot Reheat Steam from M2.
        s_is05: LP Steam from M2.
        params: ST design parameters. None -> NETL defaults with back-calc.

    Returns:
        STOutput with all module boundary streams and per-unit results.
    """
    if params is None:
        params = STParams()

    # HP turbine exit pressure
    P_25 = _p25(s_is03, params)

    # Back-calculate efficiencies if not provided
    eta_hpt = params.eta_hpt
    if eta_hpt is None:
        eta_hpt = back_calc_eta_hpt(s_is01, P_25)

    eta_ipt = params.eta_ipt
    eta_lpt = params.eta_lpt
    if eta_ipt is None or eta_lpt is None:
        eta_common = back_calc_eta_common(
            s_is01, s_is03, s_is05, params, eta_hpt,
        )
        if eta_ipt is None:
            eta_ipt = eta_common
        if eta_lpt is None:
            eta_lpt = eta_common

    # Unit 3-1: HP Turbine
    out_31 = hp_turbine(s_is01, P_25, eta_hpt, params.m_dot_bleed)

    # Unit 3-2: CRH Line
    out_32 = crh_line(out_31.s25, params.dP_crh)

    # Unit 3-3: IP Turbine
    out_33 = ip_turbine(s_is03, params.P_26, eta_ipt)

    # Node 3-M: LP Inlet Mixing
    out_3m = lp_mixing_node(out_33.s26, s_is05)

    # Unit 3-4: LP Turbine
    out_34 = lp_turbine(out_3m.s27, params.P_28, eta_lpt)

    # Unit 3-5: ST Generator
    W_shaft, W_ST = st_generator(
        out_31.W_hpt, out_33.W_ipt, out_34.W_lpt, params.eta_stgen,
    )

    return STOutput(
        s_is02=out_32.s_is02,
        s28=out_34.s28,
        W_ST=W_ST,
        unit_31=out_31,
        unit_32=out_32,
        unit_33=out_33,
        node_3m=out_3m,
        unit_34=out_34,
        W_shaft=W_shaft,
        W_hpt=out_31.W_hpt,
        W_ipt=out_33.W_ipt,
        W_lpt=out_34.W_lpt,
        x_28=out_34.x_28,
        eta_hpt=eta_hpt,
        eta_ipt=eta_ipt,
        eta_lpt=eta_lpt,
    )

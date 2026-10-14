"""GTCC plant-level convergence loop (Sequential Modular + Wegstein).

Reference: GTCC_HRSG_Convergence_Strategy.md.

Loop structure:
    M1 GT (once, outside loop -- no tear stream dependency)
    Loop:
        M2 HRSG(s7, IS-02_tear, IS-06_tear) -> IS-01, IS-03, IS-05
        M3 ST(IS-01, IS-03, IS-05) -> IS-02_new, S28
        M4 Condenser(S28) -> IS-06_new
        Check convergence on IS-06 and IS-02
        Wegstein update

Tear streams: IS-06 (primary), IS-02 (secondary).
Convergence variables per tear: [T, P, m_dot].
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from eklm.vdt.models.m2_hrsg.hrsg_solver import hrsg_solve, HRSGParams, HRSGOutput
from eklm.vdt.models.m3_st.st_solver import st_solve, STParams, STOutput
from eklm.vdt.models.m4_condenser.condenser_solver import (
    condenser_solve, CondenserParams, CondenserOutput,
)
from eklm.vdt.data.properties import h_water, s_water
from eklm.vdt.data.streams import Stream


# NETL Case 13 total auxiliary load (Exhibit 5-7), fixed at the cycle
# bookkeeping level. Kept in sync with eklm.vdt.dynamic.plant_dyn.W_aux.
# Items (kW): Condensate Pumps 170, BFP 2,720, Circulating Water Pump
# 2,300, Ground Water Pumps 210, Cooling Tower Fans 1,190, SCR 10,
# GT auxiliaries 700, ST auxiliaries 100, Misc BOP 500, Transformer
# Losses 1,720. Total 9,620 kW. Steady solver subtracts this in bulk
# (model-computed W_BFP / W_CWS / W_CP are reported separately for
# transparency but not double-counted).
_W_AUX_NETL_TOTAL: float = 9_620.0  # kW


@dataclass
class GTCCResult:
    """Plant-level GTCC converged result."""

    converged: bool
    iterations: int
    residual: float

    # Module outputs
    m2: HRSGOutput
    m3: STOutput
    m4: CondenserOutput

    # M1 GT results (passed through)
    s7: Stream
    W_GT: float

    # Plant-level KPIs
    W_net: float        # Net plant power, kW
    Q_fuel: float       # Fuel heat input (LHV basis), kW
    eta_net: float      # Net plant efficiency (LHV basis)

    # Tear streams (converged values)
    is06: Stream
    is02: Stream

    # Mechanical model operating point (set by gui_adapter after solve)
    operating_point: object | None = field(default=None, repr=False)


def _stream_to_vec(s: Stream) -> np.ndarray:
    return np.array([s.T, s.P, s.m_dot])


def _vec_to_is06(v: np.ndarray) -> Stream:
    T, P, m_dot = float(v[0]), float(v[1]), float(v[2])
    return Stream(T=T, P=P, m_dot=m_dot, w={"H2O": 1.0},
                  h=h_water(T, P), s=s_water(T, P))


def _vec_to_is02(v: np.ndarray) -> Stream:
    T, P, m_dot = float(v[0]), float(v[1]), float(v[2])
    return Stream(T=T, P=P, m_dot=m_dot, w={"H2O": 1.0},
                  h=h_water(T, P), s=s_water(T, P))


def _residual(x_new: np.ndarray, x_old: np.ndarray) -> float:
    """Maximum relative component residual; never mix unlike physical units."""
    # Temperature, pressure and flow have different units/scales. A large
    # kg/h flow must not hide a pressure mismatch in the tear stream.
    return float(np.max(np.abs(x_new-x_old)/np.maximum(np.abs(x_old),1.0)))



def _wegstein_update(
    x_n: np.ndarray,
    f_n: np.ndarray,
    x_prev: np.ndarray | None,
    f_prev: np.ndarray | None,
    q_min: float = -5.0,
    q_max: float = 0.0,
) -> np.ndarray:
    """Wegstein acceleration (element-wise).

    First iteration: direct substitution (x_{n+1} = f(x_n)).
    Subsequent: Wegstein formula with q clipping.
    """
    if x_prev is None or f_prev is None:
        return f_n.copy()

    x_next = np.empty_like(x_n)
    for i in range(len(x_n)):
        dx = x_n[i] - x_prev[i]
        if abs(dx) < 1e-15:
            x_next[i] = f_n[i]
        else:
            q = (f_n[i] - f_prev[i]) / dx
            q = np.clip(q, q_min, q_max)
            if abs(q - 1.0) < 1e-15:
                x_next[i] = f_n[i]
            else:
                x_next[i] = (q * x_n[i] - f_n[i]) / (q - 1.0)
    return x_next


def gtcc_solve(
    s7: Stream,
    W_GT: float,
    Q_fuel: float,
    hrsg_params: HRSGParams | None = None,
    st_params: STParams | None = None,
    cond_params: CondenserParams | None = None,
    tol: float = 1e-4,
    max_iter: int = 50,
    *,
    auxiliary_power_kW: float = _W_AUX_NETL_TOTAL,
) -> GTCCResult:
    """Run the GTCC plant-level SM + Wegstein convergence loop.

    Args:
        s7: GT exhaust from M1 (computed once outside loop).
        W_GT: GT gross electrical output, kW.
        Q_fuel: Fuel heat input (LHV basis), kW.
        hrsg_params: M2 HRSG parameters.
        st_params: M3 ST parameters.
        cond_params: M4 Condenser parameters.
        tol: Convergence tolerance (relative). Default 1e-4.
        max_iter: Maximum iterations. Default 50.
        auxiliary_power_kW: Total plant auxiliary load on the same basis as W_GT.
            Default is the NETL reference. Specify explicitly for other plants.

    Returns:
        GTCCResult with converged plant-level results.
    """
    if not np.isfinite(auxiliary_power_kW) or auxiliary_power_kW < 0:
        raise ValueError("auxiliary_power_kW must be finite and nonnegative")
    if max_iter < 1:
        raise ValueError("max_iter must be positive")
    if hrsg_params is None:
        hrsg_params = HRSGParams()
    if st_params is None:
        st_params = STParams()
    if cond_params is None:
        cond_params = CondenserParams()

    if hrsg_params.thermal_mode == "linked":
        from dataclasses import replace
        beta=hrsg_params.blowdown_fraction
        if not 0<=beta<.2:raise ValueError("Linked blowdown fraction must be in [0, .2)")
        steam=hrsg_params.m_dot_hp+hrsg_params.m_dot_ip+hrsg_params.m_dot_lp
        cond_params=replace(cond_params,m_dot_ssr=0.,m_dot_gsc=hrsg_params.gland_flow,
                            m_dot_cond_muw=steam*beta/(1-beta))

    # NETL warm start for tear streams
    x_is06 = np.array([38.4, 0.896, 514_240.0])
    x_is02 = np.array([308.8, 2.689, 376_455.0])

    if hrsg_params.thermal_mode == "linked":
        x_is06[2]=steam-st_params.m_dot_bleed+cond_params.m_dot_gsc+cond_params.m_dot_cond_muw
        x_is02[2]=hrsg_params.m_dot_hp-st_params.m_dot_bleed

    x_is06_prev = None
    f_is06_prev = None
    x_is02_prev = None
    f_is02_prev = None

    m2_out = None
    m3_out = None
    m4_out = None

    for it in range(1, max_iter + 1):
        # Build tear stream objects
        is06_tear = _vec_to_is06(x_is06)
        is02_tear = _vec_to_is02(x_is02)

        # M2 HRSG
        m2_out = hrsg_solve(s7, is02_tear, is06_tear, hrsg_params)

        # M3 ST
        m3_out = st_solve(m2_out.s_is01, m2_out.s_is03, m2_out.s_is05, st_params)

        # M4 Condenser
        m4_out = condenser_solve(m3_out.s28, cond_params)

        # New tear stream values
        f_is06 = _stream_to_vec(m4_out.s_is06)
        f_is02 = _stream_to_vec(m3_out.s_is02)

        # Convergence check
        res_is06 = _residual(f_is06, x_is06)
        res_is02 = _residual(f_is02, x_is02)
        res = max(res_is06, res_is02)

        if res < tol:
            # Converged
            W_CWS = m4_out.W_CWS
            W_bfp = m2_out.W_bfp_total
            # Aligned with plant_dyn: subtract NETL Case 13 total aux in bulk.
            # W_BFP / W_CWS / W_cp are reported separately (informational).
            W_net = W_GT + m3_out.W_ST - auxiliary_power_kW
            eta_net = W_net / Q_fuel if Q_fuel > 0 else 0.0

            if hrsg_params.thermal_mode == "linked":
                from .water_cycle_audit import close_water_cycle
                close_water_cycle(m2_out,m3_out,m4_out,cond_params)

            return GTCCResult(
                converged=True, iterations=it, residual=res,
                m2=m2_out, m3=m3_out, m4=m4_out,
                s7=s7, W_GT=W_GT,
                W_net=W_net, Q_fuel=Q_fuel, eta_net=eta_net,
                is06=m4_out.s_is06, is02=m3_out.s_is02,
            )

        # Divergence check
        if res > 1e2:
            raise RuntimeError(
                f"GTCC loop diverged at iteration {it}: residual = {res:.2e}"
            )

        # Wegstein update
        x_is06_new = _wegstein_update(x_is06, f_is06, x_is06_prev, f_is06_prev)
        x_is02_new = _wegstein_update(x_is02, f_is02, x_is02_prev, f_is02_prev)

        x_is06_prev = x_is06.copy()
        f_is06_prev = f_is06.copy()
        x_is02_prev = x_is02.copy()
        f_is02_prev = f_is02.copy()

        x_is06 = x_is06_new
        x_is02 = x_is02_new

    # Did not converge
    W_CWS = m4_out.W_CWS
    W_bfp = m2_out.W_bfp_total
    W_net = W_GT + m3_out.W_ST - auxiliary_power_kW
    eta_net = W_net / Q_fuel if Q_fuel > 0 else 0.0

    return GTCCResult(
        converged=False, iterations=max_iter, residual=res,
        m2=m2_out, m3=m3_out, m4=m4_out,
        s7=s7, W_GT=W_GT,
        W_net=W_net, Q_fuel=Q_fuel, eta_net=eta_net,
        is06=m4_out.s_is06, is02=m3_out.s_is02,
    )

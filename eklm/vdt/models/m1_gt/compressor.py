"""Unit 1-2: Compressor.

Reference:
    - Lump model (default, n_stages=1): GT_Module_Math_Model §2 (Unit 1-2).
    - Stage-resolved (n_stages>1):       Unit_1-2_Compressor_StageResolved
      v1_0 supplementary math model.

Backward compatibility:
    The 3-tuple return ``(s3, s_bleed, W_comp)`` is preserved when
    ``return_stages=False`` (default). Existing call sites are unaffected.
"""

from dataclasses import dataclass, field
from typing import Optional, Union

from eklm.vdt.data.properties import h_air, h_from_PS_air, s_air, T_from_PH_air
from eklm.vdt.data.streams import Stream

# Reference state for corrected mass flow (ISO standard ambient).
_T_REF_K = 288.15
_P_REF_MPA = 0.101325

# Default map / surge parameters (see math model §3).
_ALPHA_MAP_DEFAULT = 0.6
_KAPPA_ETA_DEFAULT = 0.5
_SM_D_DEFAULT = 0.18
_C_S_DEFAULT = 0.4


@dataclass
class CompressorDiagnostics:
    """Per-stage states and 1D-map post-processing.

    Populated only when ``return_stages=True``. ``stage_states[i]`` is the
    state at the exit of stage ``i+1`` (so ``stage_states[-1]`` matches the
    pre-bleed S^(3) state).
    """
    n_stages: int
    PR_stages: list[float]
    eta_stages: list[float]
    stage_states: list[Stream] = field(default_factory=list)
    stage_powers: list[float] = field(default_factory=list)  # kW
    eta_overall: float = 0.0  # back-calc: (h_ref_total - h2) / (hN - h2)
    m_dot_corr: float = 0.0   # kg/hr at ISO ref
    surge_margin: float = 0.0  # fraction


def _resolve_stages(
    PR: float,
    eta: float,
    n_stages: int,
    PR_stages: Optional[list[float]],
    eta_stages: Optional[list[float]],
) -> tuple[list[float], list[float]]:
    """Build the per-stage PR and η vectors per math-model §4.2."""
    if n_stages < 1:
        raise ValueError(f"n_stages must be >= 1, got {n_stages}")

    if PR_stages is None:
        PR_each = PR ** (1.0 / n_stages)
        PR_list = [PR_each] * n_stages
    else:
        if len(PR_stages) != n_stages:
            raise ValueError(
                f"PR_stages length {len(PR_stages)} != n_stages {n_stages}"
            )
        prod = 1.0
        for p in PR_stages:
            prod *= p
        rel_err = abs(prod - PR) / PR
        if rel_err > 0.05:
            raise ValueError(
                f"Π PR_i = {prod:.4f} mismatches PR^(comp) = {PR:.4f} "
                f"by {rel_err*100:.2f}% (>5%)"
            )
        PR_list = list(PR_stages)

    if eta_stages is None:
        eta_list = [eta] * n_stages
    else:
        if len(eta_stages) != n_stages:
            raise ValueError(
                f"eta_stages length {len(eta_stages)} != n_stages {n_stages}"
            )
        eta_list = list(eta_stages)

    return PR_list, eta_list


def _map_post(
    s2: Stream,
    PR_total: float,
    m_dot_corr_d: Optional[float],
    alpha_map: float,
    kappa_eta: float,
    SM_d: float,
    c_s: float,
) -> tuple[float, float]:
    """Compute corrected flow + surge margin (math model §4.4–§4.5)."""
    T2_K = s2.T + 273.15
    m_dot_corr = s2.m_dot * (T2_K / _T_REF_K) ** 0.5 / (s2.P / _P_REF_MPA)
    m_dot_corr_d = m_dot_corr_d if m_dot_corr_d is not None else m_dot_corr

    PR_surge = PR_total * (1.0 + SM_d) * (m_dot_corr / m_dot_corr_d) ** (-c_s)
    SM = PR_surge / PR_total - 1.0

    # alpha_map and kappa_eta are reserved for future PR/η deviation reporting;
    # they parameterise the map's curvature but do not feed back into the
    # design-point thermodynamic solve (see math model §4.4 N-3).
    _ = (alpha_map, kappa_eta)

    return m_dot_corr, SM


def compressor(
    s2: Stream,
    PR: float,
    eta: float,
    f_bleed: float = 0.0,
    n_stages: int = 1,
    PR_stages: Optional[list[float]] = None,
    eta_stages: Optional[list[float]] = None,
    return_stages: bool = False,
    m_dot_corr_d: Optional[float] = None,
    alpha_map: float = _ALPHA_MAP_DEFAULT,
    kappa_eta: float = _KAPPA_ETA_DEFAULT,
    SM_d: float = _SM_D_DEFAULT,
    c_s: float = _C_S_DEFAULT,
) -> Union[
    tuple[Stream, Optional[Stream], float],
    tuple[Stream, Optional[Stream], float, CompressorDiagnostics],
]:
    """Compress inlet air using stage-resolved isentropic-efficiency loop.

    Args:
        s2: Conditioned air from Unit 1-1 (S^(2)).
        PR: Total compressor pressure ratio PR^(comp). Must be > 1.
        eta: Stage isentropic efficiency η^(comp), in (0, 1]. When
            n_stages=1 this is the lump efficiency.
        f_bleed: Bleed air mass fraction in [0, 1). Default 0.
        n_stages: Number of stages N >= 1. Default 1 (lump model).
        PR_stages: Optional length-N PR vector. If None, uniform
            PR_i = PR^(1/N). If given, must satisfy Π PR_i ≈ PR within 5%.
        eta_stages: Optional length-N η vector. If None, uniform η_i = eta.
        return_stages: If True, return a 4-tuple including
            CompressorDiagnostics. Default False (3-tuple, lump-compatible).
        m_dot_corr_d, alpha_map, kappa_eta, SM_d, c_s: Map parameters per
            math model §4.4–§4.5. Defaults reproduce the design point as
            self-consistent.

    Returns:
        ``return_stages=False`` (default):
            (s3, s_bleed, W_comp)  — backward compatible 3-tuple.
        ``return_stages=True``:
            (s3, s_bleed, W_comp, diag) — diag is CompressorDiagnostics.

    Math model §6 calculation sequence:
        Step 0: distribute {PR_i}, {η_i}.
        Step 1: stage loop (P, isentropic-ref, h, T, s) for i=1..N.
        Step 2: mass split + total power.
        Step 3: corrected flow + surge margin (diagnostic only).
    """
    PR_list, eta_list = _resolve_stages(PR, eta, n_stages, PR_stages, eta_stages)

    # Step 1: stage loop. State i-1 → i.
    state = s2
    h2_inlet = h_air(s2.T, s2.P, s2.w)
    if state.h is None:
        state = Stream(T=state.T, P=state.P, m_dot=state.m_dot, w=state.w,
                       h=h2_inlet, s=s_air(state.T, state.P, state.w))

    stage_states: list[Stream] = []
    stage_powers: list[float] = []

    for i in range(n_stages):
        P_i = PR_list[i] * state.P
        s_ref = state.s
        h_ref = h_from_PS_air(P_i, s_ref, state.w)
        h_i = state.h + (h_ref - state.h) / eta_list[i]
        T_i = T_from_PH_air(P_i, h_i, state.w)
        s_i = s_air(T_i, P_i, state.w)

        # ṁ [kg/hr] × Δh [J/kg] / 3.6e6 → kW
        W_i = s2.m_dot * (h_i - state.h) / 3.6e6
        stage_powers.append(W_i)

        next_state = Stream(
            T=T_i, P=P_i, m_dot=s2.m_dot, w=state.w, h=h_i, s=s_i,
        )
        stage_states.append(next_state)
        state = next_state

    # Step 2: mass split + total power.
    m_dot_3 = s2.m_dot * (1.0 - f_bleed)
    m_dot_bleed = s2.m_dot * f_bleed
    W_comp = s2.m_dot * (state.h - h2_inlet) / 3.6e6  # kW

    s3_stream = Stream(
        T=state.T, P=state.P, m_dot=m_dot_3, w=state.w,
        h=state.h, s=state.s,
    )
    if f_bleed == 0.0:
        s_bleed_stream = None
    else:
        s_bleed_stream = Stream(
            T=state.T, P=state.P, m_dot=m_dot_bleed, w=state.w,
            h=state.h, s=state.s,
        )

    if not return_stages:
        return s3_stream, s_bleed_stream, W_comp

    # Step 3: map post-processing.
    m_dot_corr, SM = _map_post(
        s2, PR, m_dot_corr_d, alpha_map, kappa_eta, SM_d, c_s,
    )

    # Overall isentropic efficiency:
    #   η_overall = (h_ref_overall - h2) / (h_actual_outlet - h2)
    s_ref_overall = s_air(s2.T, s2.P, s2.w)
    h_ref_overall = h_from_PS_air(state.P, s_ref_overall, s2.w)
    delta_actual = state.h - h2_inlet
    eta_overall = (h_ref_overall - h2_inlet) / delta_actual if delta_actual > 0 else 0.0

    diag = CompressorDiagnostics(
        n_stages=n_stages,
        PR_stages=PR_list,
        eta_stages=eta_list,
        stage_states=stage_states,
        stage_powers=stage_powers,
        eta_overall=eta_overall,
        m_dot_corr=m_dot_corr,
        surge_margin=SM,
    )

    return s3_stream, s_bleed_stream, W_comp, diag


def compressor_residuals(
    diag: CompressorDiagnostics,
    reference: Optional[CompressorDiagnostics] = None,
    stages: tuple[int, ...] = (3, 6, 9),
    SM_d: float = _SM_D_DEFAULT,
) -> dict[str, float]:
    """Build Tier-2 FDI residuals from a stage-resolved compressor diagnostic.

    Channel keys match osim.agents.tier2.fault_diagnosis._DEFAULT_THRESHOLDS:

        T_stage_i : T^(2.i) deviation from reference, in K (°C delta).
                    Positive = stage hotter than expected (fouling signature).
        SM_loss   : max(0, SM_d - SM). Positive = surge margin degraded.

    Args:
        diag: Current (measured / degraded) compressor diagnostics.
        reference: Nominal-model diagnostics. If None, T_stage residuals
            are zero (only SM_loss is computed).
        stages: 1-indexed stage numbers to monitor. Each must satisfy
            1 <= i <= diag.n_stages and (if reference given) the same for
            reference.n_stages.
        SM_d: Design surge margin used as the reference for SM_loss.
            Defaults to the math-model §3 default (0.18).

    Returns:
        dict[channel] -> residual. Caller passes this to
        ``FaultDiagnosisAgent.step(t, residuals)`` (and may merge with the
        existing 28-state residuals).
    """
    out: dict[str, float] = {}

    # Per-stage temperature residuals (only when reference provided).
    if reference is not None:
        for i in stages:
            if not (1 <= i <= diag.n_stages):
                continue
            if not (1 <= i <= reference.n_stages):
                continue
            T_meas = diag.stage_states[i - 1].T
            T_ref = reference.stage_states[i - 1].T
            out[f"T_stage_{i}"] = T_meas - T_ref

    # Surge margin loss (clamped at 0 — over-margin is harmless).
    out["SM_loss"] = max(0.0, SM_d - diag.surge_margin)

    return out

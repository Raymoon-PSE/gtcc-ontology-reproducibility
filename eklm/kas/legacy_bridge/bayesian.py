"""Bayesian Fault Diagnosis for GTCC plant.

Uses Bayesian-style normalization of geometric-mean symptom scores.
The returned legacy field name `posterior` denotes an uncalibrated normalized
hypothesis score, not a measured or calibrated fault probability.

P(Fault_i | obs) = P(obs | Fault_i) * P(Fault_i) / P(obs)
"""

from dataclasses import dataclass, field
import math

import numpy as np

from eklm.vdt.analysis.gtcc_loop import GTCCResult


@dataclass
class Fault:
    """A fault type with prior and symptom signatures."""

    id: str
    name: str
    unit: str
    description: str
    prior: float
    symptoms: dict[str, dict]  # {obs_key: {"direction": "down"/"up", "magnitude": float, "likelihood": float}}


@dataclass
class DiagnosisResult:
    """Result of Bayesian diagnosis."""

    fault_id: str
    fault_name: str
    prior: float
    likelihood: float
    posterior: float
    recommendation: str


# ── Fault Library ────────────────────────────────────────────────────────

FAULT_LIBRARY = [
    Fault(
        id="F-01", name="Compressor fouling", unit="M1 1-2",
        description="Intake filter degradation, blade contamination",
        prior=0.25,
        symptoms={
            "eta_comp":  {"direction": "down", "threshold": 0.02, "likelihood": 0.90},
            "T_stack":   {"direction": "up",   "threshold": 5.0,  "likelihood": 0.75},
            "W_net_pct": {"direction": "down", "threshold": 2.0,  "likelihood": 0.85},
            "mech_comp_surge_margin_pct": {"direction": "down", "threshold": 2.0, "likelihood": 0.80},
        },
    ),
    Fault(
        id="F-02", name="GT blade erosion", unit="M1 1-5",
        description="Hot corrosion, TBC spallation",
        prior=0.10,
        symptoms={
            "eta_turb":  {"direction": "down", "threshold": 0.02, "likelihood": 0.90},
            "W_GT_pct":  {"direction": "down", "threshold": 3.0,  "likelihood": 0.85},
            "T_stack":   {"direction": "up",   "threshold": 3.0,  "likelihood": 0.60},
        },
    ),
    Fault(
        id="F-03", name="Combustor degradation", unit="M1 1-4",
        description="Combustion efficiency drop, flame instability",
        prior=0.08,
        symptoms={
            "T_stack":   {"direction": "up",   "threshold": 10.0, "likelihood": 0.85},
            "W_net_pct": {"direction": "down", "threshold": 1.5,  "likelihood": 0.70},
        },
    ),
    Fault(
        id="F-04", name="HRSG tube fouling", unit="M2 2-2/2-6",
        description="Gas-side contamination, pinch degradation",
        prior=0.20,
        symptoms={
            "PTD_HP":    {"direction": "down", "threshold": 3.0,  "likelihood": 0.90},
            "T_stack":   {"direction": "up",   "threshold": 8.0,  "likelihood": 0.80},
            "W_ST_pct":  {"direction": "down", "threshold": 2.0,  "likelihood": 0.70},
        },
    ),
    Fault(
        id="F-05", name="ST blade erosion", unit="M3 3-4",
        description="LP wet steam erosion",
        prior=0.05,
        symptoms={
            "W_ST_pct":  {"direction": "down", "threshold": 3.0,  "likelihood": 0.85},
            "x_28":      {"direction": "down", "threshold": 0.02, "likelihood": 0.70},
        },
    ),
    Fault(
        id="F-06", name="Condenser fouling", unit="M4 4-1",
        description="Tube scale, CW quality degradation",
        prior=0.15,
        symptoms={
            "P_cond":    {"direction": "up",   "threshold": 0.001, "likelihood": 0.85},
            "W_net_pct": {"direction": "down", "threshold": 1.0,   "likelihood": 0.60},
        },
    ),
    Fault(
        id="F-07", name="CW system degradation", unit="M4 4-3/4-4",
        description="CT fill degradation, CWP wear",
        prior=0.10,
        symptoms={
            "P_cond":    {"direction": "up",   "threshold": 0.0005, "likelihood": 0.75},
            "T_stack":   {"direction": "up",   "threshold": 2.0,    "likelihood": 0.40},
        },
    ),
    Fault(
        id="F-08", name="Sensor drift", unit="All",
        description="Temperature/pressure sensor calibration deviation",
        prior=0.07,
        symptoms={
            # Sensor drift: single anomalous reading, others normal
            # Low likelihood for all systematic symptoms
            "W_net_pct": {"direction": "down", "threshold": 0.5, "likelihood": 0.30},
        },
    ),
]

# Historical mixed reference, retained only for replay of archived results.
LEGACY_DESIGN_REF = {
    "eta_comp": 0.845,
    "eta_turb": 0.876,
    "W_GT": 362_200,
    "W_ST": 202_500,
    "W_net": 581_312,
    "T_stack": 106.0,
    "PTD_HP": 10.0,
    "P_cond": 0.00677,
    "x_28": 0.919,
    "mech_comp_surge_margin_pct": 15.0,
}

# Fixed nominal EKLM reference for revised diagnostic evaluation.
# This is a simulation baseline, not measured healthy-plant data.
DESIGN_REF = {'eta_comp': 0.845, 'eta_turb': 0.876, 'W_GT': 367724.0803469602, 'W_ST': 202500.0, 'W_net': 560604.0803469602, 'T_stack': 106.0, 'PTD_HP': 10.0, 'P_cond': 0.00677, 'x_28': 0.9280155434338059, 'mech_comp_surge_margin_pct': 15.0}

RECOMMENDATIONS = {
    "F-01": "Compressor borescope inspection recommended. Check intake filter dP.",
    "F-02": "GT hot gas path inspection. Check TBC condition and blade profile.",
    "F-03": "Combustion tuning required. Check fuel nozzle wear and flame monitor.",
    "F-04": "HRSG gas-side cleaning (soot blowing). Check economizer fin condition.",
    "F-05": "ST LP section inspection. Check last-stage blade erosion pattern.",
    "F-06": "Condenser tube cleaning. Check CW chemistry and biofouling.",
    "F-07": "CT fill inspection. Check CWP vibration and performance curve.",
    "F-08": "Sensor calibration check. Compare redundant instruments.",
}


def _extract_observations(result: GTCCResult, reference: dict | None = None) -> dict[str, float]:
    """Extract observation values from simulation result."""
    ref = {**DESIGN_REF, **(reference or {})}
    obs = {
        "eta_comp": 0.845,  # Not directly in GTCCResult; use sidebar param
        "eta_turb": 0.876,
        "W_GT": result.W_GT,
        "W_ST": result.m3.W_ST,
        "W_net": result.W_net,
        "T_stack": result.m2.T_stack,
        "PTD_HP": result.m2.unit_22.PTD,
        "P_cond": result.m4.s_is06_hw.P,  # Hotwell, before condensate pump
        "x_28": result.m3.x_28,
        # Derived percentage deviations
        "W_GT_pct": (result.W_GT - ref["W_GT"]) / ref["W_GT"] * 100,
        "W_ST_pct": (result.m3.W_ST - ref["W_ST"]) / ref["W_ST"] * 100,
        "W_net_pct": (result.W_net - ref["W_net"]) / ref["W_net"] * 100,
    }
    return obs


THRESHOLD_ABS_TOL = 1e-10
THRESHOLD_REL_TOL = 1e-12


def threshold_exceeded(deviation: float, threshold: float, direction: str) -> bool:
    """Strict exceedance; roundoff-close equality is a non-match.

    Tolerances are numerical guards in each channel's native units, not
    uncertainty bounds or fitted engineering alarm margins.
    """
    signed = -deviation if direction == 'down' else deviation
    return signed > threshold and not math.isclose(
        signed, threshold, rel_tol=THRESHOLD_REL_TOL, abs_tol=THRESHOLD_ABS_TOL)


def _compute_likelihood(fault: Fault, obs: dict[str, float], reference: dict | None = None) -> float:
    """Compute an uncalibrated symptom match score."""
    ref = {**DESIGN_REF, **(reference or {})}
    if not fault.symptoms:
        return 0.1  # minimal likelihood for faults with no symptoms defined

    match_scores = []
    for obs_key, symptom in fault.symptoms.items():
        if obs_key not in obs:
            continue

        value = obs[obs_key]
        direction = symptom["direction"]
        threshold = symptom["threshold"]
        max_likelihood = symptom["likelihood"]

        # For percentage-based keys (W_GT_pct etc), value is already a deviation
        # But mech_ keys are absolute values, not deviations
        if obs_key.endswith("_pct") and not obs_key.startswith("mech_"):
            deviation = value  # already percentage
        elif obs_key in ref:
            deviation = value - ref[obs_key]
        else:
            deviation = 0

        # Check if deviation matches expected direction
        if direction == "down" and threshold_exceeded(deviation, threshold, direction):
            # Matches: stronger deviation → higher likelihood
            strength = min(abs(deviation) / threshold, 3.0) / 3.0
            match_scores.append(max_likelihood * (0.5 + 0.5 * strength))
        elif direction == "up" and threshold_exceeded(deviation, threshold, direction):
            strength = min(abs(deviation) / threshold, 3.0) / 3.0
            match_scores.append(max_likelihood * (0.5 + 0.5 * strength))
        else:
            # No match: low but non-zero
            match_scores.append(0.1)

    if not match_scores:
        return 0.1

    # Combined likelihood: geometric mean of individual matches
    return float(np.prod(match_scores) ** (1.0 / len(match_scores)))


def diagnose_bayesian(
    result: GTCCResult,
    params: dict | None = None,
    faults: list[Fault] | None = None,
    *,
    observations: dict[str, float] | None = None,
    reference: dict[str, float] | None = None,
) -> list[DiagnosisResult]:
    """Run Bayesian fault diagnosis.

    Args:
        result: Converged GTCCResult.
        params: Simulation parameters (for eta_comp, eta_turb overrides).
        faults: Fault library. None -> FAULT_LIBRARY.
        observations: Complete observation vector, e.g. read from the runtime RDF graph.
            When supplied, params must be omitted.

    Returns:
        List of DiagnosisResult sorted by posterior (highest first).
    """
    if reference is not None:
        if not all(np.isfinite(v) for v in reference.values()):
            raise ValueError("Non-finite diagnostic reference")
        if any(reference.get(k, DESIGN_REF[k]) <= 0 for k in ("W_GT", "W_ST", "W_net")):
            raise ValueError("Reference powers must be positive")
    if faults is None:
        faults = FAULT_LIBRARY

    if observations is not None and params:
        raise ValueError("Supply either explicit observations or parameter overrides")
    obs = dict(observations) if observations is not None else _extract_observations(result, reference)

    # Override with actual params if available
    if params:
        if "eta_comp" in params:
            obs["eta_comp"] = params["eta_comp"]
        if "eta_turb" in params:
            obs["eta_turb"] = params["eta_turb"]

        # Inject mechanical model evidence (mech_ prefix keys → obs)
        for k, v in params.items():
            if k.startswith("mech_") and isinstance(v, (int, float)):
                obs[k] = v

    # Compute likelihood for each fault
    likelihoods = []
    for f in faults:
        lik = _compute_likelihood(f, obs, reference)
        likelihoods.append(lik)

    # Bayes: posterior proportional to prior * likelihood
    raw_posteriors = [f.prior * lik for f, lik in zip(faults, likelihoods)]
    total = sum(raw_posteriors)
    if total == 0:
        total = 1.0

    results = []
    for f, lik, raw_post in zip(faults, likelihoods, raw_posteriors):
        posterior = raw_post / total
        results.append(DiagnosisResult(
            fault_id=f.id,
            fault_name=f.name,
            prior=f.prior,
            likelihood=lik,
            posterior=posterior,
            recommendation=RECOMMENDATIONS.get(f.id, ""),
        ))

    # Sort by posterior descending
    results.sort(key=lambda r: r.posterior, reverse=True)
    return results

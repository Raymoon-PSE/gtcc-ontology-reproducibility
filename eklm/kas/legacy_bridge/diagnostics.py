"""Fault/Diagnostic rules for GTCC plant.

Evaluates simulation results against engineering thresholds and produces
diagnostic findings. Rules are based on general GTCC engineering practice.

Each rule returns a list of Findings. A Finding can be:
- INFO: normal observation
- WARNING: approaching limits
- FAULT: off-design condition requiring attention
"""

from dataclasses import dataclass
from enum import Enum

from eklm.vdt.analysis.gtcc_loop import GTCCResult


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    FAULT = "FAULT"


@dataclass
class Finding:
    """A diagnostic finding."""

    rule_id: str
    unit: str
    severity: Severity
    message: str
    value: float | None = None
    threshold: float | None = None


def diagnose(result: GTCCResult, mech_results: list | None = None) -> list[Finding]:
    """Run all diagnostic rules on a converged GTCC result.

    Args:
        result: Converged GTCCResult.
        mech_results: Optional list of DeviceResult from mechanical models.

    Returns:
        List of Findings (may be empty if everything is nominal).
    """
    findings = []
    findings.extend(_rule_compressor_eta(result))
    findings.extend(_rule_turbine_eta(result))
    findings.extend(_rule_hrsg_pinch(result))
    findings.extend(_rule_hrsg_ttd(result))
    findings.extend(_rule_stack_temperature(result))
    findings.extend(_rule_steam_quality(result))
    findings.extend(_rule_condenser_ttd(result))
    findings.extend(_rule_power_balance(result))

    if mech_results:
        findings.extend(_rules_mechanical(mech_results))

    return findings


# ── Rule implementations ────────────────────────────────────────────────

def _rule_compressor_eta(r: GTCCResult) -> list[Finding]:
    """R-01: Compressor efficiency degradation."""
    # eta_comp is not stored in GTCCResult directly — skip if not available.
    # This rule will be activated when calibration results are passed.
    return []


def _rule_turbine_eta(r: GTCCResult) -> list[Finding]:
    """R-02: ST turbine efficiency check."""
    findings = []
    for name, eta in [("HP Turbine", r.m3.eta_hpt),
                      ("IP Turbine", r.m3.eta_ipt),
                      ("LP Turbine", r.m3.eta_lpt)]:
        if eta < 0.75:
            findings.append(Finding(
                rule_id="R-02", unit=name, severity=Severity.FAULT,
                message=f"{name} eta = {eta:.3f} < 0.75: severe degradation",
                value=eta, threshold=0.75,
            ))
        elif eta < 0.82:
            findings.append(Finding(
                rule_id="R-02", unit=name, severity=Severity.WARNING,
                message=f"{name} eta = {eta:.3f} < 0.82: possible degradation",
                value=eta, threshold=0.82,
            ))
    return findings


def _rule_hrsg_pinch(r: GTCCResult) -> list[Finding]:
    """R-03: HRSG Evaporator pinch temperature difference."""
    findings = []
    checks = [
        ("HP Evaporator", r.m2.unit_22.PTD, 5.0, 3.0),
        ("LP Evaporator", r.m2.unit_28.PTD, 5.0, 3.0),
    ]
    for name, ptd, warn_thresh, fault_thresh in checks:
        if ptd < fault_thresh:
            findings.append(Finding(
                rule_id="R-03", unit=name, severity=Severity.FAULT,
                message=f"{name} PTD = {ptd:.1f} C < {fault_thresh}: tube fouling or leak risk",
                value=ptd, threshold=fault_thresh,
            ))
        elif ptd < warn_thresh:
            findings.append(Finding(
                rule_id="R-03", unit=name, severity=Severity.WARNING,
                message=f"{name} PTD = {ptd:.1f} C < {warn_thresh}: approaching pinch limit",
                value=ptd, threshold=warn_thresh,
            ))
    return findings


def _rule_hrsg_ttd(r: GTCCResult) -> list[Finding]:
    """R-04: HRSG Superheater/Reheater TTD (temperature cross check)."""
    findings = []
    checks = [
        ("HP Superheater", r.m2.unit_21.TTD_cold),
        ("Reheater", r.m2.unit_24.TTD_cold),
        ("IP Superheater", r.m2.unit_25.TTD_cold),
    ]
    for name, ttd in checks:
        if ttd < 0:
            findings.append(Finding(
                rule_id="R-04", unit=name, severity=Severity.FAULT,
                message=f"{name} TTD_cold = {ttd:.1f} C < 0: TEMPERATURE CROSS",
                value=ttd, threshold=0.0,
            ))
        elif ttd < 10:
            findings.append(Finding(
                rule_id="R-04", unit=name, severity=Severity.WARNING,
                message=f"{name} TTD_cold = {ttd:.1f} C < 10: tight approach",
                value=ttd, threshold=10.0,
            ))
    return findings


def _rule_stack_temperature(r: GTCCResult) -> list[Finding]:
    """R-05: Stack temperature — acid dew point and heat recovery."""
    findings = []
    T_stack = r.m2.T_stack
    if T_stack < 90:
        findings.append(Finding(
            rule_id="R-05", unit="Stack", severity=Severity.FAULT,
            message=f"Stack T = {T_stack:.1f} C < 90: acid dew point corrosion risk",
            value=T_stack, threshold=90.0,
        ))
    elif T_stack > 150:
        findings.append(Finding(
            rule_id="R-05", unit="Stack", severity=Severity.WARNING,
            message=f"Stack T = {T_stack:.1f} C > 150: poor heat recovery",
            value=T_stack, threshold=150.0,
        ))
    return findings


def _rule_steam_quality(r: GTCCResult) -> list[Finding]:
    """R-06: LP turbine exhaust steam quality (blade erosion)."""
    findings = []
    x = r.m3.x_28
    if x >= 0:  # -1 means superheated (no concern)
        if x < 0.86:
            findings.append(Finding(
                rule_id="R-06", unit="LP Turbine", severity=Severity.FAULT,
                message=f"Exhaust quality x = {x:.3f} < 0.86: blade erosion danger",
                value=x, threshold=0.86,
            ))
        elif x < 0.90:
            findings.append(Finding(
                rule_id="R-06", unit="LP Turbine", severity=Severity.WARNING,
                message=f"Exhaust quality x = {x:.3f} < 0.90: approaching erosion limit",
                value=x, threshold=0.90,
            ))
    return findings


def _rule_condenser_ttd(r: GTCCResult) -> list[Finding]:
    """R-07: Condenser CW outlet vs saturation temperature."""
    findings = []
    from eklm.vdt.data.properties import T_sat_water
    T_sat = T_sat_water(0.00677)
    T_cw_out = r.m4.s32.T
    margin = T_sat - T_cw_out
    if margin < 1.0:
        findings.append(Finding(
            rule_id="R-07", unit="Condenser", severity=Severity.FAULT,
            message=f"CW outlet {T_cw_out:.1f} C within {margin:.1f} C of T_sat: "
                    "insufficient cooling capacity",
            value=margin, threshold=1.0,
        ))
    return findings


def _rule_power_balance(r: GTCCResult) -> list[Finding]:
    """R-08: Auxiliary power ratio check."""
    findings = []
    W_gross = r.W_GT + r.m3.W_ST
    W_aux = r.m4.W_CWS + r.m2.W_bfp_total
    aux_ratio = W_aux / W_gross if W_gross > 0 else 0
    if aux_ratio > 0.05:
        findings.append(Finding(
            rule_id="R-08", unit="Plant", severity=Severity.WARNING,
            message=f"Auxiliary power ratio = {aux_ratio*100:.1f}% > 5%: high parasitic load",
            value=aux_ratio, threshold=0.05,
        ))
    return findings


# ── Mechanical diagnostic rules (R-09 ~ R-14) ─────────────────────────

def _rules_mechanical(mech_results: list) -> list[Finding]:
    """Convert mechanical model warnings to diagnostic Findings."""
    findings = []
    for mr in mech_results:
        for w in mr.warnings:
            rule_id = w.split(":")[0].strip() if ":" in w else "R-MEC"
            sev = Severity.FAULT if "FAULT" in w else Severity.WARNING
            findings.append(Finding(
                rule_id=rule_id,
                unit=f"{mr.device_id} ({mr.device_type})",
                severity=sev,
                message=w,
            ))
    return findings

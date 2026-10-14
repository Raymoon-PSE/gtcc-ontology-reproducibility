"""Axial Compressor Mechanical Model — COMP-001 (unit 1-2).

Outputs: surge_margin_pct, efficiency_current, degradation_rate_pct_khr,
         remaining_life_hr

Physics basis:
    - Surge margin: SM = (PR_surge / PR_op - 1) * 100  [Boyce, GT Eng. Handbook]
    - Degradation: Kurz & Brun, ASME GT2001-30314
      delta_eta = -k_deg * (hours / 1000), recoverable + non-recoverable
    - Remaining life: time until eta drops below min threshold (0.80)
"""

from __future__ import annotations

import math

from eklm.vdt.mechanical.base import DeviceResult, HybridModel, PhysicsModel
from eklm.vdt.mechanical.data_package import DeviceDataPackage
from eklm.vdt.mechanical.model_router import register_model
from eklm.vdt.mechanical.operating_point import OperatingPoint

_ETA_MIN = 0.80


def _compute(op: OperatingPoint, pkg: DeviceDataPackage) -> dict:
    PR_op = op.pressure_ratio
    PR_design = pkg.get("pressure_ratio_design", 18.1)
    eta_design = pkg.get("polytropic_efficiency_design", 0.87)
    SM_design = pkg.get("surge_margin_design_pct", 15.0)
    k_deg = pkg.get("k_degradation_per_khr", 0.002)
    hours = op.cumulative_hours

    # Surge margin — surge line PR scales with design margin
    PR_surge = PR_design * (1.0 + SM_design / 100.0)
    surge_margin_pct = (PR_surge / PR_op - 1.0) * 100.0 if PR_op > 0 else 0.0

    # Degradation — efficiency drop over time
    delta_eta = k_deg * (hours / 1000.0)
    eta_current = max(eta_design - delta_eta, _ETA_MIN)
    degradation_rate = k_deg * 100.0  # %/khr

    # Remaining life — hours until eta reaches _ETA_MIN
    eta_margin = eta_current - _ETA_MIN
    remaining_life_hr = (eta_margin / k_deg) * 1000.0 if k_deg > 0 else math.inf

    return {
        "mech_comp_surge_margin_pct": round(surge_margin_pct, 2),
        "mech_comp_efficiency_current": round(eta_current, 5),
        "mech_comp_degradation_rate_pct_khr": round(degradation_rate, 4),
        "mech_comp_remaining_life_hr": round(remaining_life_hr, 0),
    }


def _warnings(outputs: dict) -> list[str]:
    w = []
    sm = outputs["mech_comp_surge_margin_pct"]
    rl = outputs["mech_comp_remaining_life_hr"]
    if sm < 10.0:
        w.append(f"R-09: Compressor surge margin {sm:.1f}% < 10% WARNING")
    if rl < 5000:
        w.append(f"R-09: Compressor remaining life {rl:.0f} hr < 5000 hr WARNING")
    return w


class CompressorPhysicsModel(PhysicsModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        return self._result("ACTIVE", outputs, _warnings(outputs))


class CompressorHybridModel(HybridModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        uncertain = [
            k for k in ["surge_margin_design_pct", "k_degradation_per_khr"]
            if k not in self.package.required_params
        ]
        return self._result("ACTIVE_UNCERTAIN", outputs, _warnings(outputs), uncertain)


register_model("Compressor", CompressorPhysicsModel, CompressorHybridModel)

"""GT Turbine Mechanical Model — EXP-001 (unit 1-5).

Outputs: creep_life_fraction, eoh_consumed, eoh_remaining, blade_temp_C

Physics basis:
    - Larson-Miller creep: LMP = T_K * (C + log10(t_rupture))
      [Viswanathan, Damage Mechanisms & Life Assessment]
    - EOH: base_hours + start_stop * eoh_per_start  [GE TIL]
    - Blade temperature: T_blade = TIT - cooling_eff * (TIT - T_coolant)
"""

from __future__ import annotations

import math

from eklm.vdt.mechanical.base import DeviceResult, HybridModel, PhysicsModel
from eklm.vdt.mechanical.data_package import DeviceDataPackage
from eklm.vdt.mechanical.model_router import register_model
from eklm.vdt.mechanical.operating_point import OperatingPoint


def _compute(op: OperatingPoint, pkg: DeviceDataPackage) -> dict:
    TIT_C = op.TIT_C
    hours = op.cumulative_hours
    starts = op.start_stop_count

    cooling_eff = pkg.get("cooling_effectiveness", 0.60)
    LM_C = pkg.get("larson_miller_C", 20.0)
    LMP_rupture = pkg.get("larson_miller_LMP_rupture", 28500.0)
    eoh_per_start = pkg.get("eoh_per_start", 15.0)
    major_eoh = pkg.get("major_inspection_eoh", 24000.0)
    stress_MPa = pkg.get("design_stress_MPa", 150.0)

    # Blade temperature — coolant approximated as compressor outlet
    T_coolant_C = op.compressor_outlet_T_C
    blade_temp_C = TIT_C - cooling_eff * (TIT_C - T_coolant_C)

    # Larson-Miller creep life at blade temperature
    T_blade_K = blade_temp_C + 273.15
    if T_blade_K > 0 and LMP_rupture > 0:
        log_t = LMP_rupture / T_blade_K - LM_C
        t_rupture_hr = 10.0 ** log_t if log_t < 10 else math.inf
    else:
        t_rupture_hr = math.inf

    creep_life_fraction = hours / t_rupture_hr if t_rupture_hr > 0 else 0.0

    # EOH
    eoh_consumed = hours + starts * eoh_per_start
    eoh_remaining = max(0.0, major_eoh - eoh_consumed)

    return {
        "mech_gt_blade_temp_C": round(blade_temp_C, 1),
        "mech_gt_creep_life_fraction": round(creep_life_fraction, 6),
        "mech_gt_creep_rupture_hr": round(t_rupture_hr, 0) if t_rupture_hr < 1e9 else -1,
        "mech_gt_eoh_consumed": round(eoh_consumed, 0),
        "mech_gt_eoh_remaining": round(eoh_remaining, 0),
    }


def _warnings(outputs: dict) -> list[str]:
    w = []
    clf = outputs["mech_gt_creep_life_fraction"]
    eoh_r = outputs["mech_gt_eoh_remaining"]
    if clf > 0.80:
        w.append(f"R-10: GT creep life fraction {clf:.2%} > 80% FAULT")
    elif clf > 0.50:
        w.append(f"R-10: GT creep life fraction {clf:.2%} > 50% WARNING")
    if 0 <= eoh_r < 2000:
        w.append(f"R-10: GT EOH remaining {eoh_r:.0f} hr < 2000 WARNING")
    return w


class GTTurbinePhysicsModel(PhysicsModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        return self._result("ACTIVE", outputs, _warnings(outputs))


class GTTurbineHybridModel(HybridModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        uncertain = [
            k for k in ["cooling_effectiveness", "larson_miller_LMP_rupture", "design_stress_MPa"]
            if k not in self.package.required_params
        ]
        return self._result("ACTIVE_UNCERTAIN", outputs, _warnings(outputs), uncertain)


register_model("GT_Turbine", GTTurbinePhysicsModel, GTTurbineHybridModel)

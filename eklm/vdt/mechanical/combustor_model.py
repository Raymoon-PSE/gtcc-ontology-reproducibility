"""Combustor Mechanical Model — COMB-001 (unit 1-4).

Outputs: liner_temp_C, fatigue_life_fraction, remaining_starts, remaining_life_hr

Physics basis:
    - Liner temperature: T_liner = TIT * liner_temp_ratio
    - Thermal fatigue (Coffin-Manson): N_f = N_f_design * (delta_T_ref / delta_T)^n
      [Lefebvre, Gas Turbine Combustion]
    - Operating-hour life: fraction of inspection interval consumed
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

    liner_ratio = pkg.get("liner_temp_ratio", 0.90)
    N_f_design = pkg.get("N_f_design_starts", 10000)
    insp_interval = pkg.get("inspection_interval_hr", 16000)
    delta_T_ref = pkg.get("delta_T_start_C", 800.0)
    cm_exp = pkg.get("coffin_manson_exponent", 2.0)

    # Liner temperature
    liner_temp_C = TIT_C * liner_ratio

    # Actual thermal cycle delta_T (ambient to TIT)
    delta_T_actual = TIT_C - op.compressor_inlet_T_C
    if delta_T_actual > 0 and delta_T_ref > 0:
        N_f_actual = N_f_design * (delta_T_ref / delta_T_actual) ** cm_exp
    else:
        N_f_actual = N_f_design

    # Fatigue life fraction
    fatigue_life_fraction = starts / N_f_actual if N_f_actual > 0 else 0.0
    remaining_starts = max(0, int(N_f_actual - starts))

    # Hour-based life
    hour_life_fraction = hours / insp_interval if insp_interval > 0 else 0.0
    remaining_life_hr = max(0.0, insp_interval - hours)

    # Combined life (whichever is worse)
    combined_life_fraction = max(fatigue_life_fraction, hour_life_fraction)

    return {
        "mech_comb_liner_temp_C": round(liner_temp_C, 1),
        "mech_comb_fatigue_life_fraction": round(fatigue_life_fraction, 6),
        "mech_comb_remaining_starts": remaining_starts,
        "mech_comb_hour_life_fraction": round(hour_life_fraction, 6),
        "mech_comb_remaining_life_hr": round(remaining_life_hr, 0),
        "mech_comb_combined_life_fraction": round(combined_life_fraction, 6),
    }


def _warnings(outputs: dict) -> list[str]:
    w = []
    clf = outputs["mech_comb_combined_life_fraction"]
    rs = outputs["mech_comb_remaining_starts"]
    if clf > 0.80:
        w.append(f"R-11: Combustor combined life fraction {clf:.2%} > 80% FAULT")
    elif clf > 0.50:
        w.append(f"R-11: Combustor combined life fraction {clf:.2%} > 50% WARNING")
    if 0 <= rs < 500:
        w.append(f"R-11: Combustor remaining starts {rs} < 500 WARNING")
    return w


class CombustorPhysicsModel(PhysicsModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        return self._result("ACTIVE", outputs, _warnings(outputs))


class CombustorHybridModel(HybridModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        uncertain = [
            k for k in ["liner_temp_ratio", "N_f_design_starts", "coffin_manson_exponent"]
            if k not in self.package.required_params
        ]
        return self._result("ACTIVE_UNCERTAIN", outputs, _warnings(outputs), uncertain)


register_model("Combustor", CombustorPhysicsModel, CombustorHybridModel)

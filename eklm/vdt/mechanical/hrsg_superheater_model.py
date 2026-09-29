"""HRSG HP Superheater Mechanical Model — HPSH-001 (unit 2-1).

Outputs: hoop_stress_MPa, creep_rupture_life_hr, creep_life_fraction, fouling_factor

Physics basis:
    - Hoop stress (ASME B31.1): sigma = P * D_o / (2 * t_w)
    - Creep rupture (Larson-Miller for P91): LMP = T_K * (C + log10(t_r))
      [NIMS Creep Data Sheet No. 43]
    - Fouling: R_f = R_f0 * (1 + k * hours/1000)
"""

from __future__ import annotations

import math

from eklm.vdt.mechanical.base import DeviceResult, HybridModel, PhysicsModel
from eklm.vdt.mechanical.data_package import DeviceDataPackage
from eklm.vdt.mechanical.model_router import register_model
from eklm.vdt.mechanical.operating_point import OperatingPoint


def _compute(op: OperatingPoint, pkg: DeviceDataPackage) -> dict:
    steam_T_C = op.HP_steam_T_C
    steam_P_MPa = op.HP_steam_P_MPa
    hours = op.cumulative_hours

    tube_OD_mm = pkg.get("tube_OD_mm", 50.8)
    tube_wall_mm = pkg.get("tube_wall_mm", 6.35)
    LM_C = pkg.get("larson_miller_C", 31.3)
    LMP_rupture = pkg.get("larson_miller_LMP_rupture", 32500.0)
    fouling_design = pkg.get("fouling_factor_design", 0.0002)
    k_fouling = pkg.get("k_fouling_per_khr", 0.003)

    # Hoop stress (thin-wall cylinder, ASME B31.1)
    D_o_m = tube_OD_mm / 1000.0
    t_w_m = tube_wall_mm / 1000.0
    hoop_stress_MPa = (steam_P_MPa * D_o_m) / (2.0 * t_w_m) if t_w_m > 0 else 0.0

    # Larson-Miller creep rupture life at metal temperature
    # Metal temp ≈ steam temp + 20°C (gas-side film, conservative)
    T_metal_C = steam_T_C + 20.0
    T_metal_K = T_metal_C + 273.15

    if T_metal_K > 0 and LMP_rupture > 0:
        log_t = LMP_rupture / T_metal_K - LM_C
        t_rupture_hr = 10.0 ** log_t if log_t < 10 else math.inf
    else:
        t_rupture_hr = math.inf

    creep_life_fraction = hours / t_rupture_hr if t_rupture_hr > 0 else 0.0

    # Fouling degradation
    fouling_factor = fouling_design * (1.0 + k_fouling * hours / 1000.0)

    return {
        "mech_hpsh_hoop_stress_MPa": round(hoop_stress_MPa, 2),
        "mech_hpsh_creep_rupture_hr": round(t_rupture_hr, 0) if t_rupture_hr < 1e9 else -1,
        "mech_hpsh_creep_life_fraction": round(creep_life_fraction, 6),
        "mech_hpsh_fouling_factor": round(fouling_factor, 6),
        "mech_hpsh_metal_temp_C": round(T_metal_C, 1),
    }


def _warnings(outputs: dict) -> list[str]:
    w = []
    clf = outputs["mech_hpsh_creep_life_fraction"]
    ff = outputs["mech_hpsh_fouling_factor"]
    if clf > 0.80:
        w.append(f"R-12: HP SH creep life fraction {clf:.2%} > 80% FAULT")
    elif clf > 0.50:
        w.append(f"R-12: HP SH creep life fraction {clf:.2%} > 50% WARNING")
    if ff > 0.001:
        w.append(f"R-12: HP SH fouling factor {ff:.4f} > 0.001 WARNING")
    return w


class HRSGSuperheaterPhysicsModel(PhysicsModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        return self._result("ACTIVE", outputs, _warnings(outputs))


class HRSGSuperheaterHybridModel(HybridModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        uncertain = [
            k for k in ["tube_OD_mm", "tube_wall_mm", "larson_miller_LMP_rupture"]
            if k not in self.package.required_params
        ]
        return self._result("ACTIVE_UNCERTAIN", outputs, _warnings(outputs), uncertain)


register_model("HRSG_Superheater", HRSGSuperheaterPhysicsModel, HRSGSuperheaterHybridModel)

"""HP Steam Turbine Mechanical Model — HPTURB (unit 3-1).

Outputs: blade_erosion_rate_mm_khr, erosion_depth_mm, moisture_loss_pct,
         remaining_life_hr

Physics basis:
    - Solid particle erosion: rate ~ k * (v / v_ref)^n
      [Leyzerovich, Steam Turbines for Modern Fossil-Fuel Power Plants]
    - Baumann moisture correction: eta_wet = eta_dry * (1 - alpha * y_avg)
      HP turbine operates in superheated region → moisture_loss ≈ 0
    - Life based on allowable erosion depth vs blade chord
"""

from __future__ import annotations

import math

from eklm.vdt.mechanical.base import DeviceResult, HybridModel, PhysicsModel
from eklm.vdt.mechanical.data_package import DeviceDataPackage
from eklm.vdt.mechanical.model_router import register_model
from eklm.vdt.mechanical.operating_point import OperatingPoint


def _estimate_steam_velocity(P_MPa: float, T_C: float, power_kW: float) -> float:
    """Rough estimate of steam velocity through HP nozzles (m/s).

    Uses ideal gas approximation for order-of-magnitude estimate.
    For superheated steam at ~16 MPa / 566°C, v ~ 200-400 m/s.
    """
    if P_MPa <= 0 or power_kW <= 0:
        return 200.0
    # Higher pressure / power → higher velocity (simplified scaling)
    v_base = 250.0  # typical HP nozzle velocity
    P_ratio = P_MPa / 16.5
    return v_base * (P_ratio ** 0.3)


def _compute(op: OperatingPoint, pkg: DeviceDataPackage) -> dict:
    T_C = op.HP_steam_T_C
    P_MPa = op.HP_steam_P_MPa
    hours = op.cumulative_hours

    k_erosion = pkg.get("erosion_rate_coeff", 0.005)
    v_exp = pkg.get("erosion_velocity_exponent", 2.5)
    v_ref = pkg.get("reference_velocity_m_s", 300.0)
    chord_mm = pkg.get("blade_chord_mm", 80.0)
    max_depth_mm = pkg.get("max_erosion_depth_mm", 2.0)

    # Steam velocity estimate
    v_steam = _estimate_steam_velocity(P_MPa, T_C, op.ST_power_kW)

    # Erosion rate (mm per 1000 hours)
    v_ratio = v_steam / v_ref if v_ref > 0 else 1.0
    erosion_rate = k_erosion * (v_ratio ** v_exp)

    # Accumulated erosion
    erosion_depth_mm = erosion_rate * (hours / 1000.0)

    # Remaining life (hours until max allowable erosion depth)
    remaining_depth = max(0.0, max_depth_mm - erosion_depth_mm)
    remaining_life_hr = (
        (remaining_depth / erosion_rate) * 1000.0
        if erosion_rate > 0
        else math.inf
    )

    # Moisture loss — HP turbine operates superheated, so ≈ 0
    # Included for completeness and future extension to IP/LP
    moisture_loss_pct = 0.0

    return {
        "mech_hpst_erosion_rate_mm_khr": round(erosion_rate, 5),
        "mech_hpst_erosion_depth_mm": round(erosion_depth_mm, 4),
        "mech_hpst_steam_velocity_m_s": round(v_steam, 1),
        "mech_hpst_moisture_loss_pct": round(moisture_loss_pct, 2),
        "mech_hpst_remaining_life_hr": round(remaining_life_hr, 0) if remaining_life_hr < 1e9 else -1,
    }


def _warnings(outputs: dict) -> list[str]:
    w = []
    depth = outputs["mech_hpst_erosion_depth_mm"]
    rl = outputs["mech_hpst_remaining_life_hr"]
    if depth > 1.5:
        w.append(f"R-14: HP ST blade erosion {depth:.2f} mm > 1.5 mm FAULT")
    elif depth > 1.0:
        w.append(f"R-14: HP ST blade erosion {depth:.2f} mm > 1.0 mm WARNING")
    if 0 <= rl < 5000:
        w.append(f"R-14: HP ST remaining life {rl:.0f} hr < 5000 hr WARNING")
    return w


class HPSTurbinePhysicsModel(PhysicsModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        return self._result("ACTIVE", outputs, _warnings(outputs))


class HPSTurbineHybridModel(HybridModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        outputs = _compute(op, self.package)
        uncertain = [
            k for k in ["erosion_rate_coeff", "reference_velocity_m_s", "max_erosion_depth_mm"]
            if k not in self.package.required_params
        ]
        return self._result("ACTIVE_UNCERTAIN", outputs, _warnings(outputs), uncertain)


register_model("HP_ST", HPSTurbinePhysicsModel, HPSTurbineHybridModel)

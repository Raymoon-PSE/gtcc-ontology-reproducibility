"""Calibration framework — back-calculate model parameters from plant data.

Fits eta_comp and eta_turb with fixed LHV by default.
An explicit legacy option also fits LHV but reports underdetermination.
Supports any target dataset (NETL, Sejong, or future plant data).

Usage:
    from eklm.vdt.analysis.calibrate import calibrate, PlantData, NETL_CASE13, SEJONG
    result = calibrate(NETL_CASE13)
    print(result)
"""

from dataclasses import dataclass, field, replace
import math

import numpy as np
from scipy.optimize import least_squares

from eklm.vdt.models.m1_gt.air_inlet import air_inlet
from eklm.vdt.models.m1_gt.compressor import compressor
from eklm.vdt.models.m1_gt.fuel_system import fuel_system
from eklm.vdt.models.m1_gt.combustor import combustor
from eklm.vdt.models.m1_gt.gt_expander import gt_expander
from eklm.vdt.models.m1_gt.gt_generator import gt_generator
from eklm.vdt.analysis.gtcc_loop import gtcc_solve
from eklm.vdt.data.streams import Stream
from eklm.vdt.models.m2_hrsg.hrsg_solver import HRSGParams
from eklm.vdt.models.m3_st.st_solver import STParams
from eklm.vdt.models.m4_condenser.condenser_solver import CondenserParams


@dataclass
class PlantData:
    """Target plant data for calibration."""

    name: str

    # Ambient / fuel (inputs)
    T_amb: float            # Ambient temperature, C
    P_amb: float            # Ambient pressure, MPa
    m_dot_air: float        # Air mass flow, kg/hr
    fuel_comp: dict         # Fuel mass fractions
    T_fuel: float           # Fuel temperature, C
    P_fuel: float           # Fuel pressure, MPa
    m_dot_fuel: float       # Fuel mass flow, kg/hr

    # GT parameters (fixed)
    PR: float               # Compressor pressure ratio
    P_exhaust: float        # GT exhaust pressure, MPa
    eta_gen: float          # Generator efficiency

    # Measured targets (for calibration objective)
    W_GT_target: float      # GT gross power, kW
    T_exhaust_target: float # GT exhaust temperature, C
    W_net_target: float | None = None  # Net plant power, kW (optional)


@dataclass
class PlantConfiguration:
    """Explicit common-header configuration for identical GT trains.

    gt_multiplier converts the supplied GT data basis to the whole-plant basis.
    HRSG flows are whole-plant totals. This model does not represent district
    heating extraction; do not use it for an unmodelled cogeneration condition.
    """
    gt_multiplier: int
    hrsg: HRSGParams
    steam_turbine: STParams
    condenser: CondenserParams
    auxiliary_power_kW: float
    source: str

    def validate(self):
        if type(self.gt_multiplier) is not int or self.gt_multiplier < 1:
            raise ValueError("gt_multiplier must be a positive integer")
        if not self.source.strip():
            raise ValueError("Plant configuration requires a source")
        if not math.isfinite(self.auxiliary_power_kW) or self.auxiliary_power_kW < 0:
            raise ValueError("Invalid whole-plant auxiliary power")
        for key in ('eta_hpt', 'eta_ipt', 'eta_lpt'):
            value = getattr(self.steam_turbine, key)
            if value is None or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"Explicit {key} required; NETL back-calibration is not allowed")
        if not math.isclose(self.steam_turbine.P_28, self.condenser.P_cond, rel_tol=1e-6):
            raise ValueError("ST exhaust and condenser pressures must agree")


def evaluate_plant(gt_result: dict, configuration: PlantConfiguration):
    """Aggregate GT exhaust, heat input and power on the SAME plant basis."""
    configuration.validate()
    n = configuration.gt_multiplier
    exhaust = replace(gt_result['s7'], m_dot=gt_result['s7'].m_dot * n)
    return gtcc_solve(exhaust, gt_result['W_GT'] * n, gt_result['Q_fuel'] * n,
                      hrsg_params=configuration.hrsg,
                      st_params=configuration.steam_turbine,
                      cond_params=configuration.condenser,
                      auxiliary_power_kW=configuration.auxiliary_power_kW)


@dataclass
class CalibrationResult:
    """Result of calibration."""

    plant: str
    eta_comp: float
    eta_turb: float
    LHV_scale: float        # Multiplier on handbook LHV (1.0 = no change)
    W_GT_model: float
    W_GT_target: float
    T_exhaust_model: float
    T_exhaust_target: float
    W_net_model: float | None
    W_net_target: float | None
    residual: float
    converged: bool
    calibration_targets: tuple[str, ...] = ("W_GT", "T_exhaust")
    fitted_parameters: tuple[str, ...] = ("eta_comp", "eta_turb")
    locally_identifiable: bool = False
    jacobian_rank: int = 0
    jacobian_condition: float = float("inf")
    plant_status: str = "not_evaluated"
    warnings: list[str] = field(default_factory=list)


# ── Pre-built datasets ──────────────────────────────────────────────────

NETL_CASE13 = PlantData(
    name="NETL Case 13",
    T_amb=15.0, P_amb=0.1013,
    m_dot_air=3_154_735,
    fuel_comp={"CH4": 0.86205, "C2H6": 0.05553, "C3H8": 0.01781,
               "C4H10": 0.01342, "CO2": 0.02540, "N2": 0.02579},
    T_fuel=38.0, P_fuel=3.10, m_dot_fuel=75_901,
    PR=18.1, P_exhaust=0.1048, eta_gen=0.984,
    W_GT_target=362_200,
    T_exhaust_target=629.0,
    W_net_target=555_080,
)

# Sejong: single GT train. Values from PNG (자료 column).
# Air mass flow: m_exhaust - m_fuel. NETL-style composition (dry air + humidity).
# m_exhaust = 1,586 ton/hr = 1,586,000 kg/hr.
# m_fuel estimated from heat input: 1.685e9 kJ/hr / LHV(~47,188 kJ/kg) ~ 35,700 kg/hr.
# m_air ~ 1,586,000 - 35,700 ~ 1,550,300 kg/hr.
SEJONG = PlantData(
    name="Sejong CC",
    T_amb=15.0, P_amb=0.1013,
    m_dot_air=1_550_300,
    fuel_comp={"CH4": 0.86205, "C2H6": 0.05553, "C3H8": 0.01781,
               "C4H10": 0.01342, "CO2": 0.02540, "N2": 0.02579},
    T_fuel=38.0, P_fuel=3.10, m_dot_fuel=35_700,
    PR=18.1, P_exhaust=0.1039, eta_gen=0.984,
    W_GT_target=167_104,
    T_exhaust_target=630.0,
    W_net_target=530_441,
)


def _run_m1(data: PlantData, eta_comp: float, eta_turb: float,
            LHV_scale: float = 1.0) -> dict:
    """Run M1 GT with given parameters, return key outputs."""
    ambient = Stream(T=data.T_amb, P=data.P_amb, m_dot=data.m_dot_air,
                     w={"N2": 0.7732, "O2": 0.2074, "CO2": 0.0003,
                        "H2O": 0.0099, "Ar": 0.0092})
    fuel = Stream(T=data.T_fuel, P=data.P_fuel, m_dot=data.m_dot_fuel,
                  w=data.fuel_comp)

    s2 = air_inlet(ambient)
    s3, _, W_comp = compressor(s2, PR=data.PR, eta=eta_comp)
    fs = fuel_system(fuel)

    # Apply LHV scale factor
    LHV_scaled = fs.LHV_blend * LHV_scale

    cmb = combustor(s3=s3, s5=fs.s5, LHV_f=LHV_scaled,
                    nu_O2_blend=fs.nu_O2_blend, eta_comb=0.998, delta_comb=0.03)
    s7, W_turb = gt_expander(s6=cmb.s6, s_bleed=None,
                             eta_turb=eta_turb, P_7=data.P_exhaust)
    _, W_GT = gt_generator(W_turb=W_turb, W_comp=W_comp, eta_gen=data.eta_gen)

    return {
        "s7": s7, "W_GT": W_GT, "T_exhaust": s7.T,
        "Q_fuel": cmb.Q_comb, "W_comp": W_comp, "W_turb": W_turb,
    }


def calibrate(
    data: PlantData,
    x0: tuple[float, float, float] = (0.86, 0.89, 1.0),
    bounds: tuple = ((0.75, 0.92), (0.80, 0.95), (0.95, 1.10)),
    *,
    fixed_lhv_scale: float | None = 1.0,
    plant_configuration: PlantConfiguration | None = None,
) -> CalibrationResult:
    """Fit GT efficiencies to two targets, with LHV fixed by default.

    Whole-plant results require an explicit PlantConfiguration.
    fixed_lhv_scale=None enables the underdetermined legacy fit.

    Minimizes weighted sum of squared relative errors on W_GT and T_exhaust.

    Args:
        data: Target plant data.
        x0: Initial guess (eta_comp, eta_turb, LHV_scale).
        bounds: Parameter bounds.

    Returns:
        CalibrationResult with optimized parameters and residuals.
    """
    # Two measured targets cannot identify three independent parameters.
    # Fixed LHV is the default; an explicitly requested legacy three-parameter
    # fit is retained but reported as underdetermined.
    if fixed_lhv_scale is not None and (not math.isfinite(fixed_lhv_scale) or fixed_lhv_scale <= 0):
        raise ValueError("fixed_lhv_scale must be positive and finite")
    if plant_configuration is not None:
        plant_configuration.validate()
    free_lhv = fixed_lhv_scale is None
    initial = x0 if free_lhv else x0[:2]
    fit_bounds = bounds if free_lhv else bounds[:2]
    def unpack(x):
        return tuple(x) if free_lhv else (x[0], x[1], fixed_lhv_scale)
    def residuals(x):
        r = _run_m1(data, *unpack(x))
        return np.array([(r['W_GT'] - data.W_GT_target) / data.W_GT_target,
                         (r['T_exhaust'] - data.T_exhaust_target) / (data.T_exhaust_target + 273.15)])
    result = least_squares(residuals, initial,
                           bounds=([b[0] for b in fit_bounds], [b[1] for b in fit_bounds]),
                           diff_step=1e-4, xtol=1e-12, ftol=1e-12, gtol=1e-12,
                           max_nfev=300)
    eta_comp, eta_turb, LHV_scale = unpack(result.x)
    r = _run_m1(data, eta_comp, eta_turb, LHV_scale)
    step = 1e-5
    jac = np.column_stack([(residuals(result.x + np.eye(len(result.x))[i] * step)
                            - residuals(result.x - np.eye(len(result.x))[i] * step)) / (2 * step)
                           for i in range(len(result.x))])
    rank = int(np.linalg.matrix_rank(jac))
    condition = float(np.linalg.cond(jac)) if rank == len(result.x) else float("inf")
    warnings = []
    if condition > 100:
        warnings.append("Calibration is ill-conditioned: small target errors can materially change fitted efficiencies.")
    if any(abs(value-low)<1e-5 or abs(value-high)<1e-5 for value,(low,high) in zip(result.x,fit_bounds)):
        warnings.append("At least one fitted parameter reached its bound; check inputs and model discrepancy.")
    if rank < len(result.x):
        warnings.append('Calibration is locally underdetermined; fitted parameters are not unique.')
    W_net_model = None
    plant_status = 'not_evaluated_missing_configuration'
    if plant_configuration is not None:
        try:
            gtcc = evaluate_plant(r, plant_configuration)
            plant_status = 'converged' if gtcc.converged else 'not_converged'
            if gtcc.converged:
                W_net_model = gtcc.W_net
        except (ValueError, RuntimeError, OverflowError) as exc:
            plant_status = 'failed'
            warnings.append(f'Plant evaluation failed: {type(exc).__name__}: {exc}')
    elif data.W_net_target is not None:
        warnings.append('Whole-plant comparison omitted: explicit GT basis, HRSG/ST and auxiliary configuration required.')

    return CalibrationResult(
        plant=data.name,
        eta_comp=eta_comp,
        eta_turb=eta_turb,
        LHV_scale=LHV_scale,
        W_GT_model=r["W_GT"],
        W_GT_target=data.W_GT_target,
        T_exhaust_model=r["T_exhaust"],
        T_exhaust_target=data.T_exhaust_target,
        W_net_model=W_net_model,
        W_net_target=data.W_net_target,
        residual=float(result.fun @ result.fun),
        converged=bool(result.success and np.max(np.abs(residuals(result.x))) < 1e-3),
        fitted_parameters=("eta_comp", "eta_turb", "LHV_scale") if free_lhv else ("eta_comp", "eta_turb"),
        locally_identifiable=rank == len(result.x), jacobian_rank=rank, jacobian_condition=condition,
        plant_status=plant_status, warnings=warnings,
    )

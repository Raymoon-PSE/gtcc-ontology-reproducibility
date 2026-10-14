"""OperatingPoint — interface between Steady Simulator and Mechanical Models.

Reference: GTCC_Mechanical_Modeling_Strategy.md §5.

Extracts the mechanical-relevant operating conditions from a converged
steady-state simulation result. All units follow project conventions:
    T in °C, P in MPa, m_dot in kg/hr, Power in kW.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eklm.vdt.analysis.gtcc_loop import GTCCResult
    from eklm.vdt.data.streams import Stream


@dataclass
class OperatingPoint:
    """Steady-state operating conditions for mechanical model input."""

    # Gas Turbine
    compressor_inlet_T_C: float
    compressor_outlet_T_C: float
    compressor_outlet_P_MPa: float
    compressor_inlet_P_MPa: float
    mass_flow_kg_s: float
    TIT_C: float
    GT_power_kW: float
    GT_efficiency: float

    # HRSG
    GT_exhaust_T_C: float
    HP_steam_T_C: float
    HP_steam_P_MPa: float
    reheat_steam_T_C: float
    reheat_steam_P_MPa: float

    # Steam Turbine
    ST_power_kW: float
    condenser_pressure_kPa: float

    # Operating history (user-supplied, not from simulation)
    load_factor: float = 1.0
    cumulative_hours: float = 0.0
    start_stop_count: int = 0

    @property
    def pressure_ratio(self) -> float:
        if self.compressor_inlet_P_MPa > 0:
            return self.compressor_outlet_P_MPa / self.compressor_inlet_P_MPa
        return 0.0


def extract_operating_point(
    s2: "Stream",
    s3: "Stream",
    s6: "Stream",
    W_comp: float,
    W_GT: float,
    r: "GTCCResult",
    load_factor: float = 1.0,
    cumulative_hours: float = 0.0,
    start_stop_count: int = 0,
) -> OperatingPoint:
    """Build OperatingPoint from steady-state intermediate results.

    Args:
        s2: Compressor inlet stream (after air inlet).
        s3: Compressor outlet stream.
        s6: Combustor outlet stream (TIT).
        W_comp: Compressor power, kW.
        W_GT: GT gross power, kW.
        r: Converged GTCCResult.
        load_factor: Current load factor (0-1). Default 1.0.
        cumulative_hours: Total operating hours. Default 0.
        start_stop_count: Total start-stop cycles. Default 0.
    """
    GT_eff = W_GT / r.Q_fuel if r.Q_fuel > 0 else 0.0

    return OperatingPoint(
        compressor_inlet_T_C=s2.T,
        compressor_outlet_T_C=s3.T,
        compressor_outlet_P_MPa=s3.P,
        compressor_inlet_P_MPa=s2.P,
        mass_flow_kg_s=s2.m_dot / 3600.0,
        TIT_C=s6.T,
        GT_power_kW=W_GT,
        GT_efficiency=GT_eff,
        GT_exhaust_T_C=r.s7.T,
        HP_steam_T_C=r.m2.s_is01.T,
        HP_steam_P_MPa=r.m2.s_is01.P,
        reheat_steam_T_C=r.m2.s_is03.T,
        reheat_steam_P_MPa=r.m2.s_is03.P,
        ST_power_kW=r.m3.W_ST,
        condenser_pressure_kPa=r.m4.s_is06_hw.P * 1000.0,
        load_factor=load_factor,
        cumulative_hours=cumulative_hours,
        start_stop_count=start_stop_count,
    )

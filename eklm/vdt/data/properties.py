"""Thermophysical property closure module.

Two backends:

1. **Air** — CoolProp pseudo-pure fluid "Air" (fixed atmospheric composition).
   Used by Units 1-1, 1-2 (compressor working fluid).

2. **Fuel blend** — ideal-gas, constant-cp model based on per-species cp from
   `osim.fuels.FUEL_DATA`. Used by Unit 1-3 (Fuel System).

   Why not CoolProp HEOS mixture for fuel?
       - Fuel sensible enthalpy from 25 °C reference is dominated by LHV
         by a factor of ~1000 (e.g. NETL Case 13: ~28 kJ/kg sensible vs
         ~47 000 kJ/kg LHV → 0.06% effect on the cycle).
       - HEOS mixtures with NH₃ blends have no validated mixing rule
         and may fail to converge near phase boundaries.
       - Robustness > 0.06% accuracy for a real-time simulator.
   The function bodies can be replaced with HEOS calls in Phase 2 without
   changing signatures.

All public functions accept Stream-native units (T in °C, P in MPa) and
return SI mass-specific units (h in J/kg, s in J/kg/K).

Composition convention: `w` is **mass fraction** (per Math Model §3.6).

Reference: GT_Module_Math_Model §0.5, §2.4, §3.6.
"""

import math

from CoolProp.CoolProp import PropsSI

from eklm.vdt.data.fuels import FUEL_DATA

_FLUID = "Air"
_T_REF_C = 25.0           # Fuel reference temperature, °C
_P_REF_MPA = 0.101325     # Fuel reference pressure, MPa (1 atm)
_R_UNIVERSAL = 8.314462   # J/mol/K


def _check_air(w: dict[str, float] | None) -> None:
    """Phase 1 guard: only the CoolProp 'Air' pseudo-pure fluid is supported.

    Composition `w` is currently informational only. A future mixture-aware
    backend will dispatch on `w`.
    """
    # TODO: composition-aware properties for combustion gas (Unit 1-4 onward)
    return


def h_air(T_C: float, P_MPa: float, w: dict[str, float] | None = None) -> float:
    """Specific enthalpy of air at (T, P). Returns J/kg."""
    _check_air(w)
    return PropsSI("H", "T", T_C + 273.15, "P", P_MPa * 1e6, _FLUID)


def s_air(T_C: float, P_MPa: float, w: dict[str, float] | None = None) -> float:
    """Specific entropy of air at (T, P). Returns J/kg/K."""
    _check_air(w)
    return PropsSI("S", "T", T_C + 273.15, "P", P_MPa * 1e6, _FLUID)


def h_from_PS_air(P_MPa: float, s: float, w: dict[str, float] | None = None) -> float:
    """Enthalpy at given (P, s) — used for the isentropic reference state."""
    _check_air(w)
    return PropsSI("H", "P", P_MPa * 1e6, "S", s, _FLUID)


def T_from_PH_air(P_MPa: float, h: float, w: dict[str, float] | None = None) -> float:
    """Temperature at given (P, h). Returns °C (Stream-native)."""
    _check_air(w)
    return PropsSI("T", "P", P_MPa * 1e6, "H", h, _FLUID) - 273.15


# ---------------------------------------------------------------------------
# Fuel blend properties (ideal-gas, constant-cp closure)
# ---------------------------------------------------------------------------

def _cp_blend(w: dict[str, float]) -> float:
    """Mass-weighted cp of a fuel blend, in J/kg/K."""
    return sum(w[k] * FUEL_DATA[k]["cp"] for k in w) * 1000.0


def _M_blend(w: dict[str, float]) -> float:
    """Mole-averaged molar mass of a fuel blend, in g/mol.

    Derived from mass fractions: 1/M_mix = Σ (w_k / M_k).
    """
    return 1.0 / sum(w[k] / FUEL_DATA[k]["M"] for k in w)


def _R_blend(w: dict[str, float]) -> float:
    """Specific gas constant of a fuel blend, in J/kg/K."""
    return _R_UNIVERSAL * 1000.0 / _M_blend(w)


def h_fuel(T_C: float, w: dict[str, float]) -> float:
    """Sensible enthalpy of a fuel blend, J/kg.

    Reference state: 25 °C, h_ref = 0. Ideal-gas constant-cp model.
    Composition `w` is mass fraction (Math Model §3.6).

    Note: this is sensible enthalpy only. Chemical (combustion) energy is
    handled separately in Unit 1-4 via LHV/HHV.
    """
    return _cp_blend(w) * (T_C - _T_REF_C)


def s_fuel(T_C: float, P_MPa: float, w: dict[str, float]) -> float:
    """Sensible entropy of a fuel blend, J/kg/K.

    Reference state: 25 °C, 0.101325 MPa (1 atm). Ideal-gas mixture form:
        s − s_ref = cp · ln(T / T_ref) − R · ln(P / P_ref)

    Used for Phase 2 exergy analysis. Cycle energy balance does not depend
    on this value.
    """
    cp = _cp_blend(w)
    R = _R_blend(w)
    T_K = T_C + 273.15
    T_ref_K = _T_REF_C + 273.15
    return cp * math.log(T_K / T_ref_K) - R * math.log(P_MPa / _P_REF_MPA)


# ---------------------------------------------------------------------------
# Water / Steam properties (CoolProp IAPWS-IF97)
# ---------------------------------------------------------------------------

_WATER = "Water"


def h_water(T_C: float, P_MPa: float) -> float:
    """Specific enthalpy of water/steam at (T, P). Returns J/kg."""
    return PropsSI("H", "T", T_C + 273.15, "P", P_MPa * 1e6, _WATER)


def s_water(T_C: float, P_MPa: float) -> float:
    """Specific entropy of water/steam at (T, P). Returns J/kg/K."""
    return PropsSI("S", "T", T_C + 273.15, "P", P_MPa * 1e6, _WATER)


def T_sat_water(P_MPa: float) -> float:
    """Saturation temperature at given pressure. Returns °C."""
    return PropsSI("T", "P", P_MPa * 1e6, "Q", 0, _WATER) - 273.15


def h_sat_vap_water(P_MPa: float) -> float:
    """Saturated vapor enthalpy at given pressure. Returns J/kg."""
    return PropsSI("H", "P", P_MPa * 1e6, "Q", 1, _WATER)


def h_sat_liq_water(P_MPa: float) -> float:
    """Saturated liquid enthalpy at given pressure. Returns J/kg."""
    return PropsSI("H", "P", P_MPa * 1e6, "Q", 0, _WATER)


def s_sat_vap_water(P_MPa: float) -> float:
    """Saturated vapor entropy at given pressure. Returns J/kg/K."""
    return PropsSI("S", "P", P_MPa * 1e6, "Q", 1, _WATER)


def T_from_PH_water(P_MPa: float, h: float) -> float:
    """Temperature at given (P, h) for water/steam. Returns °C."""
    return PropsSI("T", "P", P_MPa * 1e6, "H", h, _WATER) - 273.15


def s_from_PH_water(P_MPa: float, h: float) -> float:
    """Entropy at given (P, h) for water/steam. Returns J/kg/K."""
    return PropsSI("S", "P", P_MPa * 1e6, "H", h, _WATER)


def h_from_PS_water(P_MPa: float, s: float) -> float:
    """Enthalpy at given (P, s) for water/steam. Returns J/kg.

    Used for isentropic reference state in steam turbine calculations.
    Works in both single-phase and two-phase regions.
    """
    return PropsSI("H", "P", P_MPa * 1e6, "S", s, _WATER)


def x_from_PH_water(P_MPa: float, h: float) -> float:
    """Steam quality (vapor fraction) at given (P, h). Returns 0-1 or -1.

    Returns -1 if the state is outside the two-phase region (superheated
    or subcooled), since CoolProp returns negative quality for single-phase.
    """
    x = PropsSI("Q", "P", P_MPa * 1e6, "H", h, _WATER)
    return x if 0.0 <= x <= 1.0 else -1.0

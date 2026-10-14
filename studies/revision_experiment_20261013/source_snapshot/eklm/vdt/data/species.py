"""NASA-7 ideal-gas thermodynamic library (Lib_thermo).

Reference: Unit_1-4_Combustor_Math_Model_v2.1 § 4.5 Section I.
Coefficient source: GRI-Mech 3.0 thermo.dat (Smith, Golden, Frenklach, et al.,
1999), Gordon-McBride NASA Lewis polynomial compilation. See
``docs/NASA7_table_patch_for_v2_1.md`` for the patched § 4.5 Section I tables
that this module implements.

Functions:
    cp_species(T_K, name)         specific heat,         J/(kg·K)
    h_species(T_K, name)          sensible enthalpy,     J/kg  (h(298.15 K) = 0)
    s_species(T_K, P_Pa, name)    specific entropy,      J/(kg·K)
    cp_mix(T_K, w)                mass-weighted mixture cp
    h_mix(T_K, w)                 mass-weighted mixture h
    s_mix(T_K, P_Pa, w)           mass-weighted mixture s
    T_from_H_mix(h_target, w, ...) Newton-Raphson temperature inversion

**Sensible enthalpy convention** (Note N-3 of v2.1):
NASA-7 raw form is absolute enthalpy with datum at elements at 298.15 K, so
``a_6`` encodes ΔH_f°(298 K). Subtracting ``h_NASA7(298.15 K)`` per species
yields sensible enthalpy with h(298.15 K) = 0 for every species. This removes
ΔH_f° from the energy term so LHV (which already carries combustion energy)
is not double-counted in the combustor energy balance.

Coefficient selection:
    T < 1000 K  → low-T  (200–1000 K range)
    T ≥ 1000 K  → high-T (1000–5000 K range)

All inputs/outputs use SI units (K, Pa, J/kg).
"""

import math

R_KMOL = 8314.0     # J/(kmol·K), v2.1 § 4.5 Section I convention
P0 = 101325.0       # Pa, entropy reference pressure (1 atm)
T_REF_K = 298.15    # K, sensible enthalpy datum
T_BOUNDARY_K = 1000.0  # K, low/high coefficient transition

# Molar masses, kg/kmol (numerically same as g/mol).
M: dict[str, float] = {
    "N2":  28.014,
    "O2":  31.999,
    "CO2": 44.010,
    "H2O": 18.015,
    "Ar":  39.948,
    "CO":  28.010,
    "NO":  30.006,
}

# NASA-7 polynomial coefficients, GRI-Mech 3.0 thermo.dat.
# Format per species: (a1, a2, a3, a4, a5, a6, a7).
#
# h_raw(T) = (R/M) * (a1*T + a2/2*T² + a3/3*T³ + a4/4*T⁴ + a5/5*T⁵ + a6)   [J/kg]
# cp(T)    = (R/M) * (a1 + a2*T + a3*T² + a4*T³ + a5*T⁴)                   [J/(kg·K)]
# s°(T)    = (R/M) * (a1*ln T + a2*T + a3/2*T² + a4/3*T³ + a5/4*T⁴ + a7)   [J/(kg·K)]

# High-T range: 1000–5000 K
NASA7_HIGH: dict[str, tuple[float, float, float, float, float, float, float]] = {
    "N2":  (2.92664,  1.4879768e-3, -5.68476e-7,  1.0097038e-10, -6.7533510e-15,   -922.7977,  5.980528),
    "O2":  (3.66096,  6.5636581e-4, -1.4114963e-7, 2.0579794e-11, -1.2991344e-15, -1215.97718, 3.415362),
    "CO2": (4.45362,  3.1401684e-3, -1.2784105e-6, 2.3939961e-10, -1.6690333e-14, -48966.961, -0.955396),
    "H2O": (2.67215,  3.0562930e-3, -8.7302600e-7, 1.2009964e-10, -6.3916180e-15, -29899.212,  6.862817),
    "Ar":  (2.50000,  0.0,           0.0,           0.0,           0.0,             -745.375,  4.366000),
    "CO":  (3.02508,  1.4426885e-3, -5.6308270e-7, 1.0185813e-10, -6.9109510e-15, -14268.350,  6.108218),
    "NO":  (3.24544,  1.2691383e-3, -5.0158900e-7, 9.1692830e-11, -6.2754190e-15,   9800.840,  6.417294),
}

# Low-T range: 200–1000 K
NASA7_LOW: dict[str, tuple[float, float, float, float, float, float, float]] = {
    "N2":  (3.29868,  1.4082404e-3, -3.9632222e-6,  5.6415150e-9, -2.4448540e-12, -1020.8999,  3.950372),
    "O2":  (3.78246, -2.9967342e-3,  9.8473020e-6, -9.6812950e-9,  3.2437284e-12, -1063.94356, 3.657676),
    "CO2": (2.27572,  9.9220720e-3, -1.0409113e-5,  6.8666860e-9, -2.1172800e-12, -48373.140, 10.188488),
    "H2O": (3.38684,  3.4749820e-3, -6.3546960e-6,  6.9685810e-9, -2.5065880e-12, -30208.110,  2.590232),
    "Ar":  (2.50000,  0.0,           0.0,            0.0,           0.0,            -745.375,  4.366000),
    "CO":  (3.26245,  1.5119409e-3, -3.8817550e-6,  5.5819440e-9, -2.4749510e-12, -14310.539,  4.848897),
    "NO":  (3.37654,  1.2530634e-3, -3.3027500e-6,  5.2178100e-9, -2.4462620e-12,   9817.961,  5.829590),
}


def _select_coefs(T_K: float, name: str) -> tuple:
    """Pick LOW-T or HIGH-T coefficient set based on temperature."""
    if T_K < T_BOUNDARY_K:
        return NASA7_LOW[name]
    return NASA7_HIGH[name]


def _h_raw(T_K: float, name: str) -> float:
    """Raw NASA-7 absolute enthalpy at T, J/kg.

    Internal helper. External callers should use ``h_species`` which returns
    the sensible form (h(298.15 K) = 0).
    """
    a1, a2, a3, a4, a5, a6, _a7 = _select_coefs(T_K, name)
    Rs = R_KMOL / M[name]
    return Rs * (
        a1 * T_K
        + a2 / 2.0 * T_K**2
        + a3 / 3.0 * T_K**3
        + a4 / 4.0 * T_K**4
        + a5 / 5.0 * T_K**5
        + a6
    )


def cp_species(T_K: float, name: str) -> float:
    """Specific heat capacity at constant pressure, J/(kg·K)."""
    a1, a2, a3, a4, a5, _a6, _a7 = _select_coefs(T_K, name)
    Rs = R_KMOL / M[name]
    return Rs * (a1 + a2 * T_K + a3 * T_K**2 + a4 * T_K**3 + a5 * T_K**4)


def h_species(T_K: float, name: str) -> float:
    """Sensible enthalpy, J/kg, with h(298.15 K) = 0 (Note N-3).

    Subtracts the raw enthalpy at the 298.15 K reference using the LOW-T
    coefficients (since 298.15 < 1000 K), preserving smoothness across the
    1000 K boundary because the polynomial is continuous there.
    """
    return _h_raw(T_K, name) - _h_raw(T_REF_K, name)


def s_species(T_K: float, P_Pa: float, name: str) -> float:
    """Specific entropy, J/(kg·K). Reference pressure 1 atm."""
    a1, a2, a3, a4, a5, _a6, a7 = _select_coefs(T_K, name)
    Rs = R_KMOL / M[name]
    s0 = Rs * (
        a1 * math.log(T_K)
        + a2 * T_K
        + a3 / 2.0 * T_K**2
        + a4 / 3.0 * T_K**3
        + a5 / 4.0 * T_K**4
        + a7
    )
    return s0 - Rs * math.log(P_Pa / P0)


def cp_mix(T_K: float, w: dict[str, float]) -> float:
    """Mass-weighted mixture cp, J/(kg·K)."""
    return sum(wk * cp_species(T_K, k) for k, wk in w.items())


def h_mix(T_K: float, w: dict[str, float]) -> float:
    """Mass-weighted mixture sensible enthalpy, J/kg."""
    return sum(wk * h_species(T_K, k) for k, wk in w.items())


def s_mix(T_K: float, P_Pa: float, w: dict[str, float]) -> float:
    """Mass-weighted mixture entropy, J/(kg·K)."""
    return sum(wk * s_species(T_K, P_Pa, k) for k, wk in w.items())


def T_from_H_mix(
    h_target: float,
    w: dict[str, float],
    T_init_K: float = 1500.0,
    tol: float = 0.01,
    max_iter: int = 50,
) -> float:
    """Solve h_mix(T, w) = h_target for T (K) via Newton-Raphson.

    Per Math Model v2.1 § 4.5 Section V:
        T^(ν+1) = T^(ν) − [h_mix(T^ν, w) − h_target] / cp_mix(T^ν, w)

    Args:
        h_target: Target sensible enthalpy, J/kg.
        w: Mass-fraction composition.
        T_init_K: Initial guess. Default 1500 K (spec).
        tol: Convergence tolerance on |ΔT|, K. Default 0.01.
        max_iter: Iteration safety cap.

    Returns:
        Temperature in K.

    Raises:
        RuntimeError: if not converged within ``max_iter``.
    """
    T = T_init_K
    for _ in range(max_iter):
        f = h_mix(T, w) - h_target
        fp = cp_mix(T, w)
        dT = f / fp
        T = T - dT
        if abs(dT) < tol:
            return T
    raise RuntimeError(
        f"T_from_H_mix did not converge in {max_iter} iterations "
        f"(last T={T:.2f} K, residual={f:.2e} J/kg)"
    )


def T_from_PS_mix(
    P_Pa: float,
    s_target: float,
    w: dict[str, float],
    T_init_K: float = 1500.0,
    tol: float = 0.01,
    max_iter: int = 50,
) -> float:
    """Solve s_mix(T, P, w) = s_target for T (K) via Newton-Raphson.

    Used by Unit 1-5 (GT Expander) to find the isentropic reference state:
    given (P_outlet, s_inlet, w_outlet), find T such that the mixture entropy
    matches s_inlet — i.e. the temperature an isentropic expansion would reach.

    Derivative (ideal-gas thermodynamic identity at constant P):
        ∂s_mix/∂T = cp_mix(T, w) / T

    Args:
        P_Pa: Pressure (Pa) at which entropy is evaluated.
        s_target: Target entropy, J/(kg·K).
        w: Mass-fraction composition.
        T_init_K: Initial guess. Default 1500 K.
        tol: Convergence tolerance on |ΔT|, K. Default 0.01.
        max_iter: Iteration safety cap.

    Returns:
        Temperature in K.

    Raises:
        RuntimeError: if not converged within ``max_iter``.
    """
    T = T_init_K
    for _ in range(max_iter):
        f = s_mix(T, P_Pa, w) - s_target
        fp = cp_mix(T, w) / T
        dT = f / fp
        T = T - dT
        if abs(dT) < tol:
            return T
    raise RuntimeError(
        f"T_from_PS_mix did not converge in {max_iter} iterations "
        f"(last T={T:.2f} K, residual={f:.2e} J/(kg·K))"
    )

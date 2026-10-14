"""Fuel species library (Lib_fuel).

Reference: GT_Module_Math_Model §3.5, §3.6.

Provides per-species data needed by Unit 1-3 (Fuel System) and Unit 1-4
(Combustor):
    - M       molecular weight,        g/mol
    - LHV     lower heating value,     kJ/kg (mass basis)
    - HHV     higher heating value,    kJ/kg (mass basis)
    - nu_O2   stoichiometric O₂ coef., mol O₂ / mol fuel
    - cp      ideal-gas heat capacity, kJ/kg/K (25 °C, 1 atm)
    - c       CO₂ product coef.,       mol CO₂ / mol fuel
    - beta    H₂O product coef.,       mol H₂O / mol fuel
    - gamma   N₂  product coef.,       mol N₂  / mol fuel

Sources:
    - Molecular weights: IUPAC standard atomic weights.
    - LHV / HHV (25 °C, 1 atm): NIST Webbook and GPSA Engineering Data
      Book, rounded to engineering precision (± ~0.1%).
    - nu_O2, c, beta, gamma: stoichiometric balance for full combustion to
      CO₂, H₂O, N₂. For CxHyNzOw fuel: c = x, beta = y/2, gamma = z/2,
      nu_O2 = c + beta/2 − w/2 = x + y/4 − w/2.
      Inerts (CO₂, N₂) pass through to products: CO₂ → c=1, N₂ → gamma=1.
    - cp: NIST Webbook ideal-gas values at 298.15 K. Used by the
      simplified ideal-gas h_fuel / s_fuel closure (see properties.py).

Phase 1 scope: NETL NG (6 species) + blend fuels H₂, NH₃.
Pure H₂ or pure NH₃ alone is not supported (Math Model §3.3).
"""

# NETL Exhibit 5-4 — natural gas composition, mole fraction.
NETL_NG_COMPOSITION: dict[str, float] = {
    "CH4":   0.9310,
    "C2H6":  0.0320,
    "C3H8":  0.0070,
    "C4H10": 0.0040,
    "CO2":   0.0100,
    "N2":    0.0160,
}

# Per-species fuel data.
FUEL_DATA: dict[str, dict[str, float]] = {
    # Hydrocarbons (NETL NG components)
    "CH4":   {"M": 16.043, "LHV": 50_009, "HHV": 55_516, "nu_O2": 2.0,  "cp":  2.232, "c": 1, "beta": 2.0, "gamma": 0.0},
    "C2H6":  {"M": 30.070, "LHV": 47_511, "HHV": 51_901, "nu_O2": 3.5,  "cp":  1.746, "c": 2, "beta": 3.0, "gamma": 0.0},
    "C3H8":  {"M": 44.097, "LHV": 46_357, "HHV": 50_322, "nu_O2": 5.0,  "cp":  1.679, "c": 3, "beta": 4.0, "gamma": 0.0},
    "C4H10": {"M": 58.123, "LHV": 45_725, "HHV": 49_500, "nu_O2": 6.5,  "cp":  1.676, "c": 4, "beta": 5.0, "gamma": 0.0},
    # NETL NG inert components — passthrough to products
    "CO2":   {"M": 44.010, "LHV":      0, "HHV":      0, "nu_O2": 0.0,  "cp":  0.844, "c": 1, "beta": 0.0, "gamma": 0.0},
    "N2":    {"M": 28.014, "LHV":      0, "HHV":      0, "nu_O2": 0.0,  "cp":  1.039, "c": 0, "beta": 0.0, "gamma": 1.0},
    # Blend fuels (Math Model §3.3)
    "H2":    {"M":  2.016, "LHV": 119_960, "HHV": 141_790, "nu_O2": 0.5,  "cp": 14.304, "c": 0, "beta": 1.0, "gamma": 0.0},
    "NH3":   {"M": 17.031, "LHV":  18_577, "HHV":  22_472, "nu_O2": 0.75, "cp":  2.092, "c": 0, "beta": 1.5, "gamma": 0.5},
}

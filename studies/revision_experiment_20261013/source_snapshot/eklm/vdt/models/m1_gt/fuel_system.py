"""Unit 1-3: Fuel System.

Reference: GT_Module_Math_Model §3.

Prepares the fuel blend (NG ± H₂ ± NH₃), applies pressure drop, and computes
the stoichiometric combustion quantities required by Unit 1-4 (Combustor).

All composition arguments are mass fractions (Math Model §3.6).
"""

from dataclasses import dataclass

from eklm.vdt.data.fuels import FUEL_DATA
from eklm.vdt.data.properties import h_fuel, s_fuel
from eklm.vdt.data.streams import Stream

# Default O₂ mole fraction in atmospheric air (NETL Ch.5).
# Per Math Model §3.6, the caller should pass this dynamically from S^(1).
_DEFAULT_Y_O2_AIR = 0.2095


@dataclass
class FuelSystemOutput:
    """Outputs of Unit 1-3 (Math Model §3.8).

    Attributes:
        s5: Prepared fuel stream → Unit 1-4.
        LHV_blend: Effective lower heating value, kJ/kg.
        HHV_blend: Effective higher heating value, kJ/kg.
        nu_O2_blend: Stoichiometric O₂ coefficient, mol O₂ / mol fuel.
        n_dot_O2: Stoichiometric O₂ molar flow, kmol/hr.
        n_dot_air: Stoichiometric air molar flow, kmol/hr.
    """

    s5: Stream
    LHV_blend: float
    HHV_blend: float
    nu_O2_blend: float
    n_dot_O2: float
    n_dot_air: float


def fuel_system(
    s4: Stream,
    x_H2: float = 0.0,
    x_NH3: float = 0.0,
    dP_fuel: float = 0.0,
    y_O2_air: float = _DEFAULT_Y_O2_AIR,
) -> FuelSystemOutput:
    """Prepare the fuel blend and compute combustion stoichiometry.

    Args:
        s4: Boundary fuel stream. ``s4.w`` lists NG component mass fractions
            (CH4, C2H6, C3H8, C4H10, CO2, N2) summing to 1.
        x_H2: Mass fraction of H₂ to add to the blend. Default 0.
        x_NH3: Mass fraction of NH₃ to add to the blend. Default 0.
        dP_fuel: Fuel system pressure drop ΔP^(fuel), MPa. Default 0.
        y_O2_air: Mole fraction of O₂ in atmospheric air S^(1). Caller should
            pass this from the actual ambient air stream when available
            (Math Model §3.6).

    Returns:
        FuelSystemOutput. See class docstring for fields.

    Raises:
        ValueError: if ``x_H2`` or ``x_NH3`` is out of [0, 1), if their sum is
            ≥ 1 (Math Model §3.3 forbids pure H₂ / pure NH₃), if ``s4.w`` does
            not sum to 1, or if ``s4.w`` contains an unknown species.
    """
    # ---- 1. Input validation ------------------------------------------------
    if not (0.0 <= x_H2 < 1.0):
        raise ValueError(f"x_H2 must be in [0, 1), got {x_H2}")
    if not (0.0 <= x_NH3 < 1.0):
        raise ValueError(f"x_NH3 must be in [0, 1), got {x_NH3}")
    if x_H2 + x_NH3 >= 1.0:
        raise ValueError(
            f"x_H2 + x_NH3 must be < 1 (Math Model §3.3); "
            f"got {x_H2 + x_NH3}"
        )
    for k in s4.w:
        if k not in FUEL_DATA:
            raise ValueError(f"Unknown fuel species in s4.w: {k!r}")
    if abs(sum(s4.w.values()) - 1.0) > 1e-6:
        raise ValueError(
            f"s4.w mass fractions must sum to 1, got {sum(s4.w.values())}"
        )

    # ---- 2. Mass / energy / momentum balance (Math Model §3.6.1) -----------
    m_dot_5 = s4.m_dot
    T_5 = s4.T                 # isothermal
    P_5 = s4.P - dP_fuel

    # ---- 3. Blend composition w^(5) (Math Model §3.6.3) --------------------
    scale = 1.0 - x_H2 - x_NH3
    w5: dict[str, float] = {k: scale * v for k, v in s4.w.items()}
    if x_H2 > 0.0:
        w5["H2"] = x_H2
    if x_NH3 > 0.0:
        w5["NH3"] = x_NH3
    # Closure (defensive — math guarantees this if inputs are valid).
    assert abs(sum(w5.values()) - 1.0) < 1e-9

    # ---- 4. Mole fractions y^(5) and molar mass (Math Model §3.6.3) --------
    inv_M_mix = sum(w5[k] / FUEL_DATA[k]["M"] for k in w5)  # (mol/g)
    M_mix = 1.0 / inv_M_mix                                  # g/mol
    y5: dict[str, float] = {
        k: (w5[k] / FUEL_DATA[k]["M"]) / inv_M_mix for k in w5
    }

    # ---- 5. Effective LHV / HHV (mass basis) -------------------------------
    # Equivalent to Math Model §3.6.3 formula expressed via w directly.
    LHV_blend = sum(w5[k] * FUEL_DATA[k]["LHV"] for k in w5)  # kJ/kg
    HHV_blend = sum(w5[k] * FUEL_DATA[k]["HHV"] for k in w5)  # kJ/kg

    # ---- 6. Stoichiometric combustion quantities (Math Model §3.6.2) -------
    nu_O2_blend = sum(y5[k] * FUEL_DATA[k]["nu_O2"] for k in y5)
    # ṅ^(5) [kmol/hr] = ṁ [kg/hr] / M_mix [g/mol]   (units: kg·mol / g = kmol)
    n_dot_5 = m_dot_5 / M_mix
    n_dot_O2 = n_dot_5 * nu_O2_blend                          # kmol/hr
    n_dot_air = n_dot_O2 / y_O2_air                           # kmol/hr

    # ---- 7. Property closure ----------------------------------------------
    h5 = h_fuel(T_5, w5)
    s5_entropy = s_fuel(T_5, P_5, w5)

    s5 = Stream(T=T_5, P=P_5, m_dot=m_dot_5, w=w5, h=h5, s=s5_entropy)

    return FuelSystemOutput(
        s5=s5,
        LHV_blend=LHV_blend,
        HHV_blend=HHV_blend,
        nu_O2_blend=nu_O2_blend,
        n_dot_O2=n_dot_O2,
        n_dot_air=n_dot_air,
    )

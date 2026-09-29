"""Unit 1-5: GT Expander (Turbine).

Reference: GT_Module_Math_Model v1.1 § 5.

Expands hot combustion gas to generate shaft work. Bleed air (if any)
rejoins the main gas stream at the expander outlet via mass-weighted mixing.

All thermodynamics use the same NASA-7 sensible-enthalpy backend
(``osim.species``) as the combustor — h, s on incoming streams (s6 from
combustor, s_bleed from compressor) are **recomputed** locally to ensure
the property closure shares a single 298.15 K datum.
"""

from eklm.vdt.data.species import M as SPECIES_M
from eklm.vdt.data.species import T_from_PS_mix, cp_mix, h_mix, s_mix
from eklm.vdt.data.streams import Stream

# Bulk-product species (same set as combustor outlet).
_BULK_SPECIES = ("N2", "O2", "CO2", "H2O", "Ar")


def _ensure_bulk_species(w: dict[str, float]) -> dict[str, float]:
    """Return a w-dict that contains all bulk species (missing keys → 0)."""
    return {k: w.get(k, 0.0) for k in _BULK_SPECIES}


def gt_expander(
    s6: Stream,
    s_bleed: Stream | None,
    eta_turb: float,
    P_7: float = 0.1048,
) -> tuple[Stream, float]:
    """Expand combustion gas through the GT turbine.

    Implements GT_Module_Math_Model v1.1 § 5.5 (six explicit steps).

    Args:
        s6: Combustion-gas inlet from Unit 1-4 (TIT, P_6, w_6 mass fractions
            of {N2, O2, CO2, H2O, Ar}).
        s_bleed: Bleed-air inlet from Unit 1-2. ``None`` when ``f_bleed = 0``
            (Phase 1 default — no bleed). When non-None, contains air mass
            fractions and joins the main stream at the expander outlet.
        eta_turb: Isentropic efficiency η^(turb), in (0, 1].
        P_7: Outlet pressure, MPa. Default 0.1048 (NETL Exhibit 5-11).

    Returns:
        s7: GT exhaust stream → M2 HRSG.
        W_turb: Turbine shaft power Ẇ^(turb), kW (positive).
    """
    # ---- Step 1: mass balance --------------------------------------------
    m_dot_6 = s6.m_dot
    m_dot_bleed = s_bleed.m_dot if s_bleed is not None else 0.0
    m_dot_7 = m_dot_6 + m_dot_bleed

    # ---- Step 2: mixed inlet state ---------------------------------------
    # Recompute h, s for both streams via NASA-7 (consistent datum).
    T_6_K = s6.T + 273.15
    P_6_Pa = s6.P * 1.0e6
    w_6 = _ensure_bulk_species(s6.w)
    h_6 = h_mix(T_6_K, w_6)
    s_6 = s_mix(T_6_K, P_6_Pa, w_6)

    if s_bleed is not None and m_dot_bleed > 0.0:
        T_bleed_K = s_bleed.T + 273.15
        P_bleed_Pa = s_bleed.P * 1.0e6
        w_bleed = _ensure_bulk_species(s_bleed.w)
        h_bleed = h_mix(T_bleed_K, w_bleed)
        s_bleed_val = s_mix(T_bleed_K, P_bleed_Pa, w_bleed)

        # Mass-weighted mixing
        h_6_mix = (m_dot_6 * h_6 + m_dot_bleed * h_bleed) / m_dot_7
        s_6_mix = (m_dot_6 * s_6 + m_dot_bleed * s_bleed_val) / m_dot_7
        w_7 = {
            k: (m_dot_6 * w_6[k] + m_dot_bleed * w_bleed[k]) / m_dot_7
            for k in _BULK_SPECIES
        }
    else:
        # Phase 1: no bleed → all mixing terms collapse
        h_6_mix = h_6
        s_6_mix = s_6
        w_7 = w_6

    # ---- Step 3: isentropic reference state at P_7 -----------------------
    P_7_Pa = P_7 * 1.0e6
    T_ref_K = T_from_PS_mix(
        P_Pa=P_7_Pa, s_target=s_6_mix, w=w_7, T_init_K=T_6_K * 0.7
    )
    h_ref = h_mix(T_ref_K, w_7)

    # ---- Step 4: actual outlet enthalpy ----------------------------------
    h_7 = h_6_mix - eta_turb * (h_6_mix - h_ref)

    # ---- Step 5: turbine power -------------------------------------------
    # ṁ [kg/hr] × Δh [J/kg] / 3.6e6 = kW
    W_turb_kW = m_dot_7 * (h_6_mix - h_7) / 3.6e6

    # ---- Step 6: property closure ----------------------------------------
    # h_7 → T_7 via Newton-Raphson on enthalpy
    from eklm.vdt.data.species import T_from_H_mix
    T_7_K = T_from_H_mix(h_7, w_7, T_init_K=T_ref_K)
    s_7 = s_mix(T_7_K, P_7_Pa, w_7)

    s7 = Stream(
        T=T_7_K - 273.15,
        P=P_7,
        m_dot=m_dot_7,
        w=w_7,
        h=h_7,
        s=s_7,
    )

    return s7, W_turb_kW

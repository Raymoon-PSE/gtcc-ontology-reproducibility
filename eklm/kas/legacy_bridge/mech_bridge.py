"""Mechanical model ABox population — writes mech results into the RDF graph.

Follows the same pattern as populate.py: uses _set_var_value() and _set_kpi()
to write device-level mechanical model outputs to existing TTL individuals.
"""

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from eklm.kas.legacy_bridge.graph import PM
from eklm.vdt.mechanical.base import DeviceResult

# Output key → TTL property mapping
_PROP_MAP = {
    "mech_comp_surge_margin_pct": PM.mech_surgeMarginPct,
    "mech_comp_efficiency_current": PM.mech_efficiencyCurrent,
    "mech_comp_degradation_rate_pct_khr": PM.mech_degradationRatePctKhr,
    "mech_comp_remaining_life_hr": PM.mech_remainingLifeHr,
    "mech_gt_blade_temp_C": PM.mech_bladeTempC,
    "mech_gt_creep_life_fraction": PM.mech_creepLifeFraction,
    "mech_gt_creep_rupture_hr": PM.mech_creepRuptureHr,
    "mech_gt_eoh_consumed": PM.mech_eohConsumed,
    "mech_gt_eoh_remaining": PM.mech_eohRemaining,
    "mech_comb_liner_temp_C": PM.mech_linerTempC,
    "mech_comb_fatigue_life_fraction": PM.mech_fatigueLifeFraction,
    "mech_comb_combined_life_fraction": PM.mech_combinedLifeFraction,
    "mech_comb_remaining_life_hr": PM.mech_remainingLifeHr,
    "mech_hpsh_hoop_stress_MPa": PM.mech_hoopStressMPa,
    "mech_hpsh_creep_rupture_hr": PM.mech_creepRuptureHr,
    "mech_hpsh_creep_life_fraction": PM.mech_creepLifeFraction,
    "mech_hpsh_fouling_factor": PM.mech_foulingFactor,
    "mech_rh_hoop_stress_MPa": PM.mech_hoopStressMPa,
    "mech_rh_creep_rupture_hr": PM.mech_creepRuptureHr,
    "mech_rh_creep_life_fraction": PM.mech_creepLifeFraction,
    "mech_rh_fouling_factor": PM.mech_foulingFactor,
    "mech_hpst_erosion_depth_mm": PM.mech_erosionDepthMm,
    "mech_hpst_erosion_rate_mm_khr": PM.mech_erosionRateMmKhr,
    "mech_hpst_remaining_life_hr": PM.mech_remainingLifeHr,
}


def populate_mech(g: Graph, mech_results: list[DeviceResult]) -> int:
    """Write mechanical model results into the RDF graph ABox.

    Args:
        g: The RDF graph (loaded TTL files including Mechanical TTL).
        mech_results: List of DeviceResult from run_mechanical().

    Returns:
        Number of triples added/updated.
    """
    count = 0
    for mr in mech_results:
        # Remove outputs from an earlier run, including a device now inactive.
        for prop in _PROP_MAP.values():
            g.remove((PM[mr.device_id], prop, None))
        if mr.status == "INACTIVE":
            continue

        uri = PM[mr.device_id]

        for key, value in mr.outputs.items():
            prop = _PROP_MAP.get(key)
            if prop is None:
                continue
            if value == -1:
                continue
            g.remove((uri, prop, None))
            g.add((uri, prop, Literal(round(value, 6), datatype=XSD.decimal)))
            count += 1

    return count

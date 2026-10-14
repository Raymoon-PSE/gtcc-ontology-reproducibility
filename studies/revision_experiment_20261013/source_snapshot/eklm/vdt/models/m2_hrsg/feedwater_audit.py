"""Accounting for assumed feedwater states; does not supply missing heat/flows."""

def feedwater_audit(da, inlet, hp_pump, ip_pump, lp_feed):
    """Signed duties are positive into water; kg/hr, J/kg and kW throughout.

    Required external energy assumes zero storage and no other streams/work.
    A mass mismatch still requires an explicit flow model; heat cannot fix it.
    """
    pumps = {"HP": hp_pump, "IP": ip_pump}
    m_out = sum(p.s_out.m_dot for p in pumps.values()) + lp_feed.m_dot
    da_heat = (m_out * da.h_da - inlet.m_dot * inlet.h) / 3.6e6
    lp_heat = lp_feed.m_dot * (lp_feed.h - da.h_da) / 3.6e6
    residuals = {name: p.s_out.m_dot * (p.s_out.h - da.h_da) / 3.6e6 - p.W_bfp
                 for name, p in pumps.items()}
    return {
        "scope": "steady_feedwater_assumptions_no_blowdown_or_storage",
        "deaerator_inlet_kg_hr": inlet.m_dot,
        "deaerator_outlet_kg_hr": m_out,
        "deaerator_mass_balance_passed": abs(inlet.m_dot - m_out) < 1e-6,
        "deaerator_mass_residual_kg_hr": inlet.m_dot - m_out,
        "deaerator_required_external_heat_kW": da_heat,
        "lp_feed_required_external_heat_kW": lp_heat,
        "pump_energy_residual_kW": residuals,
        "pump_balances_passed": all(abs(r) < .01 for r in residuals.values()),
        "unmodeled_heat_paths_present": abs(da_heat) > .01 or abs(lp_heat) > .01,
        "whole_cycle_closed": False,
        "limitations": ["Required heat is diagnostic, not an implemented heater or cooler",
                        "No extraction, vent, makeup, blowdown or storage closure",
                        "Condensate pressure lift is outside this audit"],
    }

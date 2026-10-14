"""GUI adapter — converts params dict → solver call → result dict.

Bridges the GUI (dict-based) and the solver (dataclass-based).
All REQUIRED_KEYS from GUI Strategy v2.0 §5 are populated here.
"""

import warnings
import numpy as np
from CoolProp.CoolProp import PropsSI

from eklm.vdt.mechanical.operating_point import extract_operating_point
from eklm.vdt.mechanical.data_package import DataStatus, DeviceDataPackage
from eklm.vdt.mechanical.model_router import ModelRouter
from eklm.vdt.mechanical.reference_db import ReferenceDatabase
from eklm.vdt.mechanical.base import DeviceResult
from eklm.vdt.models.m1_gt.air_inlet import air_inlet
from eklm.vdt.models.m1_gt.compressor import compressor
from eklm.vdt.models.m1_gt.fuel_system import fuel_system
from eklm.vdt.models.m1_gt.combustor import combustor
from eklm.vdt.models.m1_gt.gt_expander import gt_expander
from eklm.vdt.models.m1_gt.gt_generator import gt_generator
from eklm.vdt.analysis.gtcc_loop import gtcc_solve, GTCCResult
from eklm.vdt.models.m2_hrsg.hrsg_solver import HRSGParams
from eklm.vdt.models.m3_st.st_solver import STParams
from eklm.vdt.models.m4_condenser.condenser_solver import CondenserParams
from eklm.vdt.data.streams import Stream
from eklm.vdt.data.species import h_mix, s_mix


# NETL reference values (hardcoded config)
NETL_REF = {
    "W_GT": 362_200, "W_ST": 202_500, "W_net": 555_080,
    "eta_net_HHV": 0.502,
}

# NETL Case 13 SCR efficiency (Exhibit 5-5). Applied to combustor-out
# NOx in the steady output so users see the realistic post-treatment
# 2.5 ppmvd figure by default. The unprocessed DLN value is reported
# separately as NOx_ppmvd_DLN.
SCR_EFFICIENCY: float = 0.9


# NETL Case 13 economic reference (DOE/NETL-2010/1397 Rev. 2a, 2007 dollars,
# no CO2 capture). Sources: Exhibit 5-13 Total Plant Cost Summary +
# §5.2.6 Cost Estimating.
#
# Field meanings (NETL convention):
#   TPC_per_kW    : Total Plant Cost per kW (Exhibit 5-13).
#   TOC_per_kW    : Total Overnight Cost per kW (§5.2.6 — TPC + owner's
#                   costs + preproduction; project contingency 8.6 % of TOC).
#   COE_mills_kWh : First-year cost of electricity (§5.2.6).
#   LCOE_mills_kWh: Levelized COE — EKLM internal (NETL Chapter 5 publishes
#                   only first-year COE; LCOE retained as a separate field
#                   for engineering use).
NETL_ECON = {
    "TPC_per_kW":     584,
    "TOC_per_kW":     718,
    "COE_mills_kWh":  58.9,
    "LCOE_mills_kWh": 56.8,
}

# Dead state for exergy
T0_C = 15.0
P0_MPA = 0.1013
T0_K = T0_C + 273.15


def _build_fuel_comp(params: dict) -> dict:
    """Build fuel mass fraction dict from GUI params."""
    w_NG = params.get("w_NG", 1.0)
    w_H2 = params.get("w_H2", 0.0)
    w_NH3 = params.get("w_NH3", 0.0)

    # NG sub-composition (NETL baseline, mass fractions)
    ng_base = {
        "CH4": 0.86205, "C2H6": 0.05553, "C3H8": 0.01781,
        "C4H10": 0.01342, "CO2": 0.02540, "N2": 0.02579,
    }
    fuel_comp = {}
    for k, v in ng_base.items():
        fuel_comp[k] = v * w_NG
    if w_H2 > 0:
        fuel_comp["H2"] = w_H2
    if w_NH3 > 0:
        fuel_comp["NH3"] = w_NH3
    return fuel_comp


# P1 device configurations: (device_id, device_type, unit_id)
_P1_DEVICES = [
    ("COMP-001", "Compressor", "1-2"),
    ("EXP-001", "GT_Turbine", "1-5"),
    ("COMB-001", "Combustor", "1-4"),
    ("HPSH-001", "HRSG_Superheater", "2-1"),
    ("RH-001", "Reheater", "2-4"),
    ("HPTURB", "HP_ST", "3-1"),
]

_ref_db = ReferenceDatabase()
_router = ModelRouter(_ref_db)


def run_mechanical(op, params: dict) -> list[DeviceResult]:
    """Run all P1 mechanical device models."""
    from eklm.vdt.mechanical.operating_point import OperatingPoint
    results = []
    for dev_id, dev_type, unit_id in _P1_DEVICES:
        pkg = DeviceDataPackage(
            device_id=dev_id,
            device_type=dev_type,
            unit_id=unit_id,
            required_params=_ref_db.get_defaults(dev_type),
            optional_params={},
        )
        model = _router.route(pkg)
        results.append(model.run(op))
    return results


# Frozen NETL design-point calibration. Do not re-fit these values at each
# changed condenser pressure: that would force 202.5 MW at every condition.
NETL_ST_CALIBRATED = (0.8177671638648989, 0.9183836674156912, 0.9183836674156912)


def run_gtcc(params: dict) -> tuple[dict, GTCCResult]:
    for key in ("T_amb", "P_amb", "m_fuel", "PR", "eta_comp", "eta_turb",
                "P_HP", "P_IP", "P_LP", "P_cond", "load_factor", "w_H2", "w_NH3", "w_NG",
                "eta_hpt", "eta_ipt", "eta_lpt"):
        if key in params and (isinstance(params[key], bool) or not isinstance(params[key], (int, float)) or not np.isfinite(params[key])):
            raise ValueError(f"{key} must be a finite number")
    load = params.get("load_factor", 1.0)
    if load <= 0 or load > 1:
        raise ValueError("load_factor must be in (0, 1]")
    if load != 1.0 and params.get("sim_mode") not in ("Mechanical", "Mechanical Analysis"):
        raise ValueError("Steady thermodynamic part-load is not implemented: load_factor must be 1.0. Use the dynamic simulator for load-setpoint response; it is not an off-design steady validation.")
    if params.get("m_fuel", 75901.) <= 0 or params.get("PR", 18.1) <= 1:
        raise ValueError("Positive fuel flow and compressor pressure ratio above 1 are required")
    for key in ("P_amb", "P_HP", "P_IP", "P_LP", "P_cond"):
        if params.get(key, 1.) <= 0:
            raise ValueError(f"{key} must be positive")
    for key in ("eta_comp", "eta_turb", "eta_hpt", "eta_ipt", "eta_lpt"):
        if key in params and (not np.isfinite(params[key]) or not 0 < params[key] <= 1):
            raise ValueError(f"{key} must be in (0, 1]")
    if any(not 0 <= params.get(k, 0.) <= 1 for k in ("w_H2", "w_NH3", "w_NG")) or params.get("w_H2", 0.) + params.get("w_NH3", 0.) > 1:
        raise ValueError("Fuel fractions must be in [0, 1] and H2 + NH3 must not exceed 1")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result, raw = _run_gtcc(params)
    messages = sorted(set(str(w.message) for w in captured))
    audit = raw.m2.thermal_audit
    result["hrsg_thermal_audit"] = audit
    feedwater = raw.m2.feedwater_audit
    result["feedwater_audit"] = feedwater
    result["condenser_water_audit"] = raw.m4.water_audit
    result["linked_cycle_audit"] = raw.m2.cycle_audit
    steam_production = raw.m2.s_is01.m_dot + raw.m2.unit_25.s_is04.m_dot + raw.m2.s_is05.m_dot
    bleed = steam_production - raw.m3.s28.m_dot
    inflows = raw.m4.water_audit["inlet_flows_kg_hr"]
    result["cycle_water_audit"] = {
        "scope": "steady_boundary_bookkeeping_unlinked_returns",
        "steam_production_kg_hr": steam_production,
        "turbine_bleed_export_kg_hr": bleed,
        "imposed_returns_and_makeup_kg_hr": sum(v for k, v in inflows.items() if k != "turbine_exhaust"),
        "net_boundary_inflow_kg_hr": raw.m4.s_is06.m_dot - steam_production,
        "whole_cycle_closed": False,
        "note": "Return sources are not linked to bleed or drum blowdown; no arbitrary flow adjustment applied",
    }
    if raw.m2.cycle_audit:
        linked=raw.m2.cycle_audit
        result["cycle_water_audit"] = dict(linked)
        result["cycle_water_audit"]["net_boundary_inflow_kg_hr"] = linked["deaerator_mass_residual_kg_hr"]
        result["cycle_water_audit"]["imposed_returns_and_makeup_kg_hr"] = inflows["makeup"] + inflows["gland_return"]
        messages.append("Linked water circuit: ideal DA, gland return and blowdown purge; stack temperature is solved from energy balance. Equipment/field validation remains incomplete.")
    cycle_water = result["cycle_water_audit"]
    if abs(cycle_water["net_boundary_inflow_kg_hr"]) > 1e-6:
        messages.append("Cycle water boundary: imposed returns and makeup "
                        f"{cycle_water['imposed_returns_and_makeup_kg_hr']:.1f} kg/hr versus bleed export "
                        f"{bleed:.1f} kg/hr; return sources are not linked to upstream extraction or blowdown.")
    if not feedwater["deaerator_mass_balance_passed"]:
        messages.append(f"Deaerator has {feedwater['deaerator_mass_residual_kg_hr']:.1f} kg/hr of unmodeled net inlet flow; required heat assumes zero storage and cannot close this mass gap.")
    if feedwater["unmodeled_heat_paths_present"]:
        messages.append("Feedwater energy closure incomplete: deaerator requires "
                        f"{feedwater['deaerator_required_external_heat_kW']:.1f} kW and LP feed conditioning "
                        f"{feedwater['lp_feed_required_external_heat_kW']:.1f} kW of unmodeled external heat "
                        "(negative means cooling); local exchanger checks do not close the whole cycle.")
    for unit in audit["units"]:
        if not unit["local_balance_passed"]:
            messages.append(f"HRSG {unit['unit']}: gas/water heat or mass balance mismatch")
        if not unit["endpoint_screen_passed"]:
            messages.append(f"HRSG {unit['unit']}: thermally infeasible endpoint temperatures or heat direction "
                f"(hot-end approach {unit['hot_end_approach_C']:.2f} C, cold-end {unit['cold_end_approach_C']:.2f} C)")
    result["model_warnings"] = messages
    result["validation_scope"] = {
        "status": "model_warnings" if messages else "reference_calibrated_prototype",
        "hrsg_local_balances_passed": audit["local_balances_passed"],
        "hrsg_endpoint_screen_passed": audit["endpoint_screen_passed"],
        "field_validated": False,
        "feedwater_whole_cycle_closed": feedwater["whole_cycle_closed"],
        "st_efficiency_basis": "explicit_input" if all(k in params for k in ("eta_hpt", "eta_ipt", "eta_lpt")) else "NETL_design_point_calibration_fixed_across_cases",
        "calibration_targets": ["ST design gross power 202500 kW", "cold reheat temperature 308.8 C"],
        "independent_validation": False,
        "part_load_thermodynamics_supported": False,
        "energy_balance_note": "Unaccounted energy is a signed residual, not independently calculated radiation loss.",
    }
    if audit["thermal_mode"] in ("bounded", "linked"):
        result["validation_scope"]["status"] = "endpoint_screened_prototype"
        result["validation_scope"]["st_efficiency_basis"] += "_not_refitted_for_bounded_hrsg"
    if audit["thermal_mode"] == "linked":
        result["validation_scope"]["status"] = "water_cycle_balanced_prototype"
    if not audit["local_balances_passed"] or not audit["endpoint_screen_passed"]:
        result["validation_scope"]["status"] = "physically_inconsistent"
    if load != 1:
        result["model_warnings"].append("load_factor affects mechanical assessment only; thermodynamics remain at the entered design flows")
        if result["validation_scope"]["status"] != "physically_inconsistent":
            result["validation_scope"]["status"] = "model_warnings"
    for w in captured:
        warnings.warn(str(w.message), w.category, stacklevel=2)
    return result, raw


def _run_gtcc(params: dict) -> tuple[dict, GTCCResult]:
    """Run full GTCC simulation from GUI params.

    Args:
        params: dict from sidebar (see GUI Strategy §3).

    Returns:
        (result_dict, result_obj) — dict for GUI display, GTCCResult for Ontology.
    """
    # Validate declared engineering bindings before any physical calculation.
    # Opt-in with ontology_runtime, preserving the ordinary simulator path.
    if params.get("ontology_runtime", False):
        from eklm.kas.legacy_bridge.graph import load_graph
        from eklm.kas.legacy_bridge.integrity import require_valid_graph, clear_runtime_evidence
        params = dict(params)
        g = params.get("ontology_graph")
        if g is None:
            g = load_graph(params.get("ontology_dir"))
        clear_runtime_evidence(g)
        require_valid_graph(g, params.get("engineering_contract"))
        params["ontology_graph"] = g

    # Build inputs
    fuel_comp = _build_fuel_comp(params)
    ambient = Stream(
        T=params.get("T_amb", 15.0),
        P=params.get("P_amb", 0.1013),
        m_dot=3_154_735,
        w={"N2": 0.7732, "O2": 0.2074, "CO2": 0.0003, "H2O": 0.0099, "Ar": 0.0092},
    )
    fuel = Stream(
        T=params.get("T_fuel", 38.0), P=3.10,
        m_dot=params.get("m_fuel", 75_901.0), w=fuel_comp,
    )

    # M1 GT
    s2 = air_inlet(ambient)
    s3, _, W_comp = compressor(s2, PR=params.get("PR", 18.1),
                                eta=params.get("eta_comp", 0.845))
    fs = fuel_system(fuel)
    cmb = combustor(s3=s3, s5=fs.s5, LHV_f=fs.LHV_blend,
                    nu_O2_blend=fs.nu_O2_blend, eta_comb=0.998, delta_comb=0.03)
    s7, W_turb = gt_expander(s6=cmb.s6, s_bleed=None,
                             eta_turb=params.get("eta_turb", 0.876), P_7=0.1048)
    _, W_GT = gt_generator(W_turb=W_turb, W_comp=W_comp, eta_gen=0.984)

    # GTCC convergence
    hrsg_p = HRSGParams(
        thermal_mode=params.get("hrsg_thermal_mode","prescribed"),
        blowdown_fraction=params.get("blowdown_fraction",.02),
        min_approach_C=params.get("hrsg_min_approach_C",10.0),
        P_HP=params.get("P_HP", 16.65),
        P_IP=params.get("P_IP", 2.482),
        P_LP=params.get("P_LP", 0.655),
        PTD_HP=params.get("PTD_HP", 10.0),
        PTD_IP=params.get("PTD_IP", 10.0),
    )
    cond_p = CondenserParams(
        P_cond=params.get("P_cond", 0.00677),
        T_cw_in=params.get("T_cw_in", 18.3),
    )

    st_p = STParams(P_28=cond_p.P_cond,
        eta_hpt=params.get("eta_hpt", NETL_ST_CALIBRATED[0]),
        eta_ipt=params.get("eta_ipt", NETL_ST_CALIBRATED[1]),
        eta_lpt=params.get("eta_lpt", NETL_ST_CALIBRATED[2]))
    # Fuel input includes the unreleased combustion loss. Using Q_comb here
    # would overstate both LHV and HHV efficiencies by 1 / eta_comb.
    fuel_input_kW = fs.s5.m_dot * fs.LHV_blend / 3600.0
    r = gtcc_solve(s7, W_GT, fuel_input_kW, hrsg_params=hrsg_p, st_params=st_p, cond_params=cond_p)

    # Build result dict
    d = _build_result_dict(r, s2, s3, cmb, s7, W_comp, W_turb, W_GT, fs,
                           ambient=ambient)

    # Attach OperatingPoint for Mechanical Model
    r.operating_point = extract_operating_point(
        s2=s2, s3=s3, s6=cmb.s6,
        W_comp=W_comp, W_GT=W_GT, r=r,
        load_factor=params.get("load_factor", 1.0),
        cumulative_hours=params.get("cumulative_hours", 0.0),
        start_stop_count=params.get("start_stop_count", 0),
    )

    # Opt-in ontology orchestration also runs mechanical models and diagnosis.
    if params.get("ontology_runtime", False):
        from eklm.kas.legacy_bridge.runtime import execute_runtime
        execute_runtime(d, r, params)
    elif params.get("sim_mode") in ("Mechanical", "Mechanical Analysis"):
        mech_results = run_mechanical(r.operating_point, params)
        d["mech_results"] = mech_results
        for mr in mech_results:
            d.update(mr.outputs)

    return d, r


def _stream_dict(sid: str, desc: str, s: Stream, phase: str = "gas") -> dict:
    d = {
        "id": sid, "desc": desc,
        "T": s.T, "P": s.P, "m_dot": s.m_dot,
        "h": s.h / 1000 if s.h else None,
        "s": s.s / 1000 if s.s else None,
        "x": None, "phase": phase,
    }
    # Composition (mass fractions) — always include if available
    if hasattr(s, "w") and s.w:
        d["w"] = dict(s.w)
    return d


def _build_result_dict(r: GTCCResult, s2, s3, cmb, s7,
                       W_comp, W_turb, W_GT, fs,
                       ambient=None) -> dict:
    """Convert GTCCResult to flat dict with all REQUIRED_KEYS."""
    d = {}

    # C5 Performance
    d["W_GT"] = W_GT
    d["W_ST"] = r.m3.W_ST
    d["W_net"] = r.W_net
    d["W_CWS"] = r.m4.W_CWS
    d["W_BFP"] = r.m2.W_bfp_total
    d["W_CP"] = r.m4.W_cp
    d["W_GT_aux"] = 0.0       # Phase 2
    d["W_ST_aux"] = 0.0       # Phase 2
    d["W_misc_bop"] = 500.0   # NETL fixed
    d["eta_net_LHV"] = r.eta_net
    Q_fuel_hhv = r.Q_fuel * (fs.HHV_blend / fs.LHV_blend) if fs.LHV_blend > 0 else r.Q_fuel
    d["eta_net_HHV"] = r.W_net / Q_fuel_hhv if Q_fuel_hhv > 0 else 0
    d["eta_hpt"] = r.m3.eta_hpt
    d["eta_ipt"] = r.m3.eta_ipt
    d["eta_lpt"] = r.m3.eta_lpt
    d["T_stack"] = r.m2.T_stack
    d["convergence_iter"] = r.iterations
    d["x_28"] = r.m3.x_28

    # C6 Economic (NETL reference, read-only Phase 1)
    d.update(NETL_ECON)

    # C9 Environmental
    co2_w = cmb.s6.w.get("CO2", 0) if hasattr(cmb, "s6") else 0
    m_dot_co2 = r.s7.m_dot * co2_w  # kg/hr
    d["CO2_total_thr"] = m_dot_co2 / 1000  # t/hr
    d["CO2_kg_MWh"] = (m_dot_co2 / (r.W_net / 1000)) if r.W_net > 0 else 0
    # NOx: report combustor-out (DLN only) AND post-SCR. NETL Case 13 uses
    # SCR with 90 % NOx reduction, giving the published 2.5 ppmvd figure.
    nox_dln = getattr(cmb, "NOx_15pct", 25.0) if hasattr(cmb, "NOx_15pct") else 25.0
    d["NOx_ppmvd_DLN"] = nox_dln                # bare DLN value
    d["NOx_ppmvd"] = nox_dln * (1.0 - SCR_EFFICIENCY)   # post-SCR (matches NETL)
    d["CW_consumption_m3min"] = r.m4.m_dot_muw / 1000 / 60  # kg/hr → m3/min

    # C3 Streams — complete list in process flow order
    streams = []
    # GT Module (M1) — air side
    streams.append(_stream_dict("S1", "Ambient Air", ambient, "gas"))
    streams.append(_stream_dict("S2", "Conditioned Air", s2, "gas"))
    streams.append(_stream_dict("S3", "Compressed Air", s3, "gas"))
    # GT Module (M1) — fuel & combustor
    streams.append(_stream_dict("S5", "Fuel to Combustor", fs.s5, "gas"))
    streams.append(_stream_dict("S6", "Combustor Exit (TIT)", cmb.s6, "gas"))
    streams.append(_stream_dict("S7", "GT Exhaust", r.s7, "gas"))
    # HRSG gas-side (M2)
    streams.append(_stream_dict("S8", "FG after HP SH", r.m2.unit_21.s8, "gas"))
    streams.append(_stream_dict("S9", "FG after Reheater", r.m2.unit_24.s9, "gas"))
    streams.append(_stream_dict("S10", "FG after HP Evap", r.m2.unit_22.s10, "gas"))
    streams.append(_stream_dict("S11", "FG after IP SH", r.m2.unit_25.s11, "gas"))
    streams.append(_stream_dict("S12", "FG after HP Eco", r.m2.unit_23.s12, "gas"))
    streams.append(_stream_dict("S13", "FG after IP Evap", r.m2.unit_26.s13, "gas"))
    streams.append(_stream_dict("S14", "FG after IP Eco", r.m2.unit_27.s14, "gas"))
    streams.append(_stream_dict("S15", "FG after LP Evap", r.m2.unit_28.s15, "gas"))
    streams.append(_stream_dict("S16", "Stack Gas", r.m2.s16, "gas"))
    # HRSG steam-side interfaces
    streams.append(_stream_dict("IS-01", "HP Main Steam", r.m2.s_is01, "steam"))
    streams.append(_stream_dict("IS-02", "Cold Reheat", r.m3.s_is02, "steam"))
    streams.append(_stream_dict("IS-03", "Hot Reheat", r.m2.s_is03, "steam"))
    streams.append(_stream_dict("IS-05", "LP Steam", r.m2.s_is05, "steam"))
    streams.append(_stream_dict("IS-06", "Condensate", r.m4.s_is06, "water"))
    # ST internal (M3)
    streams.append(_stream_dict("S25", "HP Turb Exit", r.m3.unit_31.s25, "steam"))
    streams.append(_stream_dict("S26", "IP Turb Exit", r.m3.unit_33.s26, "steam"))
    streams.append(_stream_dict("S27", "LP Turb Inlet", r.m3.node_3m.s27, "steam"))
    s28_dict = _stream_dict("S-028", "ST Exhaust", r.m3.s28, "two-phase")
    s28_dict["x"] = r.m3.x_28
    streams.append(s28_dict)
    d["streams"] = streams

    # HRSG duties
    duties = [
        {"unit_id": "2-1", "name": "HP Superheater", "Q_kW": r.m2.unit_21.Q_dot},
        {"unit_id": "2-4", "name": "Reheater", "Q_kW": r.m2.unit_24.Q_dot},
        {"unit_id": "2-2", "name": "HP Evaporator", "Q_kW": r.m2.unit_22.Q_dot},
        {"unit_id": "2-5", "name": "IP Superheater", "Q_kW": r.m2.unit_25.Q_dot},
        {"unit_id": "2-3", "name": "HP Economizer", "Q_kW": r.m2.unit_23.Q_dot},
        {"unit_id": "2-6", "name": "IP Evaporator", "Q_kW": r.m2.unit_26.Q_dot},
        {"unit_id": "2-7", "name": "IP Economizer", "Q_kW": r.m2.unit_27.Q_dot},
        {"unit_id": "2-8", "name": "LP Evaporator", "Q_kW": r.m2.unit_28.Q_dot},
        {"unit_id": "2-9", "name": "LP Economizer", "Q_kW": r.m2.unit_29.Q_dot},
    ]
    d["hrsg_duties"] = duties

    # Gas temperature profile
    d["gas_T_profile"] = [
        r.s7.T, r.m2.unit_21.s8.T, r.m2.unit_24.s9.T,
        r.m2.unit_22.s10.T, r.m2.unit_25.s11.T,
        r.m2.unit_23.s12.T, r.m2.unit_26.s13.T,
        r.m2.unit_27.s14.T, r.m2.unit_28.s15.T,
        r.m2.s16.T,
    ]

    # Sankey energy data
    d["Q_fuel"] = r.Q_fuel
    d["Q_combustion_release"] = cmb.Q_comb
    # Stack sensible enthalpy above the stated ambient reference, not the
    # LP economizer duty (S15 minus S16).
    stack_reference_K = (ambient.T + 273.15) if ambient is not None else T0_K
    d["Q_stack_loss"] = r.m2.s16.m_dot * (r.m2.s16.h - h_mix(stack_reference_K, r.m2.s16.w)) / 3.6e6
    d["Q_condenser"] = r.m4.Q_cond
    d["Q_unaccounted_balance"] = (r.Q_fuel - W_GT - r.m3.W_ST
                                 - d["Q_stack_loss"] - d["Q_condenser"])
    d["Q_radiation_loss"] = max(0., d["Q_unaccounted_balance"])  # legacy display alias only

    # T-Q diagram data (cumulative Q along gas path)
    _build_tq_data(d, r)

    # GT cycle T-s
    d["gt_cycle_Ts"] = [
        {"T": s2.T, "s": s2.s / 1000 if s2.s else 0, "label": "1 Ambient"},
        {"T": s3.T, "s": s3.s / 1000 if s3.s else 0, "label": "2 Comp out"},
        {"T": cmb.s6.T, "s": cmb.s6.s / 1000 if cmb.s6.s else 0, "label": "3 TIT"},
        {"T": r.s7.T, "s": r.s7.s / 1000 if r.s7.s else 0, "label": "4 GT exh"},
    ]

    # ST cycle T-s and P-h
    _build_st_cycle_data(d, r)

    # Saturation curve
    _build_sat_curve(d)

    # Exergy (system-level, Kotas 1995 chemical exergy for NG/H2/NH3 blends)
    _build_exergy_data(d, r, fuel_stream=fs.s5)

    return d


def _build_tq_data(d: dict, r: GTCCResult) -> None:
    """Build T-Q diagram data for HRSG."""
    # Gas side: cumulative Q from S7 to S16
    units = [r.m2.unit_21, r.m2.unit_24, r.m2.unit_22, r.m2.unit_25,
             r.m2.unit_23, r.m2.unit_26, r.m2.unit_27, r.m2.unit_28, r.m2.unit_29]
    gas_temps = [r.s7.T]
    gas_Q = [0.0]
    Q_cum = 0.0
    for u in units:
        Q_cum += u.Q_dot
        gas_Q.append(Q_cum)
        # Get gas outlet temp from each unit
    gas_temps.extend([
        r.m2.unit_21.s8.T, r.m2.unit_24.s9.T, r.m2.unit_22.s10.T,
        r.m2.unit_25.s11.T, r.m2.unit_23.s12.T, r.m2.unit_26.s13.T,
        r.m2.unit_27.s14.T, r.m2.unit_28.s15.T, r.m2.s16.T,
    ])
    d["tq_gas_Q"] = gas_Q
    d["tq_gas_T"] = gas_temps

    # Steam side (simplified: key points at each unit boundary)
    from eklm.vdt.data.properties import T_sat_water
    T_sat_hp = T_sat_water(r.m2.unit_22.s19.P)
    T_sat_ip = T_sat_water(r.m2.unit_26.s22.P)
    T_sat_lp = T_sat_water(r.m2.unit_28.s_is05.P)

    # Pinch points
    d["pinch_points"] = [
        {"Q": gas_Q[3], "T_gas": r.m2.unit_22.s10.T, "T_steam": T_sat_hp,
         "PTD": r.m2.unit_22.PTD, "unit": "HP Evap"},
        {"Q": gas_Q[6], "T_gas": r.m2.unit_26.s13.T, "T_steam": T_sat_ip,
         "PTD": r.m2.unit_26.PTD, "unit": "IP Evap"},
        {"Q": gas_Q[8], "T_gas": r.m2.unit_28.s15.T, "T_steam": T_sat_lp,
         "PTD": r.m2.unit_28.PTD, "unit": "LP Evap"},
    ]

    # Simplified steam-side T-Q (mirror of gas Q axis at key temperatures)
    d["tq_steam_Q"] = gas_Q
    d["tq_steam_T"] = [
        r.m2.s_is01.T,   # HP SH outlet
        T_sat_hp + 20,    # after RH (approx)
        T_sat_hp,         # HP evap out (sat)
        T_sat_hp,         # HP evap in (sat)
        T_sat_ip + 10,    # IP SH region
        r.m2.unit_23.s17.T,  # HP Eco inlet
        T_sat_ip,         # IP evap
        r.m2.unit_27.s20.T,  # IP Eco inlet
        T_sat_lp,         # LP evap
        r.m4.s_is06.T,    # condensate
    ]


def _build_st_cycle_data(d: dict, r: GTCCResult) -> None:
    """Build ST T-s and P-h data for cycle diagrams."""
    def _pt(T, s, h, P, circuit, label):
        return {"T": T, "s": s/1000 if s else 0, "h": h/1000 if h else 0,
                "P": P, "circuit": circuit, "label": label}

    st_ts = []
    st_ph = []

    # HP circuit: IS-01 → S25 (expansion) → IS-02 (CRH) → IS-03 (reheat)
    st_ts.append(_pt(r.m2.s_is01.T, r.m2.s_is01.s, r.m2.s_is01.h,
                     r.m2.s_is01.P, "HP", "IS-01"))
    st_ts.append(_pt(r.m3.unit_31.s25.T, r.m3.unit_31.s25.s, r.m3.unit_31.s25.h,
                     r.m3.unit_31.s25.P, "HP", "S25"))
    st_ph.append(_pt(r.m2.s_is01.T, r.m2.s_is01.s, r.m2.s_is01.h,
                     r.m2.s_is01.P, "HP", "IS-01"))
    st_ph.append(_pt(r.m3.unit_31.s25.T, r.m3.unit_31.s25.s, r.m3.unit_31.s25.h,
                     r.m3.unit_31.s25.P, "HP", "S25"))

    # IP circuit: IS-03 → S26
    st_ts.append(_pt(r.m2.s_is03.T, r.m2.s_is03.s, r.m2.s_is03.h,
                     r.m2.s_is03.P, "IP", "IS-03"))
    st_ts.append(_pt(r.m3.unit_33.s26.T, r.m3.unit_33.s26.s, r.m3.unit_33.s26.h,
                     r.m3.unit_33.s26.P, "IP", "S26"))
    st_ph.append(_pt(r.m2.s_is03.T, r.m2.s_is03.s, r.m2.s_is03.h,
                     r.m2.s_is03.P, "IP", "IS-03"))
    st_ph.append(_pt(r.m3.unit_33.s26.T, r.m3.unit_33.s26.s, r.m3.unit_33.s26.h,
                     r.m3.unit_33.s26.P, "IP", "S26"))

    # LP circuit: S27 → S28
    st_ts.append(_pt(r.m3.node_3m.s27.T, r.m3.node_3m.s27.s, r.m3.node_3m.s27.h,
                     r.m3.node_3m.s27.P, "LP", "S27"))
    st_ts.append(_pt(r.m3.s28.T, r.m3.s28.s, r.m3.s28.h,
                     r.m3.s28.P, "LP", "S28"))
    st_ph.append(_pt(r.m3.node_3m.s27.T, r.m3.node_3m.s27.s, r.m3.node_3m.s27.h,
                     r.m3.node_3m.s27.P, "LP", "S27"))
    st_ph.append(_pt(r.m3.s28.T, r.m3.s28.s, r.m3.s28.h,
                     r.m3.s28.P, "LP", "S28"))

    d["st_cycle_Ts"] = st_ts
    d["st_cycle_Ph"] = st_ph


def _build_sat_curve(d: dict) -> None:
    """Generate water saturation dome data (cached at module level)."""
    T_range = np.linspace(5, 370, 150)
    sat_T, s_liq, s_vap = [], [], []
    sat_P, h_liq, h_vap = [], [], []
    for T in T_range:
        try:
            T_K = T + 273.15
            sat_T.append(T)
            s_liq.append(PropsSI("S", "T", T_K, "Q", 0, "Water") / 1000)
            s_vap.append(PropsSI("S", "T", T_K, "Q", 1, "Water") / 1000)
            sat_P.append(PropsSI("P", "T", T_K, "Q", 0, "Water") / 1e6)
            h_liq.append(PropsSI("H", "T", T_K, "Q", 0, "Water") / 1000)
            h_vap.append(PropsSI("H", "T", T_K, "Q", 1, "Water") / 1000)
        except Exception:
            break
    d["sat_curve_T"] = sat_T
    d["sat_curve_s_liq"] = s_liq
    d["sat_curve_s_vap"] = s_vap
    d["sat_curve_P"] = sat_P
    d["sat_curve_h_liq"] = h_liq
    d["sat_curve_h_vap"] = h_vap


# Chemical exergy of fuels per Kotas (1995),
# "The Exergy Method of Thermal Plant Analysis", 2nd ed. (kJ/kg).
# NG value is the industry-typical mixture; blend weighting follows below.
E_CH_KOTAS_KJ_KG = {
    "NG": 51810.0,    # ratio e_ch/LHV_NG ≈ 1.058
    "H2": 117100.0,   # ratio e_ch/LHV_H2 ≈ 0.976
    "NH3": 19870.0,   # ratio e_ch/LHV_NH3 ≈ 1.068
}


def _fuel_chemical_exergy_rate_kW(fuel_stream) -> float:
    """Fuel chemical exergy rate [kW] from blend weighted Kotas values.

    fuel_stream.w : mass-fraction dict {CH4, C2H6, ..., H2, NH3}
    fuel_stream.m_dot : kg/hr
    """
    w = fuel_stream.w or {}
    w_H2 = float(w.get("H2", 0.0))
    w_NH3 = float(w.get("NH3", 0.0))
    w_NG = max(0.0, 1.0 - w_H2 - w_NH3)  # remaining mass is NG sub-composition
    e_ch = (w_NG * E_CH_KOTAS_KJ_KG["NG"]
            + w_H2 * E_CH_KOTAS_KJ_KG["H2"]
            + w_NH3 * E_CH_KOTAS_KJ_KG["NH3"])
    # m_dot [kg/hr] / 3600 = kg/s; kg/s × kJ/kg = kJ/s = kW
    return fuel_stream.m_dot * e_ch / 3600.0


def _build_exergy_data(d: dict, r: GTCCResult, fuel_stream=None) -> None:
    """System-level exergy calculation for boundary streams + fuel.

    Args:
        d : result dict to populate
        r : GTCC solver result
        fuel_stream : fuel Stream (fs.s5); if None, fallback NG-only approx.
    """
    # Reference state
    h0_gas = h_mix(T0_K, r.s7.w)
    s0_gas = s_mix(T0_K, P0_MPA * 1e6, r.s7.w)
    h0_water = PropsSI("H", "T", T0_K, "P", P0_MPA * 1e6, "Water")
    s0_water = PropsSI("S", "T", T0_K, "P", P0_MPA * 1e6, "Water")

    def _ex_gas(s: Stream) -> float:
        if s.h is None or s.s is None:
            return 0.0
        e = (s.h - h0_gas) - T0_K * (s.s - s0_gas)  # J/kg
        return s.m_dot * e / 3.6e6  # kW

    def _ex_water(s: Stream) -> float:
        if s.h is None or s.s is None:
            return 0.0
        e = (s.h - h0_water) - T0_K * (s.s - s0_water)  # J/kg
        return s.m_dot * e / 3.6e6  # kW

    exergy_streams = {
        "S7": _ex_gas(r.s7),
        "S16": _ex_gas(r.m2.s16),
        "IS-01": _ex_water(r.m2.s_is01),
        "IS-02": _ex_water(r.m3.s_is02),
        "IS-03": _ex_water(r.m2.s_is03),
        "IS-05": _ex_water(r.m2.s_is05),
        "S28": _ex_water(r.m3.s28),
        "IS-06": _ex_water(r.m4.s_is06),
    }
    d["exergy_streams"] = exergy_streams

    # Fuel chemical exergy (Kotas 1995 blend-weighted) with fallback
    if fuel_stream is not None:
        E_fuel = _fuel_chemical_exergy_rate_kW(fuel_stream)
    else:
        E_fuel = r.Q_fuel * 1.04  # legacy NG-only approximation
    E_product = r.W_net
    d["exergy_fuel"] = E_fuel
    d["exergy_product"] = E_product
    d["exergy_efficiency"] = E_product / E_fuel if E_fuel > 0 else 0

    # Per-unit exergy destruction. Each formula is a 2nd-law balance on the
    # control volume:  Ed = (Σ exergy_in) - (Σ exergy_out) - (work delivered).
    # Earlier versions of this block mixed energy (Q_total, Q_condenser) into
    # exergy balances, which produced negative HRSG destruction (a 2nd-law
    # violation) and an artificially small condenser destruction.

    E_s7 = exergy_streams["S7"]            # GT exhaust into HRSG (gas)
    E_s16 = exergy_streams["S16"]           # HRSG stack out (gas)
    E_is01 = exergy_streams["IS-01"]        # HRSG → HPT (HP main steam)
    E_is02 = exergy_streams["IS-02"]        # HPT exit → HRSG (cold reheat)
    E_is03 = exergy_streams["IS-03"]        # HRSG reheater → IPT (hot reheat)
    E_is05 = exergy_streams["IS-05"]        # HRSG → LPT (LP steam)
    E_s28 = exergy_streams["S28"]           # LPT exit → Condenser
    E_is06 = exergy_streams["IS-06"]        # Condenser → HRSG (condensate)

    W_GT_val = d["W_GT"]
    W_ST_val = d["W_ST"]
    Q_cond = d["Q_condenser"]

    # Cooling-water (sink) for condenser exergy of heat rejection.
    # T_cw_avg ≈ 30 °C, T0 ≈ 25 °C → Carnot factor ~1.6 % of Q_cond (small,
    # but non-zero and physically meaningful).
    T0_amb_K = 298.15
    T_cw_avg_K = 303.15  # ~30 °C average between 16 °C in and 27 °C out
    ex_qcond = max(0.0, Q_cond * (1.0 - T0_amb_K / T_cw_avg_K))

    # GT  : fuel exergy in − GT-exhaust exergy out − shaft work
    ed_gt = E_fuel - E_s7 - W_GT_val
    # HRSG: gas exergy lost − steam-side exergy gained
    #   gas: E_s7 (in) − E_s16 (out)
    #   steam in (returning): IS-06 (condensate) + IS-02 (cold reheat from HPT)
    #   steam out (delivered to ST): IS-01 + IS-03 + IS-05
    ex_steam_gain_hrsg = (E_is01 + E_is03 + E_is05) - (E_is06 + E_is02)
    ed_hrsg = (E_s7 - E_s16) - ex_steam_gain_hrsg
    # ST  : steam exergy lost − shaft work
    #   steam in: IS-01 + IS-03 + IS-05
    #   steam out: IS-02 (back to HRSG reheat) + S28 (to condenser)
    ed_st = (E_is01 + E_is03 + E_is05) - (E_is02 + E_s28) - W_ST_val
    # Cond: steam exergy lost − exergy of heat rejected to cooling water
    ed_cond = (E_s28 - E_is06) - ex_qcond

    def _pct(x: float) -> float:
        return x / E_fuel * 100.0 if E_fuel > 0 else 0.0

    d["exergy_destruction"] = [
        {"unit": "GT (M1)",       "Ed_kW": ed_gt,   "Ed_pct": _pct(ed_gt)},
        {"unit": "HRSG (M2)",     "Ed_kW": ed_hrsg, "Ed_pct": _pct(ed_hrsg)},
        {"unit": "ST (M3)",       "Ed_kW": ed_st,   "Ed_pct": _pct(ed_st)},
        {"unit": "Condenser (M4)","Ed_kW": ed_cond, "Ed_pct": _pct(ed_cond)},
    ]

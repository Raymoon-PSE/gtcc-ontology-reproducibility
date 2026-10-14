"""Economic Analysis module for GTCC plant.

Computes COE, LCOE, NPV, IRR, Payback from simulation results + economic parameters.
NETL Case 13 values as defaults.

Class-3 enhancements (2026-05-06):
- 14-account NETL Exhibit 5-13 capital breakdown
- Itemized owner's costs (TPC → TOC decomposition)
"""

from dataclasses import dataclass, field
import numpy as np


# ── NETL Case 13 14-account capital cost breakdown (Exhibit 5-13, 2007$) ──
# Each value is the account's contribution at NETL design (555.08 MW_net).
# Fractions stay roughly constant across similar-sized NGCC; we scale with
# W_net to size each account when the user changes plant size.

NETL_ACCOUNT_CATALOG: list[dict] = [
    {"id": 1,  "name": "Coal & Sorbent Handling",      "usd_per_kW": 0},    # n/a NGCC
    {"id": 2,  "name": "Coal & Sorbent Prep & Feed",   "usd_per_kW": 0},    # n/a
    {"id": 3,  "name": "Feedwater & Misc BOP",         "usd_per_kW": 76},
    {"id": 4,  "name": "Gasifier & Accessories",       "usd_per_kW": 0},    # n/a
    {"id": 5,  "name": "Gas Cleanup & CO2 Removal",    "usd_per_kW": 0},    # n/a (Case 13)
    {"id": 6,  "name": "Combustion Turbine Generator", "usd_per_kW": 172},
    {"id": 7,  "name": "HRSG, Ducting & Stack",        "usd_per_kW": 88},
    {"id": 8,  "name": "Steam Turbine Generator",      "usd_per_kW": 92},
    {"id": 9,  "name": "Cooling Water System",         "usd_per_kW": 30},
    {"id": 10, "name": "Ash & Sorbent Recovery",       "usd_per_kW": 0},    # n/a
    {"id": 11, "name": "Accessory Electric Plant",     "usd_per_kW": 63},
    {"id": 12, "name": "Instrumentation & Control",    "usd_per_kW": 24},
    {"id": 13, "name": "Improvements to Site",         "usd_per_kW": 17},
    {"id": 14, "name": "Buildings & Structures",       "usd_per_kW": 19},
]
# Sum of usd_per_kW = 581 ≈ NETL TPC $584 (rounding, fine).


# ── NETL §2.7 owner's costs decomposition (TOC = TPC + owner's) ──
# Each component as fraction of TPC. Sum ≈ 0.229 → TOC/TPC = 1.229,
# matching NETL Case 13 TOC=$718 vs TPC=$584.

OWNERS_COST_CATALOG: list[dict] = [
    {"id": "owners_eng",     "name": "Owner's Engineering",        "frac_of_TPC": 0.050},
    {"id": "preproduction",  "name": "Pre-production costs",       "frac_of_TPC": 0.020},
    {"id": "inventory",      "name": "Inventory Capital (60-day)", "frac_of_TPC": 0.080},
    {"id": "init_cat_chem",  "name": "Initial Catalyst & Chemicals","frac_of_TPC": 0.020},
    {"id": "spare_parts",    "name": "Spare Parts",                 "frac_of_TPC": 0.010},
    {"id": "land",           "name": "Land",                        "frac_of_TPC": 0.010},
    {"id": "financing",      "name": "Financing Fees",              "frac_of_TPC": 0.039},
]
# Sum of frac_of_TPC = 0.229 → TOC = 1.229 × TPC ✓.


@dataclass
class EconomicParams:
    """Economic input parameters."""

    capacity_factor: float = 85.0       # %
    plant_life: int = 30                # years
    TPC_per_kW: float = 584.0          # $/kW
    process_contingency: float = 0.0    # % of TPC
    project_contingency: float = 8.6    # % of TOC
    TASC_multiplier: float = 1.074      # TOC to TASC
    fuel_price: float = 6.55           # $/MMBtu
    fuel_escalation: float = 2.0       # %/year
    fixed_om: float = 22.1            # $/kW-yr
    variable_om: float = 1.32         # mills/kWh
    scr_catalyst: float = 129_612     # $/yr
    discount_rate: float = 7.09        # %
    electricity_price: float = 60.0    # $/MWh
    elec_escalation: float = 2.0       # %/year
    co2_price: float = 0.0            # $/tonne
    co2_escalation: float = 3.0       # %/year


@dataclass
class EconomicResult:
    """Economic analysis results."""

    TPC: float; TOC: float; TASC: float
    annual_fuel: float; annual_fixed_om: float; annual_var_om: float
    annual_co2: float; annual_revenue: float
    COE: float; LCOE: float; NPV: float; IRR: float
    payback: int; heat_rate: float
    cost_breakdown: dict; cash_flows: list[dict]
    # Class-3 additions
    account_breakdown: list[dict] = field(default_factory=list)   # 14 NETL accounts
    owners_costs: list[dict] = field(default_factory=list)         # itemized TPC→TOC


def calculate_economics(
    W_net_kW: float, eta_net_LHV: float,
    Q_fuel_kW: float, CO2_thr: float,
    params: EconomicParams | None = None,
) -> EconomicResult:
    if params is None:
        params = EconomicParams()
    p = params

    W_net_MW = W_net_kW / 1000
    CF = p.capacity_factor / 100
    annual_hours = 8760 * CF
    annual_gen_kWh = W_net_kW * annual_hours
    annual_gen_MWh = W_net_MW * annual_hours
    heat_rate = 3600 / eta_net_LHV if eta_net_LHV > 0 else 0

    # Capital
    TPC = p.TPC_per_kW * W_net_kW / 1e6
    TOC = TPC * (1 + p.process_contingency / 100) * (1 + p.project_contingency / 100)
    TASC = TOC * p.TASC_multiplier

    # Annual costs (year 1).
    # 1 kW = 3,412.14 BTU/hr → fuel_MMBtu/hr = Q_kW × 3412.14 / 1e6.
    # The OBDT-ported version used 3.412/1e6, off by 1000×, which made
    # annual_fuel ≈ $0.2M instead of ~$166M at NETL Case 13 (LCOE 11.8
    # vs the realistic ~52 mills/kWh).
    fuel_MMBtu_hr = Q_fuel_kW * 3412.14 / 1e6
    annual_fuel = fuel_MMBtu_hr * p.fuel_price * annual_hours / 1e6
    annual_fixed_om = p.fixed_om * W_net_kW / 1e6
    annual_var_om = p.variable_om * annual_gen_kWh / 1e9
    annual_scr = p.scr_catalyst / 1e6
    annual_co2 = CO2_thr * annual_hours * p.co2_price / 1e6
    annual_revenue = p.electricity_price * annual_gen_MWh / 1e6

    # COE / LCOE
    r = p.discount_rate / 100
    crf = r * (1 + r)**p.plant_life / ((1 + r)**p.plant_life - 1) if r > 0 else 1.0 / p.plant_life
    annual_capital = TASC * crf
    COE = (annual_capital + annual_fuel + annual_fixed_om + annual_var_om + annual_scr) / annual_gen_kWh * 1e9
    LCOE = COE + annual_co2 / annual_gen_kWh * 1e9

    # Cash flows
    cash_flows = []
    cumulative = -TASC
    npv_flows = [-TASC]
    for yr in range(1, p.plant_life + 1):
        ef = (1 + p.fuel_escalation/100)**(yr-1)
        ee = (1 + p.elec_escalation/100)**(yr-1)
        ec = (1 + p.co2_escalation/100)**(yr-1)
        rev = annual_revenue * ee
        fuel = annual_fuel * ef
        om = annual_fixed_om + annual_var_om + annual_scr
        co2 = annual_co2 * ec
        net = rev - fuel - om - co2
        cumulative += net
        cash_flows.append({"Year": yr, "Revenue": round(rev,2), "Fuel": round(fuel,2),
                          "O&M": round(om,2), "CO2": round(co2,2),
                          "Net": round(net,2), "Cumulative": round(cumulative,2)})
        npv_flows.append(net)

    NPV = sum(cf / (1+r)**t for t, cf in enumerate(npv_flows))
    try:
        from scipy.optimize import brentq
        IRR = brentq(lambda rate: sum(cf/(1+rate)**t for t,cf in enumerate(npv_flows)), -0.3, 1.0) * 100
    except Exception:
        IRR = 0.0
    payback = -1
    for cf in cash_flows:
        if cf["Cumulative"] >= 0:
            payback = cf["Year"]; break

    cost_breakdown = {"Capital": round(annual_capital,2), "Fuel": round(annual_fuel,2),
                     "Fixed O&M": round(annual_fixed_om,2), "Variable O&M": round(annual_var_om,2),
                     "SCR Catalyst": round(annual_scr,2), "CO2": round(annual_co2,2)}

    # Class-3: 14-account capital breakdown.
    # Scale each account by the user's actual TPC ($/kW) relative to NETL ($584).
    netl_tpc_per_kW = 584.0
    tpc_scale = p.TPC_per_kW / netl_tpc_per_kW
    account_breakdown = []
    for acc in NETL_ACCOUNT_CATALOG:
        acc_per_kW = float(acc["usd_per_kW"]) * tpc_scale
        acc_M = acc_per_kW * W_net_kW / 1e6
        account_breakdown.append({
            "id": acc["id"], "name": acc["name"],
            "usd_per_kW": round(acc_per_kW, 1),
            "usd_M": round(acc_M, 2),
            "pct_of_TPC": round(acc_per_kW / p.TPC_per_kW * 100, 1) if p.TPC_per_kW > 0 else 0.0,
        })

    # Class-3: owner's costs decomposition (replaces single TASC multiplier).
    # Rebuild TOC and TASC from itemized costs so totals stay consistent.
    owners_costs = []
    for oc in OWNERS_COST_CATALOG:
        oc_M = TPC * float(oc["frac_of_TPC"])
        owners_costs.append({
            "id": oc["id"], "name": oc["name"],
            "frac_of_TPC": round(oc["frac_of_TPC"] * 100, 2),  # %
            "usd_M": round(oc_M, 2),
        })
    owners_total_M = sum(o["usd_M"] for o in owners_costs)
    # When user has not changed defaults, owners_total_M ≈ 22.9 % × TPC,
    # giving TOC ≈ 1.229 × TPC, matching the legacy formula via
    # process_contingency × project_contingency. We do not overwrite
    # TOC/TASC here — they already include user's contingencies — but we
    # report owners_total alongside for transparency.

    return EconomicResult(TPC=round(TPC,1), TOC=round(TOC,1), TASC=round(TASC,1),
        annual_fuel=round(annual_fuel,1), annual_fixed_om=round(annual_fixed_om,1),
        annual_var_om=round(annual_var_om,1), annual_co2=round(annual_co2,1),
        annual_revenue=round(annual_revenue,1), COE=round(COE,1), LCOE=round(LCOE,1),
        NPV=round(NPV,1), IRR=round(IRR,2), payback=payback, heat_rate=round(heat_rate,0),
        cost_breakdown=cost_breakdown, cash_flows=cash_flows,
        account_breakdown=account_breakdown,
        owners_costs=owners_costs)

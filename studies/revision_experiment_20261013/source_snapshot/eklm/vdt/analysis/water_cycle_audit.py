"""Independent external steam-water boundary ledger after tear convergence."""
def close_water_cycle(hrsg,st,cond,params):
    a=hrsg.cycle_audit
    gland_heat=params.m_dot_gsc*(st.unit_31.s25.h-params.h_gsc)/3.6e6
    makeup_energy=params.m_dot_cond_muw*cond.water_audit['makeup_supply_enthalpy_J_kg']/3.6e6
    residual=(hrsg.Q_total+hrsg.W_bfp_total+cond.W_cp+makeup_energy-st.W_shaft
              -cond.Q_cond-gland_heat-a['blowdown_enthalpy_rate_kW'])
    a.update(gland_heat_rejection_kW=gland_heat,makeup_enthalpy_rate_kW=makeup_energy,
             external_energy_residual_kW=residual,
             external_mass_residual_kg_hr=params.m_dot_cond_muw-a['blowdown_kg_hr'])
    a['whole_cycle_closed']=bool(abs(residual)<.1 and abs(a['external_mass_residual_kg_hr'])<1e-3
                                and abs(a['deaerator_mass_residual_kg_hr'])<1e-3)
    hrsg.feedwater_audit['whole_cycle_closed']=a['whole_cycle_closed']
    if not a['whole_cycle_closed']:raise ValueError('Linked water-cycle external balance failed')

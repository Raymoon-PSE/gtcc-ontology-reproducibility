"""Linked steam-water circuit: ideal open heater, blowdown purge and makeup.

Engineering topology, not a reconstruction of vendor P&IDs. All HP bleed
except gland supply enters the DA. Blowdown leaves the cycle without heat
recovery. LP economizer duty (thus stack temperature) follows DA balance.
"""
from dataclasses import replace
import math
from .hrsg_solver import (HRSGOutput,HPEvaporatorOutput,IPEvaporatorOutput,
    LPEvaporatorOutput,hp_superheater,reheater,ip_superheater,ip_mixing_node,
    hp_economizer,ip_economizer,lp_economizer,bfp)
from .deaerator import deaerator, mix_deaerator
from .water_boundary import condition_water
from .heat_limits import limited_outlet_temperature
from .thermal_audit import heat_exchanger_audit,summarize_audits
from eklm.vdt.data.properties import (h_water,T_sat_water,h_sat_liq_water,
    h_sat_vap_water,T_from_PH_water,s_from_PH_water)
from eklm.vdt.data.species import h_mix,T_from_H_mix,s_mix
from eklm.vdt.data.streams import Stream


def water(p,h,m):
    return Stream(T=T_from_PH_water(p,h),P=p,m_dot=m,w={'H2O':1.},h=h,s=s_from_PH_water(p,h))


def cool_gas(g,q):
    h=h_mix(g.T+273.15,g.w)-q*3.6e6/g.m_dot
    t=T_from_H_mix(h,g.w)
    return replace(g,T=t-273.15,h=h,s=s_mix(t,g.P*1e6,g.w))


def linked_hrsg(g,cold,cond,p):
    if not math.isfinite(p.min_approach_C) or p.min_approach_C<=0:
        raise ValueError("Linked minimum approach must be finite and positive")
    beta=p.blowdown_fraction
    if not math.isfinite(beta) or not 0<=beta<.2:raise ValueError('Linked blowdown fraction must be in [0, .2)')
    masses=[p.m_dot_hp,p.m_dot_ip,p.m_dot_lp];pressures=[p.P_HP,p.P_IP,p.P_LP]
    if min(masses)<=0:raise ValueError('Linked steam flows must be positive')
    fw=[m/(1-beta) for m in masses];blow=[f-m for f,m in zip(fw,masses)]
    bleed=p.m_dot_hp-cold.m_dot
    da_steam=bleed-p.gland_flow
    if not math.isfinite(da_steam) or da_steam<0:raise ValueError('HP bleed cannot supply the specified gland branch')
    if cold.P<p.P_LP:raise ValueError('DA extraction pressure below DA pressure')
    target=deaerator(p.P_LP)
    hp=bfp(target.T_da,p.P_LP,p.P_HP,fw[0],p.eta_bfp)
    ip=bfp(target.T_da,p.P_LP,p.P_IP,fw[1],p.eta_bfp)
    def limited(g,m,pressure,temp,inlet=None):
        inlet=inlet or water(pressure,h_sat_vap_water(pressure),m)
        return limited_outlet_temperature(g,inlet,pressure,temp,p.min_approach_C)
    a=hp_superheater(g,masses[0],P_HP=p.P_HP,T_is01=limited(g,masses[0],p.P_HP,p.T_is01))
    b=reheater(a.s8,cold,T_24=limited(a.s8,cold.m_dot,cold.P-p.dP_rh_st,p.T_24,cold),dP_st=p.dP_rh_st)
    def evaporator(g,j):
        pressure=pressures[j];ts=T_sat_water(pressure)
        hf=h_sat_liq_water(pressure);hg=h_sat_vap_water(pressure)
        hin=h_water(ts-10.,pressure) if j<2 else target.h_da
        wi=water(pressure,hin,fw[j]);wo=water(pressure,hg,masses[j])
        drain=water(pressure,hf,blow[j])
        q=(masses[j]*hg+blow[j]*hf-fw[j]*hin)/3.6e6
        go=cool_gas(g,q)
        # Audit a total outlet with enthalpy equal to the vapor+purge mixture.
        # Actual saturated vapor and liquid purge remain separate streams.
        combined=water(pressure,(masses[j]*hg+blow[j]*hf)/fw[j],fw[j])
        audit=heat_exchanger_audit(['HP Evaporator','IP Evaporator','LP Evaporator'][j],g,go,wi,combined,q)
        return go,wi,wo,drain,q,audit
    g2,wi,wo,bdhp,q,ah=evaporator(b.s9,0)
    c=HPEvaporatorOutput(g2,wo,wi,q,g2.T-T_sat_water(p.P_HP),10.,h_sat_vap_water(p.P_HP)-h_sat_liq_water(p.P_HP))
    d=ip_superheater(c.s10,masses[1],P_IP=p.P_IP,T_is04=limited(c.s10,masses[1],p.P_IP,p.T_is04))
    mix=ip_mixing_node(b.s24,d.s_is04)
    e=hp_economizer(d.s11,c.s18,fw[0],T_17=hp.s_out.T,P_HP=p.P_HP)
    g3,wi,wo,bdip,q,ai=evaporator(e.s12,1)
    f=IPEvaporatorOutput(g3,wo,wi,q,g3.T-T_sat_water(p.P_IP),10.)
    k=ip_economizer(f.s13,f.s21,fw[1],T_20=ip.s_out.T,P_IP=p.P_IP)
    g4,wi,wo,bdlp,q,al=evaporator(k.s14,2)
    l=LPEvaporatorOutput(g4,wo,wi,q,g4.T-T_sat_water(p.P_LP),0.)
    conditioned,work=condition_water(cond,p.P_LP)
    # Adiabatic mixing with actual extraction determines required condensate
    # preheat. Stack temperature is an output, not an independent heat sink.
    m_da=cond.m_dot+da_steam
    h_pre=(m_da*target.h_da-da_steam*cold.h)/cond.m_dot
    q_pre=cond.m_dot*(h_pre-conditioned.h)/3.6e6
    if q_pre<=0:raise ValueError('Linked DA requires cooling or bypass: no feasible positive LP preheat')
    stack=cool_gas(l.s15,q_pre)
    n=lp_economizer(l.s15,cond,T_16=stack.T,P_eco=p.P_LP)
    da=mix_deaerator(n.s23,water(p.P_LP,cold.h,da_steam),p.P_LP)
    boundaries=[('HP Superheater',g,a.s8,c.s19,a.s_is01,a.Q_dot),
                ('Reheater',a.s8,b.s9,cold,b.s24,b.Q_dot),
                ('IP Superheater',c.s10,d.s11,f.s22,d.s_is04,d.Q_dot),
                ('HP Economizer',d.s11,e.s12,e.s17,c.s18,e.Q_dot),
                ('IP Economizer',f.s13,k.s14,k.s20,f.s21,k.Q_dot),
                ('LP Economizer',l.s15,n.s16,n.s_in,n.s23,n.Q_dot)]
    audits=[heat_exchanger_audit(*x) for x in boundaries]+[ah,ai,al]
    audit=summarize_audits(audits);audit.update(thermal_mode='linked',min_approach_C=p.min_approach_C)
    if not audit['local_balances_passed'] or not audit['endpoint_screen_passed']:
        bad=[u['unit'] for u in audits if not u['local_balance_passed'] or not u['endpoint_screen_passed']]
        raise ValueError('Linked HRSG infeasible: '+', '.join(bad))
    mass_gap=m_da-sum(fw)
    da_energy=(cond.m_dot*n.s23.h+da_steam*cold.h-m_da*da.h_da)/3.6e6
    pump_res={name:x.s_out.m_dot*(x.s_out.h-da.h_da)/3.6e6-x.W_bfp for name,x in [('HP',hp),('IP',ip)]}
    linked=dict(scope='linked_steady_water_circuit',feedwater_kg_hr=sum(fw),
        extraction_to_da_kg_hr=da_steam,gland_supply_kg_hr=p.gland_flow,
        blowdown_kg_hr=sum(blow),blowdown_enthalpy_rate_kW=sum(s.m_dot*s.h for s in [bdhp,bdip,bdlp])/3.6e6,
        makeup_required_kg_hr=sum(blow),deaerator_mass_residual_kg_hr=mass_gap,
        deaerator_energy_residual_kW=da_energy,deaerator_outlet_h_J_kg=da.h_da,
        whole_cycle_closed=False,
        assumptions=['All non-gland HP bleed heats ideal adiabatic DA; no vent',
                     'Drum blowdown purged; no heat recovery; makeup replaces purge',
                     'Gland steam condensed externally and returned; heat reported separately',
                     'No vendor UA or full internal-pinch validation'])
    fa=dict(scope='linked_steady_feedwater',deaerator_mass_balance_passed=abs(mass_gap)<1e-3,
        deaerator_mass_residual_kg_hr=mass_gap,deaerator_required_external_heat_kW=-da_energy,
        lp_feed_required_external_heat_kW=0.,pump_energy_residual_kW=pump_res,
        pump_balances_passed=all(abs(v)<.01 for v in pump_res.values()),
        unmodeled_heat_paths_present=False,whole_cycle_closed=linked['whole_cycle_closed'])
    return HRSGOutput(a.s_is01,mix.s_is03,l.s_is05,n.s16,n.s23,a,b,mix,c,d,e,f,k,l,n,da,hp,ip,
        sum(x.Q_dot for x in [a,b,c,d,e,f,k,l,n]),n.s16.T,hp.W_bfp+ip.W_bfp+work,audit,fa,linked)

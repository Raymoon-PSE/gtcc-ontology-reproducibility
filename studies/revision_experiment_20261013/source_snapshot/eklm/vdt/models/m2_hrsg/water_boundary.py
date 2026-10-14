"""Explicit pressure conditioning of liquid condensate (kW, MPa, J/kg)."""
from dataclasses import replace
import math
from CoolProp.CoolProp import PropsSI
from eklm.vdt.data.properties import h_water,T_from_PH_water,s_from_PH_water


def condition_water(inlet, pressure, efficiency=.8):
    h = inlet.h if inlet.h is not None else h_water(inlet.T,inlet.P)
    if not all(math.isfinite(x) for x in (h,pressure,inlet.P,inlet.m_dot,efficiency)):
        raise ValueError('Water boundary inputs must be finite')
    if min(pressure,inlet.P)<=0 or inlet.m_dot<0 or not 0<efficiency<=1:
        raise ValueError('Invalid water boundary pressure, flow or efficiency')
    work=0.
    if pressure>inlet.P:
        hf=PropsSI('H','P',inlet.P*1e6,'Q',0,'Water')
        if h>hf+1e-5:raise ValueError('Pressure lift requires liquid water')
        rho=PropsSI('D','P',inlet.P*1e6,'H',h,'Water')
        rise=(pressure-inlet.P)*1e6/(rho*efficiency)
        work=inlet.m_dot*rise/3.6e6
        h+=rise
    return replace(inlet,P=pressure,h=h,T=T_from_PH_water(pressure,h),
                   s=s_from_PH_water(pressure,h)),work

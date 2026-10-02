"""Typed reference-schema checks for governed execution, not plant validation."""
import math


def resolve_parameters(defaults, required, optional, status):
    if set(required) & set(optional):
        raise ValueError('Parameter declared in both required and optional maps')
    supplied={**optional, **required}
    unknown=set(supplied)-set(defaults)
    if unknown:
        raise ValueError('Unknown mechanical parameters: '+str(sorted(unknown)))
    for key,value in supplied.items():
        exemplar=defaults[key]
        if isinstance(exemplar,str):
            if not isinstance(value,str) or not value.strip():
                raise ValueError('Expected nonempty text: '+key)
        elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Expected finite numeric parameter: '+key)
    resolved={**defaults,**supplied}
    for key,value in resolved.items():
        if isinstance(value,str):
            if not value.strip():raise ValueError('Empty reference parameter: '+key)
            continue
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Invalid reference parameter: '+key)
        if 'efficiency' in key or key in ('cooling_effectiveness','liner_temp_ratio'):
            valid=0 < value <= 1
        elif key=='cooling_air_fraction':valid=0 <= value < 1
        elif key.endswith('_C') and key!='larson_miller_C':valid=value > -273.15
        elif key in ('k_degradation_per_khr','k_fouling_per_khr','fouling_factor_design','erosion_rate_coeff','surge_margin_design_pct','eoh_per_start'):
            valid=value >= 0
        else:valid=value > 0
        if key in ('stage_count','N_f_design_starts'):valid=valid and value==int(value)
        if not valid:raise ValueError('Parameter outside declared computational domain: '+key)
    if {'tube_OD_mm','tube_wall_mm'} <= set(resolved):
        if 2*resolved['tube_wall_mm']>=resolved['tube_OD_mm']:
            raise ValueError('Tube wall must be less than half the outside diameter')
    if status=='FULL' and set(defaults)-set(supplied):
        raise ValueError('Incomplete FULL input: '+str(sorted(set(defaults)-set(supplied))))
    return ({} if status=='NONE' else resolved), supplied


def validate_outputs(result, package):
    """Known positive-infinity lifetime sentinels are explicitly labelled."""
    from eklm.kas.legacy_bridge.mech_bridge import _PROP_MAP
    for key,value in result.outputs.items():
        if key not in _PROP_MAP:raise ValueError('Unregistered output binding: '+key)
        if isinstance(value,bool) or not isinstance(value,(int,float)):
            raise ValueError('Nonnumeric mechanical output: '+key)
        allowed=(key in ('mech_gt_creep_rupture_hr','mech_hpsh_creep_rupture_hr','mech_rh_creep_rupture_hr')
                 or (key=='mech_comp_remaining_life_hr' and package.get('k_degradation_per_khr')==0)
                 or (key=='mech_hpst_remaining_life_hr' and result.outputs.get('mech_hpst_erosion_rate_mm_khr')==0))
        if not math.isfinite(value):
            if value==math.inf and allowed:
                result.warnings.append('UNBOUNDED_MODEL_LIFETIME: '+key+'; no finite crossing under this model, not guaranteed service life')
            else:raise ValueError('Invalid nonfinite mechanical output: '+key)

"""Experimental compressor inspection indicator; no new physical accuracy claim.

This plugin wraps the unchanged compressor calculation. The ratio compares its
conditional remaining-life estimate with a declared planning window, in hours.
It is a computational integration task, not a maintenance recommendation.
"""
from eklm.vdt.mechanical.compressor_model import CompressorPhysicsModel,CompressorHybridModel
from eklm.vdt.mechanical.model_router import register_model
TYPE='CompressorInspectionV1'
KEY='mech_comp_inspection_window_ratio'
class InspectionPhysics(CompressorPhysicsModel):
 def run(self,op):
  result=super().run(op)
  result.outputs[KEY]=result.outputs['mech_comp_remaining_life_hr']/self.package.get('inspection_window_hr')
  return result
class InspectionHybrid(CompressorHybridModel):
 def run(self,op):
  result=super().run(op)
  result.outputs[KEY]=result.outputs['mech_comp_remaining_life_hr']/self.package.get('inspection_window_hr')
  return result

def install():register_model(TYPE,InspectionPhysics,InspectionHybrid)

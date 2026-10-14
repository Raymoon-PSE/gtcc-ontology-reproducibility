"""VDT.data — fluid properties / species / fuels / streams.

Pure-data module: 무상태 함수와 dataclass. CoolProp 직접 의존
(KDL Facade 비노출 — 물성 계산은 numerical layer).

Reference: GT_Module_Math_Model §0.5, §2.4, §3.6.
"""

from eklm.vdt.data import fuels, properties, species, streams

__all__ = ["fuels", "properties", "species", "streams"]

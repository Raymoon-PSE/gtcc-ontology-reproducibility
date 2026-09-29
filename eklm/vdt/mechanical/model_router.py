"""ModelRouter — selects model type based on DataStatus.

Reference: GTCC_Mechanical_Modeling_Strategy.md §2.

    FULL    → PhysicsModel (device-specific subclass)
    PARTIAL → HybridModel  (same physics + Reference fill + uncertainty flags)
    NONE    → NullModel    (inactive, warning only)
"""

from __future__ import annotations

from eklm.vdt.mechanical.base import BaseDeviceModel, NullModel
from eklm.vdt.mechanical.data_package import DataStatus, DeviceDataPackage
from eklm.vdt.mechanical.reference_db import ReferenceDatabase


# Device-type → (PhysicsModelClass, HybridModelClass)
# Populated by register_model() from each device module.
_MODEL_REGISTRY: dict[str, tuple[type, type]] = {}


def register_model(device_type: str, physics_cls: type, hybrid_cls: type) -> None:
    _MODEL_REGISTRY[device_type] = (physics_cls, hybrid_cls)


class ModelRouter:

    def __init__(self, ref_db: ReferenceDatabase | None = None):
        self.ref_db = ref_db or ReferenceDatabase()

    def route(self, package: DeviceDataPackage) -> BaseDeviceModel:
        if package.status == DataStatus.NONE:
            return NullModel(package)

        entry = _MODEL_REGISTRY.get(package.device_type)
        if entry is None:
            return NullModel(package)

        physics_cls, hybrid_cls = entry

        if package.status == DataStatus.FULL:
            return physics_cls(package)

        # PARTIAL: fill optional params from reference, flag uncertainty
        self.ref_db.fill(package)
        return hybrid_cls(package)

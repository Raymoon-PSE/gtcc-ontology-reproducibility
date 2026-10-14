"""Base classes for Mechanical Device Models.

Reference: GTCC_Mechanical_Modeling_Strategy.md §4.

Hierarchy:
    BaseDeviceModel (ABC)
    ├── PhysicsModel   — FULL data, high-fidelity physics
    ├── HybridModel    — PARTIAL data, Reference-filled + uncertainty flag
    └── NullModel      — NONE data, inactive (never crashes)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from eklm.vdt.mechanical.data_package import DeviceDataPackage
from eklm.vdt.mechanical.operating_point import OperatingPoint


@dataclass
class DeviceResult:
    """Standard output from any mechanical device model."""

    device_id: str
    device_type: str
    status: str  # "ACTIVE", "ACTIVE_UNCERTAIN", "INACTIVE"
    outputs: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    uncertain_params: list[str] = field(default_factory=list)


class BaseDeviceModel(ABC):

    def __init__(self, package: DeviceDataPackage):
        self.package = package

    @abstractmethod
    def run(self, op: OperatingPoint) -> DeviceResult:
        ...

    def _result(
        self,
        status: str,
        outputs: dict[str, float],
        warnings: list[str] | None = None,
        uncertain: list[str] | None = None,
    ) -> DeviceResult:
        return DeviceResult(
            device_id=self.package.device_id,
            device_type=self.package.device_type,
            status=status,
            outputs=outputs,
            warnings=warnings or [],
            uncertain_params=uncertain or [],
        )


class NullModel(BaseDeviceModel):

    def run(self, op: OperatingPoint) -> DeviceResult:
        return self._result(
            status="INACTIVE",
            outputs={},
            warnings=[f"{self.package.device_id}: DataStatus=NONE, model inactive"],
        )


class PhysicsModel(BaseDeviceModel):
    """Base for FULL-data physics models. Subclasses implement run()."""
    pass


class HybridModel(BaseDeviceModel):
    """PARTIAL data — same physics as PhysicsModel but flags uncertain params."""
    pass

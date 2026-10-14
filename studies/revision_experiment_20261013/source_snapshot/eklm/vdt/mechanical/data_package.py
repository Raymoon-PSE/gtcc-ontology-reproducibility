"""Data availability and device data packaging for Mechanical Modeling.

Reference: GTCC_Mechanical_Modeling_Strategy.md §2.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DataStatus(Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


@dataclass
class DeviceDataPackage:
    """Encapsulates a device's mechanical data and its availability status.

    Status is auto-computed from required/optional param completeness:
        FULL    = all required + all optional present
        PARTIAL = all required present, some optional missing
        NONE    = any required missing
    """

    device_id: str
    device_type: str
    unit_id: str
    required_params: dict[str, Any] = field(default_factory=dict)
    optional_params: dict[str, Any] = field(default_factory=dict)
    status: DataStatus = DataStatus.NONE

    def __post_init__(self):
        self.status = self._compute_status()

    def _compute_status(self) -> DataStatus:
        if not self.required_params:
            return DataStatus.NONE
        has_required = all(v is not None for v in self.required_params.values())
        if not has_required:
            return DataStatus.NONE
        has_optional = (
            bool(self.optional_params)
            and all(v is not None for v in self.optional_params.values())
        )
        return DataStatus.FULL if has_optional else DataStatus.PARTIAL

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.required_params and self.required_params[key] is not None:
            return self.required_params[key]
        if key in self.optional_params and self.optional_params[key] is not None:
            return self.optional_params[key]
        return default

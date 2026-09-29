"""Reference Database — loads default values from JSON files.

Reference: GTCC_Mechanical_Modeling_Strategy.md §7.

Hierarchical lookup:
    1. User-supplied data (in DeviceDataPackage)
    2. Primary reference (e.g., netl_case13.json)
    3. OEM public data (oem_generic.json)
    4. Standards (codes_iso_asme.json)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eklm.vdt.mechanical.data_package import DeviceDataPackage

_DEFAULT_REF_DIR = Path(__file__).resolve().parents[3] / "data" / "reference"


class ReferenceDatabase:
    """Loads and merges reference values from JSON files.

    Each JSON file maps device_type -> {param_name: value}.
    Multiple files are merged in priority order (first file wins).
    """

    def __init__(self, ref_dir: Path | str | None = None):
        if ref_dir is None:
            ref_dir = _DEFAULT_REF_DIR
        self._ref_dir = Path(ref_dir)
        self._data: dict[str, dict[str, Any]] = {}
        self._load_all()

    def _load_all(self) -> None:
        load_order = [
            "netl_case13.json",
            "oem_generic.json",
            "codes_iso_asme.json",
        ]
        for fname in load_order:
            fpath = self._ref_dir / fname
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for dev_type, params in data.items():
                    if dev_type not in self._data:
                        self._data[dev_type] = {}
                    for k, v in params.items():
                        if k not in self._data[dev_type]:
                            self._data[dev_type][k] = v

    def get_defaults(self, device_type: str) -> dict[str, Any]:
        return dict(self._data.get(device_type, {}))

    def fill(self, package: DeviceDataPackage) -> DeviceDataPackage:
        """Fill missing optional params from reference data."""
        ref = self.get_defaults(package.device_type)
        for key, val in ref.items():
            if package.optional_params.get(key) is None:
                package.optional_params[key] = val
        return package

"""Standard stream object for PlantMind GTCC Simulator.

Reference: PlantMind_MASTER_SPEC §2.4, GT_Module_Math_Model §0.5.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Stream:
    """Standard stream object S^(n) = {T, P, m_dot, w, h, s}.

    Phase 1 conventions:
        - T in degrees Celsius
        - P in MPa
        - m_dot in kg/hr
        - w as composition dict, **mass fraction** (per GT_Module_Math_Model
          §3.6; species symbols follow PlantMind Symbol Convention v1.1).
          Mole fractions, when needed, are derived locally inside each unit
          via y_k = (w_k / M_k) / Σ(w_j / M_j).
        - h in J/kg, s in J/kg/K — Optional. Populated by units that have a
          property closure (Air via CoolProp; fuel via ideal-gas, see
          osim.properties).
    """

    T: float
    P: float
    m_dot: float
    w: dict[str, float]
    h: Optional[float] = None
    s: Optional[float] = None

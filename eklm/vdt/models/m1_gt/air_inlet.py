"""Unit 1-1: Air Inlet.

Reference: GT_Module_Math_Model §1 (Unit 1-1).
"""

from eklm.vdt.data.streams import Stream


def air_inlet(s1: Stream, dP: float = 0.0) -> Stream:
    """Apply inlet filter/duct pressure drop.

    Mass, temperature, and composition are conserved.
    Property closure (h, s) is deferred to a separate property module.

    Args:
        s1: Ambient air stream S^(1).
        dP: Inlet filter pressure drop ΔP^(ai), in MPa. Default 0.

    Returns:
        s2: Conditioned air stream S^(2), delivered to Unit 1-2 (Compressor).
    """
    return Stream(
        T=s1.T,
        P=s1.P - dP,
        m_dot=s1.m_dot,
        w=s1.w,
        h=None,
        s=None,
    )

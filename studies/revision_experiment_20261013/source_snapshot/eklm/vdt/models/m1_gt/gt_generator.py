"""Unit 1-6: GT Generator.

Reference: GT_Module_Math_Model v1.1 § 6.

Pure power-balance unit. Computes net shaft power and gross GT electrical
output from the turbine and compressor power values produced by Units 1-5
and 1-2 respectively. No material stream involvement.
"""


def gt_generator(
    W_turb: float,
    W_comp: float,
    eta_gen: float = 0.984,
) -> tuple[float, float]:
    """Convert turbine/compressor power flows to GT electrical output.

    Args:
        W_turb: Turbine shaft power Ẇ^(turb), kW (positive). From Unit 1-5.
        W_comp: Compressor shaft power Ẇ^(comp), kW (positive). From Unit 1-2.
        eta_gen: GT generator efficiency η^(gen). Default 0.984 (NETL).

    Returns:
        W_shaft: Net shaft power Ẇ^(shaft) = Ẇ^(turb) − Ẇ^(comp), kW.
        W_GT: Gross electrical output Ẇ^(GT) = η^(gen) × Ẇ^(shaft), kWe.
    """
    W_shaft = W_turb - W_comp
    W_GT = eta_gen * W_shaft
    return W_shaft, W_GT

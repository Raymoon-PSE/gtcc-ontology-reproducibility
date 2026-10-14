"""Unit 3-5: ST Generator.

Reference: ST_Module_Math_Model v1.0 Unit 3-5.

Converts turbine shaft powers to ST gross electrical output.
Same pattern as M1 GT Generator.
"""


def st_generator(
    W_hpt: float,
    W_ipt: float,
    W_lpt: float,
    eta_stgen: float = 0.984,
) -> tuple[float, float]:
    """Convert turbine powers to ST electrical output.

    Args:
        W_hpt: HP turbine power, kW.
        W_ipt: IP turbine power, kW.
        W_lpt: LP turbine power, kW.
        eta_stgen: ST generator efficiency. Default 0.984 (NETL).

    Returns:
        W_shaft: ST shaft power (sum of turbines), kW.
        W_ST: ST gross electrical output, kWe.
    """
    W_shaft = W_hpt + W_ipt + W_lpt
    W_ST = eta_stgen * W_shaft
    return W_shaft, W_ST

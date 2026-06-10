"""Published benchmark values from Docs/lqd_model_note.tex (sections 8-9).

These are golden numbers: the SVI-JW target slice, the LQD coefficients the
note reports for its two fits, and the associated endpoint diagnostics.
"""

import numpy as np

from volfit.models.lqd.basis import LQDParams
from volfit.models.svi_jw import RawSVI, SVIJW

# --- SPX-like SVI-JW benchmark (note section 8) ------------------------------
SVI_T = 0.50
SVI_JW_PARAMS = SVIJW(t=SVI_T, v=0.0425, psi=-0.25, p=0.75, c=0.25, v_tilde=0.0340)
SVI_RAW = RawSVI(
    a=0.0106250000,
    b=0.0728868987,
    rho=-0.5000000000,
    m=0.0583095189,
    sigma=0.1009950494,
)
SVI_FIT_RANGE = (-0.35, 0.30)

# Seven-parameter LQD fit reported in eq. (svi_lqd_coeffs).
SVI_LQD_PARAMS = LQDParams(
    L=-1.87350162,
    R=-3.09113957,
    a=np.array([0.38052207, -0.04814625, -0.00684433, 0.00560282, 0.00216176]),
)
SVI_LQD_A_LEFT = 0.21433704
SVI_LQD_A_RIGHT = 0.06906158
SVI_LQD_MU = 0.02069448
SVI_LQD_BETA_LEFT = 0.09702292
SVI_LQD_BETA_RIGHT = 0.03577726

# --- Bimodal "double-hat" event benchmark (note section 9) --------------------
DH_T = 30.0 / 365.0
DH_M1 = -0.10075573
DH_M2 = 0.08924427
DH_S = 0.05
DH_FIT_RANGE = (-0.25, 0.25)

# Thirteen-parameter LQD fit reported in eq. (dh_lqd_coeffs).
DH_LQD_PARAMS = LQDParams(
    L=-2.95878524,
    R=-2.96084492,
    a=np.array(
        [
            -1.13861892,
            -0.00127725,
            0.46596301,
            0.00265138,
            -0.55916861,
            -0.00622975,
            0.40038700,
            -0.00664862,
            -0.39218679,
            0.02292111,
            -0.00832500,
        ]
    ),
)
DH_LQD_A_LEFT = 0.01530895
DH_LQD_A_RIGHT = 0.01493256
DH_LQD_MU = -0.00583082


def double_hat_call(k: np.ndarray) -> np.ndarray:
    """Closed-form normalized call of the two-component lognormal mixture
    (eq. mix_call): equal weights, common s = 0.05, means DH_M1 / DH_M2."""
    from volfit.core.black import norm_cdf

    k = np.asarray(k, dtype=float)
    price = np.zeros_like(k)
    for m_i in (DH_M1, DH_M2):
        d1 = (m_i + DH_S**2 - k) / DH_S
        d2 = (m_i - k) / DH_S
        price += 0.5 * (np.exp(m_i + 0.5 * DH_S**2) * norm_cdf(d1) - np.exp(k) * norm_cdf(d2))
    return price

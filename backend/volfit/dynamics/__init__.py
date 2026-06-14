"""Vol-spot dynamics: smile response to spot moves (SSR and sticky regimes).

``ssr`` is the legacy linearized scenario-overlay rule; ``transport`` implements
the exact no-recalibration spot-move transforms of
``Docs/spot_move_vol_surface_note_updated.tex`` (smile, surface and LV-grid).
"""

from volfit.dynamics.ssr import Regime, shifted_smile, ssr_of_regime
from volfit.dynamics.transport import (
    TransportedSlice,
    beta_of,
    ell_T,
    is_exact_lv,
    transport_grid_logk,
    transport_grid_strikes,
    transported_w,
)

__all__ = [
    "Regime",
    "shifted_smile",
    "ssr_of_regime",
    "TransportedSlice",
    "transported_w",
    "ell_T",
    "is_exact_lv",
    "beta_of",
    "transport_grid_logk",
    "transport_grid_strikes",
]

"""Vol-spot dynamics: smile response to spot moves (SSR and sticky regimes)."""

from volfit.dynamics.ssr import Regime, shifted_smile, ssr_of_regime

__all__ = ["Regime", "shifted_smile", "ssr_of_regime"]

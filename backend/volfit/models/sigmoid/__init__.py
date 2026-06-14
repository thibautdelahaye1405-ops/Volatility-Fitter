"""Multi-Core Sigmoid Implied Variance (MC-SIV) smile model.

A one-core SIV base (level / skew / convexity / asymmetric wings) plus R signed
zero-wing hat kernels for WW / dual-hat shapes — see
``Docs/Multi_Core_SIV_Technical_Note.tex``. ``SigmoidSmile`` is kept as an alias
of ``MultiCoreSiv`` so the API/UI family stays "sigmoid" (SIV).
"""

from volfit.models.sigmoid.calibrate import calibrate_sigmoid
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv, SigmoidSmile

__all__ = ["HatCore", "MultiCoreSiv", "SigmoidSmile", "calibrate_sigmoid"]

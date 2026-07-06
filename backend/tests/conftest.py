"""Shared test configuration.

Pins the calibration fit pool OFF (VOLFIT_CALIB_WORKERS=1) so the suite keeps
the historical inline/serial calibration behaviour everywhere except the
dedicated parallel-calibration tests (tests/test_parallel_calibration.py),
which override the variable per-test and reset the pool themselves.
"""

import os

os.environ["VOLFIT_CALIB_WORKERS"] = "1"

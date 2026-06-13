"""Performance budget suite (Phase 9).

A single place that times the hot quant paths and asserts each stays within a
budget. These guard against accidental *algorithmic* regressions — an O(N^2)
creeping into a vectorized path, a lost cache, a scalar fallback — rather than
micro-benchmarking absolute speed.

Budgets are deliberately loose multiples (~8-12x) of the timings measured on
the dev box, so the suite stays green on slow, shared CI runners while still
catching an order-of-magnitude blow-up. Each entry in ``BUDGET_MS`` records the
representative local timing and the design target it derives from.

Run just this suite (``-s`` surfaces the timing report)::

    pytest tests/test_perf.py -m perf -q -s
"""

import time

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.core.american import (
    DEFAULT_BATCH_STEPS,
    binomial_price_batch,
    deamericanize_batch,
)
from volfit.graph import build_graph, build_increment_prior, posterior_update
from volfit.models.localvol import LocalVolGrid, LocalVolModel
from volfit.models.lqd.calibrate import calibrate_slice

pytestmark = pytest.mark.perf

# Operation -> wall-clock ceiling in milliseconds (median of timed runs). The
# trailing comment is the timing measured on the dev box (Win, py3.11); budgets
# sit ~2.5-3.5x above that to absorb slower shared CI runners without masking a
# real algorithmic regression.
BUDGET_MS = {
    "lqd_slice_fit": 350.0,         # ~95 ms local; Phase-1 exit target < 50 ms (warm)
    "graph_update_1k": 2500.0,      # ~700 ms local; Phase-4 target < 1 s @ 1k nodes
    "localvol_forward": 250.0,      # ~20 ms local; CN Dupire forward, 2 expiries
    "deamericanize_chain": 1800.0,  # ~630 ms local; ~80-quote vectorized CRR de-Am
}


def _median_ms(fn, *, repeat: int, warmup: int = 1) -> float:
    """Median wall-clock of ``fn`` over ``repeat`` runs after ``warmup`` runs.

    Warmup absorbs first-call costs (import-time lazy compilation, allocator
    warm-up); the median (not the min) is robust to a single scheduler hiccup
    on a noisy CI runner without rewarding a lucky best case.
    """
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1e3)
    return float(np.median(samples))


@pytest.fixture(scope="module")
def perf_report():
    """Collect (name, measured_ms) pairs and print a budget table at teardown."""
    rows: list[tuple[str, float]] = []
    yield rows
    if not rows:
        return
    width = max(len(name) for name, _ in rows)
    print("\n\n  Perf budget report (median ms vs ceiling)")
    print("  " + "-" * (width + 26))
    for name, measured in rows:
        budget = BUDGET_MS[name]
        pct = 100.0 * measured / budget
        print(f"  {name:<{width}}  {measured:8.1f} / {budget:8.1f} ms  ({pct:4.0f}% of budget)")


def _check(perf_report, name: str, fn, *, repeat: int, warmup: int = 1) -> float:
    measured = _median_ms(fn, repeat=repeat, warmup=warmup)
    perf_report.append((name, measured))
    assert measured < BUDGET_MS[name], (
        f"{name}: {measured:.1f} ms exceeds budget {BUDGET_MS[name]:.1f} ms"
    )
    return measured


# ---------------------------------------------------------------------------
# 1. LQD slice calibration — the per-(ticker, expiry) fit behind every refit.
# ---------------------------------------------------------------------------


def test_perf_lqd_slice_fit(perf_report):
    """Seven-parameter LQD fit to the note's 40-point SVI benchmark slice."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 40)
    w_quotes = bm.SVI_RAW.total_variance(k)
    _check(
        perf_report,
        "lqd_slice_fit",
        lambda: calibrate_slice(k, w_quotes, t=bm.SVI_T, n_order=6),
        repeat=15,
    )


# ---------------------------------------------------------------------------
# 2. Graph posterior update — the 1k-node extrapolation pipeline.
# ---------------------------------------------------------------------------


def _make_big_universe(n: int = 1000):
    """Ring of ``n`` smiles plus random cross-asset chords (deterministic).

    Mirrors the fixture in test_graph_scale so the budget tracks the same
    workload the scale guard exercises.
    """
    rng = np.random.RandomState(7)
    nodes = list(range(n))
    weights: dict[tuple[int, int], float] = {}
    for i in range(n):
        weights[(i, (i + 1) % n)] = 1.0 + rng.rand()
        weights[((i + 1) % n, i)] = 1.0 + rng.rand()
    for _ in range(2 * n):
        i, j = rng.randint(0, n, size=2)
        if i != j:
            weights[(i, j)] = 0.2 * rng.rand()
    return nodes, weights


def test_perf_graph_update_1k(perf_report):
    nodes, weights = _make_big_universe(1000)
    n = len(nodes)
    rng = np.random.RandomState(11)
    baseline = rng.rand(n) + 1.0
    observed = rng.choice(n, size=25, replace=False)
    observations = baseline[observed] + 0.1 * rng.randn(25)

    def pipeline():
        graph = build_graph(nodes, weights)
        prior = build_increment_prior(
            graph, kappa=2.0, eta=5.0, ot_weight=0.1, source_allowance=0.15
        )
        return posterior_update(
            prior,
            baseline,
            baseline_precision=np.full(n, 25.0),
            observed=observed,
            observations=observations,
            observation_precision=np.full(25, 100.0),
        )

    _check(perf_report, "graph_update_1k", pipeline, repeat=5)


# ---------------------------------------------------------------------------
# 3. Local-vol Crank–Nicolson Dupire forward solve.
# ---------------------------------------------------------------------------


def test_perf_localvol_forward(perf_report):
    """Skewed bilinear grid, forward-solved to two expiries (the surface path).

    A fresh ``LocalVolModel`` is built inside each timed run: ``solve`` caches
    on the expiry tuple, so reusing one model would time a dict lookup, not the
    Crank–Nicolson sweep we care about.
    """
    k = np.array([-1.0, 0.0, 1.0])
    t = np.array([0.1, 2.0])
    # Mild negative skew + term ramp, well-posed for the Dupire forward PDE.
    sigma = np.array([[0.26, 0.20, 0.17], [0.30, 0.24, 0.21]])

    def solve_fresh():
        model = LocalVolModel(LocalVolGrid(k=k, t=t, sigma=sigma, interp="bilinear"))
        return model.solve((0.25, 1.0))

    _check(perf_report, "localvol_forward", solve_fresh, repeat=10)


# ---------------------------------------------------------------------------
# 4. De-Americanization batch — one vectorized CRR sweep over a full chain.
# ---------------------------------------------------------------------------


def test_perf_deamericanize_chain(perf_report):
    """Realistic post-filter chain (~80 quotes) inverted to European prices.

    40 strikes spanning 0.80–1.25 F, calls and puts at each — the order of a
    single equity expiry after the 4-sd wing filter, which is what the live
    quote-prep path actually de-Americanizes per expiry.
    """
    spot, t, r, q = 100.0, 0.5, 0.05, 0.02
    forward = spot * float(np.exp((r - q) * t))
    moneyness = np.linspace(0.80, 1.25, 40)
    strikes = moneyness * forward

    # Build calls and puts at every strike (200 quotes), priced American at a
    # known smile so the inputs are realistic and fully invertible.
    k = np.concatenate([strikes, strikes])
    is_call = np.concatenate([np.ones(strikes.size, bool), np.zeros(strikes.size, bool)])
    log_m = np.log(k / forward)
    sigma = 0.2 + 0.05 * log_m**2
    prices = binomial_price_batch(
        is_call, spot, k, t, sigma, r, q, n_steps=DEFAULT_BATCH_STEPS, american=True
    )

    _check(
        perf_report,
        "deamericanize_chain",
        lambda: deamericanize_batch(is_call, prices, spot, k, t, r, q),
        repeat=5,
    )

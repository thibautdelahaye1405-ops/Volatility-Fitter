"""Phase-0 golden contracts for the precision-message graph operator.

Locks the expected posterior means, variances, and receiver conditional
precisions of Docs/graph_precision_message_framework.md Section 21 (amended
2026-07-18: pairwise relation factors, canonical orientation, edge-linked
shrunk-transfer anchor) BEFORE graph/message.py exists. The checker here is
an independent brute-force dense Gaussian reference built directly from the
factor definition — Phases 1-2 must reproduce these numbers through the
production operator against the SAME fixture file.

Fixture: tests/fixtures/graph_message_golden.json. Each case:
  * factors:      p * (z[receiver] - beta * z[informer])^2   (spec 7.2)
  * clamps:       hard-known lit nodes (substituted, not solved)
  * observations: finite-precision innovation observations r*(z - value)^2
  * anchors:      innovation-anchor precision kappa * z^2    (spec 14.2)

Universal contract checked on every case: scaling ALL precisions by c leaves
every mean unchanged and divides every variance by c (units invariance).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "graph_message_golden.json"


def _load():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


_CASES = {c["name"]: c for c in _load()["cases"]}


# ------------------------------------------------------------------ reference
def reference_posterior(case: dict, scale: float = 1.0, anchors: dict | None = None):
    """Brute-force dense Gaussian solve of one fixture case.

    Free nodes get a flat prior; clamped nodes are substituted (eliminated).
    Returns (means, variances) keyed by free-node name. Raises LinAlgError if
    the system is not positive definite (the fixture set contains none)."""
    clamps = case.get("clamps", {})
    free = [n for n in case["nodes"] if n not in clamps]
    idx = {n: i for i, n in enumerate(free)}
    n = len(free)
    q = np.zeros((n, n))
    b = np.zeros(n)

    for f in case.get("factors", []):
        p = f["precision"] * scale
        beta = f["beta"]
        rec, inf = f["receiver"], f["informer"]
        # u = e_rec - beta * e_inf over (free ∪ clamped); expand p * (u.z)^2.
        terms = []  # (free index | None, coefficient, clamped value | None)
        for node, coef in ((rec, 1.0), (inf, -beta)):
            if node in clamps:
                terms.append((None, coef, clamps[node]))
            else:
                terms.append((idx[node], coef, None))
        const = sum(c * v for i, c, v in terms if i is None)
        live = [(i, c) for i, c, _v in terms if i is not None]
        for i, ci in live:
            for j, cj in live:
                q[i, j] += p * ci * cj
            b[i] += -p * ci * const
    for node, ob in case.get("observations", {}).items():
        r = ob["precision"] * scale
        q[idx[node], idx[node]] += r
        b[idx[node]] += r * ob["value"]
    for node, kappa in (anchors or {}).items():
        q[idx[node], idx[node]] += kappa * scale

    cov = np.linalg.inv(q)  # LinAlgError ⇔ improper system
    mean = cov @ b
    return (
        {nname: float(mean[i]) for nname, i in idx.items()},
        {nname: float(cov[i, i]) for nname, i in idx.items()},
    )


def incident_q(case: dict, node: str) -> float:
    """Receiver conditional precision via the spec-7.6 unit mapping."""
    total = 0.0
    for f in case.get("factors", []):
        if f["receiver"] == node:
            total += f["precision"]
        elif f["informer"] == node:
            total += f["precision"] * f["beta"] ** 2
    return total


def _case_anchors(case: dict) -> dict | None:
    """Node-linked anchor of spec 14.2 (chosen 2026-07-18): kappa is a FIXED
    per-node constant carried explicitly by the fixture's rho_cases — it is
    calibrated once from the primary relation class and NOT rescaled as
    corroborating edges arrive."""
    subs = case.get("rho_cases")
    return dict(subs[0].get("kappa") or {}) or None if subs else None


# --------------------------------------------------------------------- checks
def _check_expected(case: dict, anchors: dict | None = None,
                    mean_key: str = "mean", var_key: str = "var",
                    expected: dict | None = None) -> None:
    exp = expected if expected is not None else case["expected"]
    means, variances = reference_posterior(case, anchors=anchors)
    for node, m in exp.get(mean_key, {}).items():
        assert means[node] == pytest.approx(m, abs=1e-12), (case["name"], node)
    for node, v in exp.get(var_key, {}).items():
        assert variances[node] == pytest.approx(v, abs=1e-12), (case["name"], node)
    for node, expected_q in exp.get("q", {}).items():
        assert incident_q(case, node) == pytest.approx(expected_q, abs=1e-12)


@pytest.mark.parametrize(
    "name",
    [n for n, c in _CASES.items() if "expected" in c],
)
def test_golden_case(name: str) -> None:
    _check_expected(_CASES[name])


@pytest.mark.parametrize("name", sorted(_CASES))
def test_units_invariance(name: str) -> None:
    """Scaling every precision by c preserves means and divides vars by c."""
    case = _CASES[name]
    anchors = _case_anchors(case)
    m1, v1 = reference_posterior(case, scale=1.0, anchors=anchors)
    m4, v4 = reference_posterior(case, scale=4.0, anchors=anchors)
    for node in m1:
        assert m4[node] == pytest.approx(m1[node], abs=1e-12)
        assert v4[node] == pytest.approx(v1[node] / 4.0, abs=1e-12)


def test_calendar_precision_moves_bands_not_means() -> None:
    """Spec 21.1: edge precision changes posterior SD, never the mean."""
    case = _CASES["calendar_full_transmission"]
    m_lo, v_lo = reference_posterior(case, scale=0.25)
    m_hi, v_hi = reference_posterior(case, scale=25.0)
    for node in m_lo:
        assert m_lo[node] == pytest.approx(m_hi[node], abs=1e-12)
        assert v_lo[node] > v_hi[node]


def test_multi_hop_high_precision_source_limit() -> None:
    """Spec 21.6: the high-precision-source limit recovers pure edge noise."""
    case = dict(_CASES["multi_hop_variance"])
    limit = case["high_precision_source_limit"]
    case["observations"] = {
        "A": {"value": 1.0, "precision": limit["observation_precision"]}
    }
    _means, variances = reference_posterior(case)
    for node, v in limit["var"].items():
        assert variances[node] == pytest.approx(v, rel=1e-9)


def test_dead_informer_zero_dilution_and_proper() -> None:
    """Spec 21.11: a configured-precise but information-free informer neither
    dilutes the lit message nor makes the system improper."""
    case = _CASES["dead_informer"]
    means, variances = reference_posterior(case)  # inv() proves properness
    assert means["C"] == pytest.approx(1.5 * 0.8, abs=1e-12)
    assert variances["C"] == pytest.approx(0.25, abs=1e-12)  # 1/p_lit exactly
    assert variances["D"] > variances["C"]  # informed only through C


@pytest.mark.parametrize(
    "name", [n for n, c in _CASES.items() if "rho_cases" in c]
)
def test_shrunk_transfer_rho_cases(name: str) -> None:
    """Spec 21.12: the node-linked anchor gives single-source transfer
    rho*beta*z exactly (rho=1 -> kappa=0 -> full transmission), and a FIXED
    kappa lifts two agreeing equal sources to 2rho/(1+rho) per unit beta —
    the corroboration behaviour validated on the stored benchmark rows
    (single-source 0.391 -> predicted 0.563 vs measured 0.561)."""
    case = _CASES[name]
    for sub in case["rho_cases"]:
        anchors = dict(sub.get("kappa") or {}) or None
        means, variances = reference_posterior(case, anchors=anchors)
        for node, m in sub["expected_mean"].items():
            assert means[node] == pytest.approx(m, abs=1e-12)
        for node, v in sub["expected_var"].items():
            assert variances[node] == pytest.approx(v, abs=1e-12)


def test_repeated_path_beats_naive_precision_addition() -> None:
    """Spec 21.8: two routes from one uncertain source are NOT two
    observations — the global variance must exceed the naive path-sum claim."""
    case = _CASES["repeated_path_no_double_count"]
    _means, variances = reference_posterior(case)
    assert variances["T"] == pytest.approx(5.0 / 12.0, abs=1e-12)
    naive = case["naive_path_sum_var"]["T"]
    assert variances["T"] > naive + 0.05  # falsely-tight naive claim rejected

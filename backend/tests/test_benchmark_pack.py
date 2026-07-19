"""Benchmark pack (backtest.benchmark_pack): chunking, part-file resume,
aggregation math and the HTML artifact — the pure parts (the heavy LOO sweep
itself is exercised by the fixtures-driven run in the user's window).
"""

from __future__ import annotations

import json

import pytest

from backtest import benchmark_pack as bp


def _row(regime="spike_aug2024", design="full_loo", ssr=0, kind="name",
         res_atm=0.001, base_atm=0.003, zeta=0.5, **kw) -> dict:
    row = {
        "regime": regime, "design": design, "ssr": ssr, "kind": kind,
        "ticker": kw.get("ticker", "AAPL"), "expiry": "2024-09-20",
        "as_of": kw.get("as_of", "2024-08-05"),
        "res_atm": res_atm, "base_atm": base_atm,
        "res_skew": 0.01, "base_skew": 0.02,
        "res_curv": 0.1, "base_curv": 0.2,
        "wing_wing_g": kw.get("wing_g", 20.0), "wing_wing_b": kw.get("wing_b", 30.0),
        "zeta": zeta,
    }
    row.update(kw)
    return row


def test_chunk_ranges_cover_everything_without_overlap():
    assert bp.chunk_ranges(19, 4) == [(0, 4), (4, 8), (8, 12), (12, 16), (16, 19)]
    assert bp.chunk_ranges(4, 4) == [(0, 4)]
    assert bp.chunk_ranges(0, 4) == []


def test_summarize_by_skill_math():
    rows = [_row(res_atm=0.001, base_atm=0.003), _row(res_atm=-0.001, base_atm=-0.003)]
    (rec,) = bp.summarize_by(rows, ("design", "ssr"))
    assert rec["design"] == "full_loo" and rec["ssr"] == 0 and rec["n"] == 2
    assert rec["atm_graph_rms"] == pytest.approx(10.0)  # 0.001 -> 10 bp RMS
    assert rec["atm_base_rms"] == pytest.approx(30.0)
    assert rec["atm_skill"] == pytest.approx(20.0)  # positive = graph beats prior
    assert rec["wing_graph"] == pytest.approx(20.0)
    assert rec["zeta_mean"] == pytest.approx(0.5)


def test_summarize_by_groups_and_tolerates_missing():
    rows = [
        _row(design="full_loo", kind="index"),
        _row(design="full_loo", kind="name"),
        _row(design="liquid_split", wing_g=None, wing_b=None, zeta=None),
    ]
    by_kind = bp.summarize_by([r for r in rows if r["design"] == "full_loo"], ("kind",))
    assert [r["kind"] for r in by_kind] == ["index", "name"]
    (liquid,) = bp.summarize_by([rows[2]], ("design",))
    assert liquid["wing_graph"] is None and liquid["zeta_mean"] is None
    assert liquid["atm_skill"] is not None  # residuals still present


def test_parts_roundtrip_and_resume_skip(tmp_path, monkeypatch, capsys):
    from backtest.graph_edges import EdgeConfig

    monkeypatch.setattr(bp, "RESULTS_DIR", str(tmp_path))
    calls: list[tuple] = []
    seeds: list[int] = []

    def fake_loo(regime, designs, r_values, max_pairs, cfg, pair_range=None,
                 eta_scale=1.0, history_rows=None, lambda_scale=0.0, nu=0.1,
                 msg=None):
        calls.append(pair_range)
        seeds.append(len(history_rows or []))
        return [_row(as_of=f"day{pair_range[0]}")]

    monkeypatch.setattr(bp, "run_loo", fake_loo)
    monkeypatch.setattr(bp, "_n_pairs", lambda regime: 5)

    bp.run_regime("spike_aug2024", ("full_loo",), (0.0,), chunk=2, cfg=EdgeConfig())
    assert calls == [(0, 2), (2, 4), (4, 5)]
    # Each chunk is seeded with every EARLIER same-tag part's rows (the idio
    # band floor's cross-chunk innovation history): 0, then 1, then 2 rows.
    assert seeds == [0, 1, 2]

    calls.clear()
    bp.run_regime("spike_aug2024", ("full_loo",), (0.0,), chunk=2, cfg=EdgeConfig())
    assert calls == []  # every part exists -> fully resumed, nothing recomputed
    assert "skipped" in capsys.readouterr().out

    rows = bp.load_parts("spike_aug2024")
    assert len(rows) == 3
    assert all(r["eta"] == 1.0 for r in rows)  # provenance stamp on every row
    assert bp.load_parts("other_regime") == []

    # A TAGGED sweep coexists with the untagged parts instead of being skipped.
    calls.clear()
    bp.run_regime("spike_aug2024", ("liquid_split",), (0.0,), chunk=2,
                  cfg=EdgeConfig(), eta_scale=10.0, tag="_topofix_eta10")
    assert calls == [(0, 2), (2, 4), (4, 5)]  # ran despite existing untagged parts
    assert (tmp_path / "spike_aug2024_pairs00-02_topofix_eta10.json").exists()
    assert seeds[-3:] == [0, 1, 2]  # tagged sweep never seeds from untagged parts


def test_load_parts_dedupes_overlapping_chunks(tmp_path, monkeypatch):
    """A smoke part (chunk 1) overlapping the full run's part (chunk 2) must
    not double-count its rows — dedupe on (regime, day, design, R, node)."""
    monkeypatch.setattr(bp, "RESULTS_DIR", str(tmp_path))
    row = _row(as_of="2024-08-05")
    (tmp_path / "spike_aug2024_pairs00-01.json").write_text(
        json.dumps({"regime": "spike_aug2024", "pairs": [0, 1], "rows": [row]})
    )
    (tmp_path / "spike_aug2024_pairs00-02.json").write_text(
        json.dumps({"regime": "spike_aug2024", "pairs": [0, 2],
                    "rows": [row, _row(as_of="2024-08-06")]})
    )
    rows = bp.load_parts()
    assert len(rows) == 2  # the overlapping row counted once
    assert sorted({r["as_of"] for r in rows}) == ["2024-08-05", "2024-08-06"]


def test_report_html_and_json(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "RESULTS_DIR", str(tmp_path))
    rows = [
        _row(design="full_loo", ssr=0), _row(design="full_loo", ssr=1),
        _row(design="liquid_split", ssr=0, kind="name"),
        _row(regime="low_jul2023", design="full_loo", ssr=0),
    ]
    (tmp_path / "spike_aug2024_pairs00-02.json").write_text(
        json.dumps({"regime": "spike_aug2024", "pairs": [0, 2], "rows": rows})
    )
    html_path, json_path = bp.write_report()

    html = open(html_path, encoding="utf-8").read()
    assert "benchmark pack" in html
    assert "Aug-2024 vol spike" in html and "Jul-2023 calm" in html
    assert "Full-LOO ATM skill" in html and "Methodology" in html
    assert "By design" in html and "asset kind" in html

    payload = json.load(open(json_path, encoding="utf-8"))
    assert payload["nRows"] == 4
    assert {r["regime"] for r in payload["byDesign"]} == {"spike_aug2024", "low_jul2023"}


def test_report_requires_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "RESULTS_DIR", str(tmp_path / "missing"))
    with pytest.raises(SystemExit):
        bp.write_report()

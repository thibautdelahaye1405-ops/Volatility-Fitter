# Vol Fitter

Implied-volatility surface fitter with graph-based extrapolation of sparse
smile observations to a full universe of smiles (across expiries and assets).

- Roadmap: see [ROADMAP.md](ROADMAP.md)
- Technical notes: see [Docs/](Docs/) (LQD smile model, OT-Bayesian graph extrapolation)

## Layout

```
backend/   Python quant engine + FastAPI service (package: volfit)
frontend/  React + TypeScript UI (Vite, Tailwind)
Docs/      Technical notes (LaTeX)
```

## Backend quickstart

```powershell
python -m venv .venv
.venv\Scripts\pip install -e backend[dev]
cd backend; ..\.venv\Scripts\python -m pytest tests -q   # 74 tests, ~3 s
```

## End-to-end engine demo

```powershell
.venv\Scripts\python backend\demo.py
```

Synthetic chain -> implied forwards -> LQD calibration -> calendar-constrained
surface -> graph extrapolation of a vol shock with credible bands.

## Frontend quickstart

```powershell
cd frontend
npm install
npm run dev
```

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
.venv\Scripts\python -m pytest backend/tests -q
```

## Frontend quickstart

```powershell
cd frontend
npm install
npm run dev
```

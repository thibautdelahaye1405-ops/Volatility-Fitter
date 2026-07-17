# Single-tenant container deployment (hosting track, FORWARD ROADMAP v2)

One container per client desk. Each instance owns its AppState, its SQLite
volume (universes, fit history, governance manifests, priors) and connects
with the **desk's own feed credentials** (BYO entitlement — settled 2026-07-10:
we ship computation + surfaces + lineage, never market data). This dodges the
multi-tenancy rewrite entirely: isolation is by construction, SQLite stays
viable, and the workspace/governance work (R1 items 8-9) already made the
state serializable and replayable per instance.

## Run

```bash
cp deploy/client.env.example deploy/client.env   # fill in the desk's creds
docker compose -f deploy/docker-compose.yml up --build
# -> http://localhost:8000  (UI + API, single origin)
```

Or plain docker, from the repo root:

```bash
docker build -f deploy/Dockerfile -t volfit .
docker run -p 8000:8000 -v volfit-data:/data --env-file deploy/client.env volfit
```

## What the image is

* **Stage 1** builds the React bundle; **stage 2** is `python:3.11-slim` with
  the `volfit` package (`[api]` extra + httpx/yfinance/duckdb) and the bundle
  at `frontend/dist`, where `volfit.api.frontend` finds it — the same
  single-origin serving the desktop build uses (`VOLFIT_SERVE_FRONTEND=1`,
  `VOLFIT_HOST=0.0.0.0`; both are no-ops for the dev workflow, which stays
  loopback + Vite).
* State lives on the `/data` volume via `VOLFIT_DB` — recreate the container
  freely, the desk's history survives.
* `HEALTHCHECK` reads `/settings/options` — a cheap state read that never
  probes a feed or triggers a fit.

## Deliberate v1 boundaries

* **No auth in the container** — an ingress (reverse proxy with TLS + auth)
  fronts each instance; roadmap defers product auth to R4.
* **No Bloomberg in the container** — xbbg/blpapi need a Terminal on the same
  machine; Bloomberg desks run the desktop build (`backend/desktop.py` / the
  PyInstaller exe).
* **One desk per container** — scaling is more services in the compose file,
  each with its own volume + env file. No shared anything.

## Validation state (2026-07-17 spike)

Docker is not installed on the dev box, so the image build itself has not
run here. What IS validated natively: the single-origin serving path the
image uses (`VOLFIT_SERVE_FRONTEND=1` + built bundle → `/` serves the UI and
the API answers on the same origin — smoke-tested on a scratch port;
`tests/test_frontend_mount.py` locks the mount semantics), and the env
surface (`VOLFIT_HOST`/`VOLFIT_PORT`/`VOLFIT_DB`/provider keys) — all read
by `backend/serve.py`. First `docker build` on a Docker-equipped machine is
the remaining step; expected rough edges: numba/llvmlite wheel pull on
slim (manylinux wheels exist for 3.11), and image size (~1.5 GB with numba
+ scipy — acceptable for v1, trimmable later).

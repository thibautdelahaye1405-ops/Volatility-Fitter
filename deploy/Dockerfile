# Single-tenant vol-fitter instance (FORWARD ROADMAP v2, hosting track).
#
# One container per client desk: own AppState, own SQLite volume, the
# client's OWN feed credentials via environment (BYO entitlement — we ship
# computation + surfaces + lineage, never market data). Auth/TLS live at the
# ingress in front of this container (deferred to R4 by the roadmap).
#
# Build from the REPO ROOT (the build context needs backend/ and frontend/):
#
#   docker build -f deploy/Dockerfile -t volfit:latest .
#
# Run (state persisted under ./data, creds in deploy/client.env):
#
#   docker run -p 8000:8000 -v $(pwd)/data:/data --env-file deploy/client.env volfit

# ---- Stage 1: the React bundle ---------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the API + single-origin serving ------------------------------
FROM python:3.11-slim
WORKDIR /app

# The layout mirrors the source checkout so volfit.api.frontend's dist
# resolution (<repo>/frontend/dist) works unchanged.
COPY backend/ backend/
COPY --from=frontend /build/dist frontend/dist/

# numba pulls llvmlite (manylinux wheels — no compiler needed on slim).
# providers = httpx/yfinance for the BYO feeds; Bloomberg (xbbg/blpapi) is
# deliberately NOT installed: a Terminal cannot live in a container — desks
# on Bloomberg run the desktop build instead.
RUN pip install --no-cache-dir ./backend[api] httpx yfinance duckdb

# Single-tenant state on a volume; wipe the container, keep the desk's
# universes / fit history / governance manifests.
ENV VOLFIT_DB=/data/volfit.sqlite \
    VOLFIT_HOST=0.0.0.0 \
    VOLFIT_PORT=8000 \
    VOLFIT_SERVE_FRONTEND=1
VOLUME /data
EXPOSE 8000

# Cheap state read — no feed probe, no fit (quality/feed endpoints touch the
# network and must not gate container health).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import httpx; httpx.get('http://127.0.0.1:8000/settings/options', timeout=4).raise_for_status()"

WORKDIR /app/backend
CMD ["python", "serve.py"]

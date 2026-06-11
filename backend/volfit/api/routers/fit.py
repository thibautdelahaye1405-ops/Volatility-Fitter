"""Surface-fit endpoints: synchronous POST and streaming WebSocket.

POST /fit/surface fits every expiry of one ticker sequentially (warm start,
calendar floor — the volfit.calib.calibrate_surface recipe) and caches each
slice so subsequent GET /smiles serve the surface-consistent fit.

WS /ws/fit/surface accepts the same JSON body and streams one
{"type": "progress"} frame after each expiry, then {"type": "done"} with the
full POST-shaped result. Slice fits are CPU-bound scipy work, so each one
runs on a worker thread via anyio.to_thread; the loop is replicated here
(rather than calling service.fit_surface) so progress frames can be awaited
*between* expiries.
"""

from __future__ import annotations

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Request, WebSocket

from volfit.api import service
from volfit.api.schemas import SurfaceFitRequest, SurfaceFitResponse
from volfit.api.state import FitRecord, UnknownNodeError
from volfit.calib.calendar import calendar_violation

router = APIRouter()


@router.post("/fit/surface", response_model=SurfaceFitResponse)
def fit_surface(body: SurfaceFitRequest, request: Request) -> SurfaceFitResponse:
    try:
        return service.fit_surface(
            request.app.state.volfit, body.ticker, body.fitMode, body.enforceCalendar
        )
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.websocket("/ws/fit/surface")
async def fit_surface_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    state = websocket.app.state.volfit
    try:
        body = SurfaceFitRequest.model_validate(await websocket.receive_json())
        plan = await anyio.to_thread.run_sync(
            service.surface_inputs, state, body.ticker, body.fitMode
        )

        prev = None
        residuals: list[float] = []
        fitted = []
        for index, (iso, prepared, weights) in enumerate(plan):
            result = await anyio.to_thread.run_sync(
                service.fit_surface_slice,
                state,
                body.ticker,
                iso,
                prepared,
                weights,
                prev,
                body.enforceCalendar,
            )
            residuals.append(
                0.0 if prev is None else calendar_violation(prev.slice, result.slice)
            )
            state.store_fit(
                service.fit_key(state, body.ticker, iso, body.fitMode),
                FitRecord(prepared=prepared, result=result),
            )
            fitted.append((iso, result))
            await websocket.send_json(
                {
                    "type": "progress",
                    "expiry": iso,
                    "index": index,
                    "total": len(plan),
                    "maxIvErrorBp": result.max_iv_error * 1e4,
                }
            )
            prev = result

        response = service.assemble_surface_response(
            state, body.ticker, body.fitMode, fitted, residuals
        )
        await websocket.send_json({"type": "done", "result": response.model_dump()})
    except UnknownNodeError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
    finally:
        await websocket.close()

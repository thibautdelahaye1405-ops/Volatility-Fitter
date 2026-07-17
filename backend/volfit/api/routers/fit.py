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
from volfit.api.state import UnknownNodeError
from volfit.calib.calendar import calendar_violation_windowed, common_support

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

        if body.enforceCalendar and state.options().surfaceSolver == "symmetric":
            # Symmetric pipeline: the whole run happens on ONE worker thread
            # (independent fits -> screen -> component repair); each slice's
            # progress frame is sent live from that thread via the portal.
            def send_progress(iso: str, index: int, total: int, err_bp: float):
                anyio.from_thread.run(
                    websocket.send_json,
                    {
                        "type": "progress",
                        "expiry": iso,
                        "index": index,
                        "total": total,
                        "maxIvErrorBp": err_bp,
                    },
                )

            response = await anyio.to_thread.run_sync(
                service.fit_surface,
                state,
                body.ticker,
                body.fitMode,
                True,
                send_progress,
            )
            await websocket.send_json({"type": "done", "result": response.model_dump()})
            return

        state.set_spot_shift(body.ticker, 0.0)  # re-anchor: fit at the chain's spot
        plan = await anyio.to_thread.run_sync(
            service.surface_inputs, state, body.ticker, body.fitMode
        )

        prev = None
        prev_display = None
        prev_k = None
        residuals: list[float] = []
        fitted = []
        for index, (iso, prepared) in enumerate(plan):
            # Calendar-couple + cache + re-point + persist in one worker-thread
            # step (the shared service helper), so progress frames can be awaited
            # between expiries. ``prev_display`` carries the overlay's calendar
            # floor; ``prev_k`` the common-support confinement window.
            record = await anyio.to_thread.run_sync(
                service.fit_and_commit_slice,
                state,
                body.ticker,
                iso,
                prepared,
                prev,
                body.enforceCalendar,
                body.fitMode,
                prev_display,
                prev_k,
            )
            result = record.result
            cur_k = service.retained_k(state, body.ticker, iso, prepared)
            residuals.append(
                0.0
                if prev is None
                else calendar_violation_windowed(
                    prev.slice, result.slice, common_support(prev_k, cur_k)
                )
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
            prev_display = record.display
            prev_k = cur_k

        response = service.assemble_surface_response(
            state, body.ticker, body.fitMode, fitted, residuals
        )
        await websocket.send_json({"type": "done", "result": response.model_dump()})
    except UnknownNodeError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
    finally:
        await websocket.close()

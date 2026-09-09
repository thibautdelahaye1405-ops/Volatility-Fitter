"""Background jobs for the macro tools: a workflow outlives any host's tool-call budget.

Chat hosts cap a single tool call at an undocumented duration, and a desk
routine on live Bloomberg chains runs for minutes. So ``run_desk_workflow``
does not run inside its own call: it starts a ``Job`` on the server's event
loop and waits for it up to ``wait_seconds``, forwarding the job's progress to
the caller. If the job finishes in time the call returns its full result; if
not, the call returns a handle (``jobId``, the steps so far) and
``wait_for_workflow`` resumes the wait and returns the same full result when
the job completes — the chart renders from whichever call carries it.

One registry per server process; the app runs one calibration at a time, so
one workflow at a time is the honest concurrency (a second start while one
runs is refused with the running job's handle).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from mcp.server.mcpserver import Context
from mcp.types import CallToolResult


@dataclass
class Progress:
    """The latest progress line a job reported (the sink ``ops`` writes to)."""

    done: float = 0.0
    total: float = 1.0
    message: str = ""

    async def report_progress(self, progress: float, total: float | None = None, message: str | None = None) -> None:
        """Same signature as ``Context.report_progress`` so ``ops`` can write to either."""
        self.done = float(progress)
        if total:
            self.total = float(total)
        if message is not None:
            self.message = message


@dataclass
class Job:
    kind: str
    args: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started: float = field(default_factory=monotonic)
    progress: Progress = field(default_factory=Progress)
    steps: list[dict[str, Any]] = field(default_factory=list)  # the runner appends as it goes
    result: CallToolResult | None = None
    error: str | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[Any] | None = None

    @property
    def running(self) -> bool:
        return not self.done.is_set()

    @property
    def elapsed(self) -> float:
        return round(monotonic() - self.started, 1)

    def handle(self) -> dict[str, Any]:
        """The status a caller sees while (or after) the job runs."""
        return {
            "jobId": self.id,
            "kind": self.kind,
            "running": self.running,
            "elapsedSeconds": self.elapsed,
            "progress": {"done": self.progress.done, "total": self.progress.total, "message": self.progress.message},
            "steps": list(self.steps),
            "error": self.error,
        }


class JobRegistry:
    """The server's jobs (one running at a time), by id, with the last one remembered."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._last: Job | None = None

    @property
    def running(self) -> Job | None:
        return self._last if self._last is not None and self._last.running else None

    def get(self, job_id: str | None) -> Job | None:
        if job_id:
            return self._jobs.get(job_id)
        return self._last

    def start(self, kind: str, args: dict[str, Any], runner: Callable[[Job], Awaitable[CallToolResult]]) -> Job:
        """Start ``runner(job)`` on the event loop; refuses while another job runs."""
        if self.running is not None:
            raise RuntimeError(f"a {self.running.kind} job ({self.running.id}) is still running; wait for it first")
        job = Job(kind=kind, args=args)

        async def _run() -> None:
            try:
                job.result = await runner(job)
            except Exception as exc:  # the job's own failure is its result, not the server's
                job.error = f"{type(exc).__name__}: {exc}"[:500]
            finally:
                job.done.set()

        job.task = asyncio.create_task(_run())
        self._jobs[job.id] = job
        self._last = job
        return job

    async def wait(self, job: Job, ctx: Context | None, wait_seconds: float, poll: float = 0.5) -> bool:
        """Wait up to ``wait_seconds`` for ``job``, forwarding its progress to
        ``ctx`` as it changes; True when the job finished within the budget."""
        t0 = monotonic()
        last = None
        while job.running and monotonic() - t0 < wait_seconds:
            p = job.progress
            snapshot = (p.done, p.total, p.message)
            if ctx is not None and snapshot != last:
                last = snapshot
                try:
                    await ctx.report_progress(p.done, max(p.total, 1.0), p.message)
                except Exception:  # a client without progress support
                    pass
            try:
                await asyncio.wait_for(job.done.wait(), timeout=poll)
            except asyncio.TimeoutError:
                continue
        return not job.running

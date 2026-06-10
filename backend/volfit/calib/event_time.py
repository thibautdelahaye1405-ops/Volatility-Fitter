"""Event-dilated time for term-structure interpolation.

Scheduled events (earnings, macro prints, elections) concentrate variance on
single dates. Interpolating ATM total variance linearly in *calendar* time
smears that variance; interpolating in a dilated clock

    tau(T) = T + sum_{t_e <= T} omega_e

(each event adds ``omega_e`` years' worth of typical diffusion variance)
keeps the forward variance between expiries flat away from events and lumps
the event variance exactly at the event date. The clock is toggleable: with
no events (or disabled) it reduces to the identity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Event:
    """One scheduled event at year-fraction ``time`` adding ``weight`` years
    of equivalent diffusion time."""

    time: float
    weight: float
    label: str = ""


@dataclass(frozen=True)
class EventClock:
    """Piecewise-linear dilated clock tau(T); slope 1 with jumps at events."""

    events: tuple[Event, ...] = ()
    enabled: bool = True

    def dilated_time(self, t: np.ndarray | float) -> np.ndarray | float:
        """tau(T) = T + sum of weights of events at or before T."""
        t_arr = np.asarray(t, dtype=float)
        if not self.enabled or not self.events:
            return t_arr if t_arr.ndim else float(t_arr)
        bump = np.zeros_like(t_arr)
        for event in self.events:
            bump = bump + np.where(t_arr >= event.time, event.weight, 0.0)
        out = t_arr + bump
        return out if out.ndim else float(out)

    def interpolate_total_variance(
        self,
        t_query: np.ndarray | float,
        expiries: np.ndarray,
        total_variance: np.ndarray,
    ) -> np.ndarray | float:
        """Interpolate w(T) linearly in dilated time (flat forward variance
        per dilated-time unit between quoted expiries).

        Extrapolation keeps the nearest segment's variance *rate* in dilated
        time, which is the natural short/long-end behavior.
        """
        expiries = np.asarray(expiries, dtype=float)
        w = np.asarray(total_variance, dtype=float)
        order = np.argsort(expiries)
        tau_nodes = np.atleast_1d(self.dilated_time(expiries[order]))
        w_nodes = w[order]

        tau_q = np.atleast_1d(self.dilated_time(t_query))
        out = np.interp(tau_q, tau_nodes, w_nodes)
        # Rate-preserving extrapolation outside the quoted range.
        low, high = tau_q < tau_nodes[0], tau_q > tau_nodes[-1]
        if np.any(low):
            out[low] = w_nodes[0] * tau_q[low] / tau_nodes[0]
        if np.any(high):
            rate = (
                (w_nodes[-1] - w_nodes[-2]) / (tau_nodes[-1] - tau_nodes[-2])
                if w_nodes.size > 1
                else w_nodes[-1] / tau_nodes[-1]
            )
            out[high] = w_nodes[-1] + rate * (tau_q[high] - tau_nodes[-1])
        return out if np.ndim(t_query) else float(out[0])

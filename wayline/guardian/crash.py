"""Crash detection from the device's high-g IMU, corroborated by vehicle signals.

A crash is declared when a high-g horizontal pulse integrates to a meaningful
change in velocity (delta-V) and the car's own wheel speed agrees (or the pulse is
too large / lateral / at standstill to need agreement). Rollover is detected from
the gravity vector; a CAN airbag-deployment signal is always treated as severe.

Rejected by design: potholes and speed bumps (vertical, tiny delta-V), hard
braking (long ~1 g, never crosses the trigger), door slams / a knocked device
(short spike, small delta-V, wheel speed unchanged).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .types import Severity

G = 9.80665


@dataclass(frozen=True)
class ImuSample:
    t: float
    ax: float  # m/s^2, + = forward
    ay: float  # m/s^2, + = left
    az: float  # m/s^2, + = up (reads ~+9.81 when level and still)


@dataclass(frozen=True)
class CrashTuning:
    trigger_g: float = 3.0           # horizontal |a| that opens an impact window
    release_g: float = 1.0
    max_window_s: float = 0.3
    min_delta_v_kph: float = 12.0    # below this: bump, not a crash
    moderate_delta_v_kph: float = 20.0
    severe_delta_v_kph: float = 40.0
    confirm_window_s: float = 1.5    # time allowed for wheel speed to corroborate
    speed_drop_fraction: float = 0.5
    rollover_deg: float = 60.0
    rollover_hold_s: float = 1.0
    cooldown_s: float = 30.0


@dataclass(frozen=True)
class CrashEvent:
    t: float
    severity: Severity
    delta_v_kph: float
    peak_g: float
    direction: str            # frontal | rear | left | right | rollover | unknown
    speed_before_kph: float
    rollover: bool = False
    airbag: bool = False

    def describe(self) -> str:
        bits = [f"{self.direction} impact" if self.direction not in ("rollover", "unknown") else self.direction]
        if self.delta_v_kph > 0:
            bits.append(f"Δv {self.delta_v_kph:.0f} km/h")
        if self.peak_g > 0:
            bits.append(f"peak {self.peak_g:.1f} g")
        if self.airbag:
            bits.append("airbag deployed")
        if self.rollover and self.direction != "rollover":
            bits.append("rollover")
        return " · ".join(bits)


class CrashDetector:
    def __init__(self, tuning: CrashTuning | None = None):
        self.tuning = tuning or CrashTuning()
        self._speeds: deque[tuple[float, float]] = deque(maxlen=400)
        self._win = None            # open impact window state
        self._pending = None        # impact awaiting wheel-speed corroboration
        self._last_t: float | None = None
        self._grav = (0.0, 0.0, G)  # low-pass gravity estimate
        self._tilted_since: float | None = None
        self._last_event_t = -math.inf
        self._rollover_reported = False
        self._airbag_reported = False
        self._airbag_since: float | None = None  # airbag fired; waiting for the impact pulse to finish

    def update(self, t: float, samples: list[ImuSample], v_ego: float,
               airbag_deployed: bool = False) -> CrashEvent | None:
        tun = self.tuning
        self._speeds.append((t, v_ego))
        event: CrashEvent | None = None

        if airbag_deployed and not self._airbag_reported:
            self._airbag_reported = True
            self._airbag_since = t
            if self._pending is not None:
                event = self._make_event(self._pending, airbag=True)

        for smp in samples:
            dt = 0.0 if self._last_t is None else max(0.0, min(0.05, smp.t - self._last_t))
            self._last_t = smp.t
            impact = self._impact_step(smp, dt)
            rollover = self._rollover_step(smp, dt)
            event = event or impact or rollover

        if event is None and self._pending is not None:
            event = self._check_pending(t, v_ego)
        if event is None and self._airbag_since is not None and self._win is None:
            # airbag fired with no usable IMU pulse (or the window just closed without one)
            event = CrashEvent(t, Severity.SEVERE, 0.0, 0.0, "unknown",
                               self._speed_before(self._airbag_since) * 3.6, airbag=True)
        if event is not None and event.airbag:
            self._airbag_since = None

        if event is not None:
            if t - self._last_event_t <= tun.cooldown_s and not (event.rollover or event.airbag):
                return None
            self._last_event_t = t
            self._pending = None
        return event

    # -- impact pulse ------------------------------------------------------

    def _impact_step(self, s: ImuSample, dt: float) -> CrashEvent | None:
        tun = self.tuning
        h_g = math.hypot(s.ax, s.ay) / G
        if self._win is None:
            if h_g >= tun.trigger_g:
                self._win = {"t0": s.t, "dvx": s.ax * dt, "dvy": s.ay * dt, "peak": h_g,
                             "v0": self._speed_before(s.t)}
            return None
        w = self._win
        w["dvx"] += s.ax * dt
        w["dvy"] += s.ay * dt
        w["peak"] = max(w["peak"], h_g)
        if h_g < tun.release_g or s.t - w["t0"] >= tun.max_window_s:
            self._win = None
            return self._evaluate(w, s.t)
        return None

    def _evaluate(self, w: dict, t_end: float) -> CrashEvent | None:
        tun = self.tuning
        dv_kph = math.hypot(w["dvx"], w["dvy"]) * 3.6
        airbag = self._airbag_since is not None
        if dv_kph < tun.min_delta_v_kph and not airbag:
            return None
        direction = self._direction(w["dvx"], w["dvy"])
        candidate = {"t": t_end, "dv_kph": dv_kph, "peak": w["peak"], "direction": direction,
                     "v0": w["v0"], "dvx_kph": abs(w["dvx"]) * 3.6}
        mostly_lateral = candidate["dvx_kph"] < 0.5 * dv_kph
        if airbag or dv_kph >= tun.severe_delta_v_kph or mostly_lateral or w["v0"] < 2.0:
            return self._make_event(candidate, airbag=airbag)
        self._pending = candidate  # wait for the wheel speed to agree
        return None

    def _check_pending(self, t: float, v_ego: float) -> CrashEvent | None:
        tun = self.tuning
        p = self._pending
        drop_kph = (p["v0"] - v_ego) * 3.6
        if drop_kph >= tun.speed_drop_fraction * p["dvx_kph"] or v_ego < 1.0:
            return self._make_event(p)
        if t - p["t"] > tun.confirm_window_s:
            self._pending = None  # IMU-only event, car kept rolling: knocked device / glitch
        return None

    def _make_event(self, c: dict, airbag: bool = False) -> CrashEvent:
        tun = self.tuning
        dv = c["dv_kph"]
        sev = (Severity.SEVERE if airbag or dv >= tun.severe_delta_v_kph
               else Severity.MODERATE if dv >= tun.moderate_delta_v_kph else Severity.MINOR)
        return CrashEvent(c["t"], sev, dv, c["peak"], c["direction"], c["v0"] * 3.6, airbag=airbag)

    @staticmethod
    def _direction(dvx: float, dvy: float) -> str:
        if abs(dvx) >= abs(dvy):
            return "frontal" if dvx < 0 else "rear"
        return "right" if dvy > 0 else "left"   # pushed left => struck from the right

    def _speed_before(self, t: float) -> float:
        older = [v for (ts, v) in self._speeds if ts <= t - 0.2]
        if older:
            return older[-1]
        return self._speeds[0][1] if self._speeds else 0.0

    # -- rollover ---------------------------------------------------------------

    def _rollover_step(self, s: ImuSample, dt: float) -> CrashEvent | None:
        tun = self.tuning
        alpha = min(1.0, dt / 0.5) if dt > 0 else 0.0
        gx, gy, gz = self._grav
        self._grav = (gx + alpha * (s.ax - gx), gy + alpha * (s.ay - gy), gz + alpha * (s.az - gz))
        gx, gy, gz = self._grav
        norm = math.sqrt(gx * gx + gy * gy + gz * gz) or 1.0
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, gz / norm))))
        if tilt >= tun.rollover_deg:
            if self._tilted_since is None:
                self._tilted_since = s.t
            elif s.t - self._tilted_since >= tun.rollover_hold_s and not self._rollover_reported:
                self._rollover_reported = True
                return CrashEvent(s.t, Severity.SEVERE, 0.0, 0.0, "rollover",
                                  self._speed_before(s.t) * 3.6, rollover=True)
        else:
            self._tilted_since = None
        return None

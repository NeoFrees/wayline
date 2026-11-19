"""Driver monitoring: turns per-frame driver observations into an awareness level.

Wayline is "hands-off, eyes-on": the IR camera model reports where the driver is
looking and whether their eyes are closed. Awareness drains while the driver is
distracted and alerts escalate. If the driver still doesn't respond after the
critical alert, they are flagged UNRESPONSIVE, which triggers Emergency Stop Assist
and a Guardian check-in instead of simply handing control back to an incapacitated
person.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


@dataclass(frozen=True)
class DriverObservation:
    face_detected: bool = True
    gaze_on_road: bool = True
    eyes_closed: float = 0.0     # probability from the camera model, 0..1
    interacted: bool = False     # deliberate input this frame (button, pedal, steering nudge)


class AlertLevel(IntEnum):
    NONE = 0
    VISUAL = 1        # "Keep your eyes on the road"
    AUDIBLE = 2       # chime + "Pay attention"
    CRITICAL = 3      # continuous alarm + "Take control now"
    UNRESPONSIVE = 4  # driver did not react to the critical alert


@dataclass(frozen=True)
class DriverMonitorTuning:
    time_to_critical: float = 9.0    # s of continuous distraction until awareness reaches 0
    visual_below: float = 0.65
    audible_below: float = 0.35
    microsleep_s: float = 1.5        # eyes closed this long -> audible alert right away
    unresponsive_after: float = 6.0  # s at CRITICAL with no reaction
    recover_after: float = 0.5       # s of attentive driving that restores full awareness
    eyes_closed_threshold: float = 0.7


@dataclass(frozen=True)
class DriverState:
    awareness: float
    level: AlertLevel
    distracted: bool
    eyes_closed_for: float

    @property
    def unresponsive(self) -> bool:
        return self.level == AlertLevel.UNRESPONSIVE


class DriverMonitor:
    def __init__(self, tuning: DriverMonitorTuning | None = None):
        self.tuning = tuning or DriverMonitorTuning()
        self.awareness = 1.0
        self._eyes_closed_for = 0.0
        self._attentive_for = 0.0
        self._critical_for = 0.0
        self._unresponsive = False

    def update(self, obs: DriverObservation, dt: float, active: bool = True) -> DriverState:
        """Advance one tick. ``active`` = Wayline is steering (alerts only matter then)."""
        t = self.tuning
        eyes_closed = obs.eyes_closed >= t.eyes_closed_threshold
        distracted = (not obs.face_detected) or (not obs.gaze_on_road) or eyes_closed
        self._eyes_closed_for = self._eyes_closed_for + dt if eyes_closed else 0.0

        if distracted and not obs.interacted:
            self._attentive_for = 0.0
            if active:
                self.awareness = max(0.0, self.awareness - dt / t.time_to_critical)
        else:
            self._attentive_for += dt
            if obs.interacted or self._attentive_for >= t.recover_after:
                self._reset()

        if not active:
            # Not steering: keep tracking, but no escalation toward the stop-in-lane path.
            self._critical_for = 0.0
            self._unresponsive = False

        if self.awareness <= 0.0 and active:
            self._critical_for += dt
            if self._critical_for >= t.unresponsive_after:
                self._unresponsive = True

        if self._unresponsive:
            level = AlertLevel.UNRESPONSIVE
        elif self.awareness <= 0.0 and active:
            level = AlertLevel.CRITICAL
        elif self.awareness < t.audible_below or (active and self._eyes_closed_for >= t.microsleep_s):
            level = AlertLevel.AUDIBLE
        elif self.awareness < t.visual_below:
            level = AlertLevel.VISUAL
        else:
            level = AlertLevel.NONE

        return DriverState(self.awareness, level, distracted, self._eyes_closed_for)

    def _reset(self) -> None:
        self.awareness = 1.0
        self._critical_for = 0.0
        self._unresponsive = False

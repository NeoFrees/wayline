"""Longitudinal control: adaptive cruise (speed hold + time-gap following) and the
gentle deceleration profile used by Emergency Stop Assist."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeadInfo:
    distance: float  # m, bumper to bumper
    v_lead: float    # m/s


@dataclass(frozen=True)
class LongitudinalTuning:
    time_gap: float = 1.6        # s
    standstill_gap: float = 4.0  # m
    k_speed: float = 0.35
    k_gap: float = 0.22
    k_rel_speed: float = 0.6
    max_accel: float = 1.6       # m/s^2 comfort limits (the safety gate has the hard limits)
    min_accel: float = -3.0
    esa_decel: float = -1.5      # Emergency Stop Assist: firm but non-alarming


class LongitudinalController:
    def __init__(self, tuning: LongitudinalTuning | None = None):
        self.tuning = tuning or LongitudinalTuning()

    def update(self, v_ego: float, v_set: float, lead: LeadInfo | None = None) -> float:
        t = self.tuning
        accel = t.k_speed * (v_set - v_ego)
        if lead is not None:
            desired_gap = t.standstill_gap + t.time_gap * v_ego
            follow = t.k_gap * (lead.distance - desired_gap) + t.k_rel_speed * (lead.v_lead - v_ego)
            accel = min(accel, follow)
        return max(t.min_accel, min(t.max_accel, accel))

    def emergency_stop(self, v_ego: float) -> float:
        """Controlled stop in lane; hold the brake once stopped."""
        return self.tuning.esa_decel if v_ego > 0.3 else -1.0

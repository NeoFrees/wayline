"""Lateral control (lane centering).

Pure-pursuit on the fitted lane centre: steer toward the centre-line point one
"lookahead time" ahead. Because the target point lies on the fitted quadratic, the
lane curvature is fed forward automatically, and the closed loop on lateral offset
is ~critically damped (zeta ~= 0.71) at every speed when lookahead = v * T.

The output is a normalised steering-torque request in [-1, 1]; ``max_lat_accel`` is
the lateral acceleration the car's lane-keep actuator produces at full request
(comes from the per-vehicle port).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..perception.lanes import LaneEstimate


@dataclass(frozen=True)
class LateralTuning:
    lookahead_time: float = 1.0  # s
    min_lookahead: float = 6.0   # m
    max_lat_accel: float = 2.5   # m/s^2 at |torque| = 1 (vehicle specific)
    min_speed: float = 1.0       # m/s, below this the request is scaled to zero


@dataclass(frozen=True)
class LateralOutput:
    desired_curvature: float
    torque: float
    lookahead: float
    target_y: float


class LateralController:
    def __init__(self, tuning: LateralTuning | None = None):
        self.tuning = tuning or LateralTuning()

    def update(self, lane: LaneEstimate, v_ego: float) -> LateralOutput:
        tun = self.tuning
        if not lane.valid or v_ego < tun.min_speed:
            return LateralOutput(0.0, 0.0, 0.0, 0.0)
        lookahead = max(tun.min_lookahead, v_ego * tun.lookahead_time)
        target_y = lane.center_y_at(lookahead)
        desired_curvature = 2.0 * target_y / (lookahead * lookahead + target_y * target_y)
        torque = desired_curvature * v_ego * v_ego / tun.max_lat_accel
        torque = max(-1.0, min(1.0, torque))
        return LateralOutput(desired_curvature, torque, lookahead, target_y)

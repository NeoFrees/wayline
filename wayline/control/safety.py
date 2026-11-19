"""Actuator safety gate — the last line of defence before commands reach the car.

Mirrors the job a CAN-interface microcontroller does on the device: whatever the
planner asks for, the gate enforces hard torque and acceleration limits, limits how
fast steering torque can ramp, blocks all actuation when not engaged, and yields to
the driver immediately. On hardware this logic is duplicated in firmware on a
separate MCU so a crashed or compromised main processor cannot exceed it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SafetyLimits:
    max_torque: float = 1.0
    max_rate_up: float = 1.0      # torque units per second when |torque| increases
    max_rate_down: float = 2.0    # ... when |torque| decreases (release fast)
    max_accel: float = 2.0        # m/s^2
    min_accel: float = -3.5       # m/s^2 (aftermarket systems never command full ABS braking)
    driver_override_torque: float = 0.35  # normalised driver torque meaning "driver is steering"


@dataclass
class GateResult:
    torque: float
    accel: float
    lateral_override: bool = False
    longitudinal_override: bool = False
    violations: list[str] = field(default_factory=list)


class SafetyGate:
    def __init__(self, dt: float, limits: SafetyLimits | None = None):
        self.dt = dt
        self.limits = limits or SafetyLimits()
        self._last_torque = 0.0

    def apply(self, *, engaged: bool, torque: float, accel: float, driver_torque: float,
              brake_pressed: bool, gas_pressed: bool) -> GateResult:
        lim = self.limits
        violations: list[str] = []

        if not engaged:
            self._last_torque = 0.0
            if torque != 0.0 or accel != 0.0:
                violations.append("actuation requested while disengaged")
            return GateResult(0.0, 0.0, violations=violations)

        lateral_override = abs(driver_torque) >= lim.driver_override_torque
        target = 0.0 if lateral_override else torque
        if abs(target) > lim.max_torque:
            violations.append("torque above limit")
            target = max(-lim.max_torque, min(lim.max_torque, target))

        last = self._last_torque
        increasing = abs(target) > abs(last) and (last == 0.0 or (target > 0) == (last > 0))
        max_step = (lim.max_rate_up if increasing else lim.max_rate_down) * self.dt
        delta = target - last
        if abs(delta) > max_step:
            delta = max_step if delta > 0 else -max_step
        out_torque = last + delta
        self._last_torque = out_torque

        longitudinal_override = gas_pressed
        if brake_pressed:
            out_accel = 0.0          # the driver's brake wins; we release
        elif gas_pressed:
            out_accel = max(0.0, accel)  # never brake against the driver's foot
        else:
            out_accel = accel
        if not (lim.min_accel <= out_accel <= lim.max_accel):
            violations.append("acceleration outside limits")
            out_accel = max(lim.min_accel, min(lim.max_accel, out_accel))

        return GateResult(out_torque, out_accel, lateral_override, longitudinal_override, violations)

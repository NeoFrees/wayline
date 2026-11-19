"""Closed-loop world model for the simulator: road, vehicle dynamics, human driver, IMU and GPS.

The vehicle is simulated in road-relative (Frenet) coordinates:
    s    distance along the lane centre
    d    lateral offset from the lane centre (+ = left)
    psi  heading relative to the lane (+ = yawed left)
Steering torque maps to lateral acceleration (torque * max_lat_accel), which is
what a car's lane-keep actuator effectively provides, followed by a first-order lag.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..guardian.crash import G, ImuSample
from ..guardian.types import GpsFix
from .render import LaneScene


class Road:
    """Piecewise-constant curvature with linear (clothoid-like) transitions."""

    def __init__(self, segments: tuple[tuple[float, float], ...] | list[tuple[float, float]],
                 lane_width: float = 3.7, transition: float = 40.0):
        self.lane_width = lane_width
        xs, ys = [0.0], [segments[0][1]]
        s, prev = 0.0, segments[0][1]
        for length, k in segments:
            if k != prev:
                xs += [s, s + min(transition, length / 2)]
                ys += [prev, k]
            s += length
            prev = k
        xs.append(s)
        ys.append(prev)
        self._xs = np.array(xs)
        self._ys = np.array(ys)
        self.length = s

    def curvature_at(self, s: float) -> float:
        return float(np.interp(s, self._xs, self._ys))


@dataclass
class VehicleState:
    s: float = 0.0
    d: float = 0.0
    psi: float = 0.0
    v: float = 0.0
    a: float = 0.0
    kappa: float = 0.0        # curvature actually being driven
    heading: float = 0.0      # world heading, radians CCW from east
    east: float = 0.0
    north: float = 0.0


class Vehicle:
    def __init__(self, road: Road, v0: float, *, max_lat_accel: float = 2.5, steer_tau: float = 0.12,
                 accel_tau: float = 0.25, origin: tuple[float, float] = (34.0522, -118.2437),
                 heading_deg: float = 90.0):
        self.road = road
        self.state = VehicleState(v=v0, heading=math.radians(heading_deg),
                                  kappa=road.curvature_at(0.0))
        self.max_lat_accel = max_lat_accel
        self.steer_tau = steer_tau
        self.accel_tau = accel_tau
        self.origin = origin

    def step(self, dt: float, torque: float, accel_cmd: float, impulse_dv: float = 0.0) -> None:
        st = self.state
        v = max(st.v, 0.0)
        kappa_cmd = torque * self.max_lat_accel / max(v * v, 1.0)
        kappa_cmd = max(-0.2, min(0.2, kappa_cmd))
        st.kappa += (kappa_cmd - st.kappa) * min(1.0, dt / self.steer_tau)
        st.a += (accel_cmd - st.a) * min(1.0, dt / self.accel_tau)
        kr = self.road.curvature_at(st.s)
        s_dot = v * math.cos(st.psi) / max(0.1, 1.0 - st.d * kr)
        st.d += v * math.sin(st.psi) * dt
        st.psi += (v * st.kappa - kr * s_dot) * dt
        st.s += s_dot * dt
        st.heading += v * st.kappa * dt
        st.east += v * math.cos(st.heading) * dt
        st.north += v * math.sin(st.heading) * dt
        st.v = max(0.0, v + st.a * dt + impulse_dv)

    def scene(self) -> LaneScene:
        st = self.state
        return LaneScene(offset=st.d, heading=st.psi, curvature=self.road.curvature_at(st.s), s=st.s,
                         lane_width=self.road.lane_width)

    def gps(self) -> GpsFix:
        lat0, lon0 = self.origin
        st = self.state
        lat = lat0 + st.north / 111_320.0
        lon = lon0 + st.east / (111_320.0 * math.cos(math.radians(lat0)))
        return GpsFix(lat, lon, accuracy_m=4.0, speed_mps=st.v,
                      heading_deg=(90.0 - math.degrees(st.heading)) % 360.0)


class HumanDriver:
    """A simple attentive human: steers toward the lane centre with a little lag.

    When distracted, their grip relaxes and the steering input decays toward zero,
    so on a curve the car drifts toward the outside of the bend.
    """

    def __init__(self, max_lat_accel: float = 2.5, lookahead_s: float = 1.3, gain: float = 0.9):
        self.max_lat_accel = max_lat_accel
        self.lookahead_s = lookahead_s
        self.gain = gain
        self._torque = 0.0

    def steer(self, vehicle: Vehicle, dt: float, attentive: bool) -> float:
        st = vehicle.state
        if attentive:
            v = max(st.v, 1.0)
            look = max(8.0, v * self.lookahead_s)
            kr = vehicle.road.curvature_at(st.s)
            kappa = kr - 2.0 * (st.d + look * math.tan(st.psi)) / (look * look)
            target = self.gain * kappa * v * v / self.max_lat_accel
            self._torque += (target - self._torque) * min(1.0, dt / 0.3)
        else:
            self._torque *= math.exp(-dt / 1.2)
        # people can out-steer a lane-keep motor: up to ~3x its authority
        self._torque = max(-3.0, min(3.0, self._torque))
        return self._torque

    @staticmethod
    def pedal(v: float, v_target: float) -> float:
        return max(-2.0, min(1.2, 0.4 * (v_target - v)))


@dataclass(frozen=True)
class Impact:
    t: float
    peak_g: float
    duration: float
    direction: str = "frontal"   # frontal | rear | left | right (side the car is struck from)
    airbag: bool = False

    def unit(self) -> tuple[float, float]:
        return {"frontal": (-1.0, 0.0), "rear": (1.0, 0.0),
                "right": (0.0, 1.0), "left": (0.0, -1.0)}[self.direction]


@dataclass(frozen=True)
class Bump:
    """Non-crash jolts: potholes, speed bumps, a door slam or a knock on the device."""

    t: float
    vertical_g: float = 0.0
    horizontal_g: float = 0.0
    duration: float = 0.03


def half_sine(t: float, t0: float, duration: float) -> float:
    if t0 <= t < t0 + duration:
        return math.sin(math.pi * (t - t0) / duration)
    return 0.0


class ImuSim:
    def __init__(self, rate_hz: float = 100.0, noise: float = 0.08, seed: int = 0):
        self.period = 1.0 / rate_hz
        self.noise = noise
        self.rng = np.random.default_rng(seed)
        self._next_t = 0.0

    def sample(self, t_end: float, vehicle: Vehicle, impacts: tuple[Impact, ...],
               bumps: tuple[Bump, ...]) -> tuple[list[ImuSample], float]:
        """IMU samples up to ``t_end`` plus the forward speed change caused by impacts."""
        st = vehicle.state
        out: list[ImuSample] = []
        impulse_dv = 0.0
        while self._next_t < t_end - 1e-9:
            ts = self._next_t
            ax, ay, az = st.a, st.v * st.v * st.kappa, G
            for imp in impacts:
                p = half_sine(ts, imp.t, imp.duration) * imp.peak_g * G
                ux, uy = imp.unit()
                ax += p * ux
                ay += p * uy
                impulse_dv += p * ux * self.period
            for b in bumps:
                p = half_sine(ts, b.t, b.duration)
                az += p * b.vertical_g * G
                ax -= p * b.horizontal_g * G
            n = self.rng.normal(0.0, self.noise, 3)
            out.append(ImuSample(ts, ax + n[0], ay + n[1], az + n[2]))
            self._next_t += self.period
        return out, impulse_dv


class LeadCar:
    """A car ahead in our lane. Bumper-to-bumper distance = s - ego_s - 4.5 m (car length)."""

    def __init__(self, gap: float, v: float, schedule: tuple[tuple[float, float], ...] = ()):
        self.s = gap + 4.5
        self.v = v
        self.schedule = sorted(schedule)

    def accel_at(self, t: float) -> float:
        a = 0.0
        for t0, accel in self.schedule:
            if t >= t0:
                a = accel
        return a

    def step(self, t: float, dt: float) -> None:
        self.v = max(0.0, self.v + self.accel_at(t) * dt)
        self.s += self.v * dt

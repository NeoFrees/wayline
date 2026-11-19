"""Synthetic sensor rendering: lane markings seen from the vehicle, as BEV or camera frames."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..perception.camera import PinholeCamera
from ..perception.lanes import BevSpec

ASPHALT = 0.15
PAINT = 0.88
SKY = 0.32


@dataclass(frozen=True)
class LaneScene:
    """Ground-truth lane geometry relative to the vehicle (vehicle frame, metres/radians)."""

    offset: float          # vehicle lateral offset from lane centre (+ = left of centre)
    heading: float         # vehicle heading relative to lane direction (+ = yawed left)
    curvature: float       # lane curvature (1/m, + = bends left)
    s: float = 0.0         # distance travelled along the road (sets the dash phase)
    lane_width: float = 3.7
    line_width: float = 0.15
    dash_on: float = 3.0   # metres painted
    dash_period: float = 12.0
    hide_left: bool = False   # simulate a worn / missing marking
    hide_right: bool = False

    def centre_y(self, x):
        return -self.offset - math.tan(self.heading) * x + 0.5 * self.curvature * x * x

    def lines(self):
        """(lateral offset from lane centre, dashed?, hidden?) for each painted line."""
        w = self.lane_width
        return [
            (+w / 2, True, self.hide_left),     # divider to the lane on our left (dashed)
            (-w / 2, False, self.hide_right),   # road edge on our right (solid)
            (+1.5 * w, False, False),           # far edge of the left lane (solid)
        ]

    def marking_mask(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        yc = self.centre_y(x)
        out = np.zeros(np.shape(x), dtype=bool)
        dash = np.mod(self.s + x, self.dash_period) < self.dash_on
        for off, dashed, hidden in self.lines():
            if hidden:
                continue
            hit = np.abs(y - (yc + off)) < self.line_width / 2
            out |= (hit & dash) if dashed else hit
        return out


def render_bev(scene: LaneScene, spec: BevSpec | None = None, *, noise: float = 0.03,
               rng: np.random.Generator | None = None) -> np.ndarray:
    spec = spec or BevSpec()
    gx, gy = spec.grid()
    img = np.where(scene.marking_mask(gx, gy), PAINT, ASPHALT).astype(np.float32)
    if noise > 0:
        rng = rng or np.random.default_rng(0)
        img += rng.normal(0.0, noise, img.shape).astype(np.float32)
    return np.clip(img, 0.0, 1.0)


class CameraRenderer:
    """Renders grayscale forward-camera frames; the ground lookup is cached per camera."""

    def __init__(self, camera: PinholeCamera | None = None):
        self.camera = camera or PinholeCamera()
        cam = self.camera
        uu, vv = np.meshgrid(np.arange(cam.width) + 0.0, np.arange(cam.height) + 0.0)
        self._x, self._y, self._ground = cam.pixel_to_ground(uu, vv)
        # far-away ground blurs into haze; cap the range like a real lens/sensor would
        self._ground &= self._x < 120.0

    def render(self, scene: LaneScene, *, noise: float = 0.02,
               rng: np.random.Generator | None = None) -> np.ndarray:
        img = np.full((self.camera.height, self.camera.width), SKY, dtype=np.float32)
        img[self._ground] = ASPHALT
        paint = scene.marking_mask(self._x, self._y) & self._ground
        img[paint] = PAINT
        if noise > 0:
            rng = rng or np.random.default_rng(0)
            img += rng.normal(0.0, noise, img.shape).astype(np.float32)
        return np.clip(img, 0.0, 1.0)

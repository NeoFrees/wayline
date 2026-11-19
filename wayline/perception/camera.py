"""Forward camera model and inverse perspective mapping (camera frame -> BEV raster).

Pure NumPy so it runs anywhere; on the device this step runs on the GPU/NPU.
A real deployment calibrates ``mount_height``, ``pitch`` and the intrinsics per install
(the same way the device's online calibration does), then reuses the cached lookup table.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .lanes import BevSpec, LaneDetector, LaneEstimate


@dataclass(frozen=True)
class PinholeCamera:
    width: int = 512
    height: int = 256
    fx: float = 480.0
    fy: float = 480.0
    cx: float = 256.0
    cy: float = 128.0
    mount_height: float = 1.3  # metres above the road
    pitch: float = 0.05        # radians, positive = tilted down

    def ground_to_pixel(self, x, y):
        """Project ground points (vehicle frame, z = 0) to pixel coordinates.

        Returns (u, v, in_front) arrays; ``in_front`` is False for points behind the camera.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        s, c = np.sin(self.pitch), np.cos(self.pitch)
        z_cam = x * c + self.mount_height * s      # forward along the optical axis
        y_cam = -x * s + self.mount_height * c     # image-down
        x_cam = -y                                 # image-right
        in_front = z_cam > 0.1
        z_safe = np.where(in_front, z_cam, 1.0)
        u = self.cx + self.fx * x_cam / z_safe
        v = self.cy + self.fy * y_cam / z_safe
        return u, v, in_front

    def pixel_to_ground(self, u, v):
        """Back-project pixels onto the road plane. Returns (x, y, hits_ground)."""
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        xc = (u - self.cx) / self.fx
        yc = (v - self.cy) / self.fy
        s, c = np.sin(self.pitch), np.cos(self.pitch)
        down = s + yc * c                       # downward component of the ray (per unit z_cam)
        hits = down > 1e-3
        t = np.where(hits, self.mount_height / np.where(hits, down, 1.0), 0.0)
        x = t * (c - yc * s)
        y = -t * xc
        return x, y, hits & (x > 0)


class BevProjector:
    """Warps a camera frame onto the BEV grid with a cached nearest-neighbour lookup."""

    def __init__(self, camera: PinholeCamera | None = None, spec: BevSpec | None = None):
        self.camera = camera or PinholeCamera()
        self.spec = spec or BevSpec()
        gx, gy = self.spec.grid()
        u, v, ok = self.camera.ground_to_pixel(gx, gy)
        ui = np.round(u).astype(np.int64)
        vi = np.round(v).astype(np.int64)
        ok &= (ui >= 0) & (ui < self.camera.width) & (vi >= 0) & (vi < self.camera.height)
        self._u = np.where(ok, ui, 0)
        self._v = np.where(ok, vi, 0)
        self._ok = ok

    @property
    def coverage(self) -> np.ndarray:
        """Boolean mask of BEV cells the camera can actually see."""
        return self._ok

    def project(self, frame: np.ndarray) -> np.ndarray:
        img = np.asarray(frame, dtype=np.float32)
        if img.ndim == 3:
            img = img.mean(axis=2)
        if img.shape != (self.camera.height, self.camera.width):
            raise ValueError(f"frame must be {self.camera.height}x{self.camera.width}, got {img.shape}")
        if img.size and float(img.max()) > 1.0:
            img = img / 255.0
        bev = img[self._v, self._u]
        bev[~self._ok] = 0.0
        return bev


def extract_markings(bev: np.ndarray, spec: BevSpec, window_m: float = 0.9, gain: float = 4.0) -> np.ndarray:
    """Highlight thin bright stripes (paint) against the local road brightness.

    Subtracts a horizontal moving average so that bright-but-wide regions (sun glare,
    concrete patches) are suppressed while 10-20 cm wide paint lines survive.
    """
    k = max(3, int(round(window_m / spec.lat_res)) | 1)
    pad = k // 2
    padded = np.pad(bev, ((0, 0), (pad, pad)), mode="edge")
    csum = np.cumsum(padded, axis=1, dtype=np.float64)
    csum = np.concatenate([np.zeros((bev.shape[0], 1)), csum], axis=1)
    local_mean = (csum[:, k:] - csum[:, :-k]) / k
    ridge = np.clip((bev - local_mean) * gain, 0.0, 1.0)
    return ridge.astype(np.float32)


class CameraLanePipeline:
    """camera frame -> inverse perspective map -> marking extraction -> lane fit."""

    def __init__(self, camera: PinholeCamera | None = None, detector: LaneDetector | None = None):
        self.detector = detector or LaneDetector()
        self.projector = BevProjector(camera, self.detector.spec)

    def process(self, frame: np.ndarray) -> LaneEstimate:
        bev = self.projector.project(frame)
        return self.detector.detect(extract_markings(bev, self.detector.spec))

"""Lane-line perception on a bird's-eye-view (BEV) raster.

Coordinate convention used everywhere in Wayline (vehicle frame):
    x  metres ahead of the vehicle reference point
    y  metres to the LEFT of the vehicle centreline

Each detected lane line is a quadratic ``y = c0 + c1*x + c2*x**2`` fitted to the
marking pixels found by a sliding-window search. The lane centre is the mean of
the two lines (or one line shifted by the tracked lane width when only one is seen).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BevSpec:
    """Geometry of a bird's-eye-view raster in the vehicle frame."""

    lat_range: float = 6.0   # metres either side of the vehicle centreline
    long_range: float = 40.0  # metres ahead
    lat_res: float = 0.05    # metres per column
    long_res: float = 0.2    # metres per row

    @property
    def width(self) -> int:
        return int(round(2 * self.lat_range / self.lat_res))

    @property
    def height(self) -> int:
        return int(round(self.long_range / self.long_res))

    @property
    def center_col(self) -> float:
        """Column (fractional) that corresponds to y = 0."""
        return self.lat_range / self.lat_res - 0.5

    def col_to_y(self, col):
        return self.lat_range - (np.asarray(col, dtype=float) + 0.5) * self.lat_res

    def row_to_x(self, row):
        return (self.height - 1 - np.asarray(row, dtype=float) + 0.5) * self.long_res

    def grid(self) -> tuple[np.ndarray, np.ndarray]:
        """Metre coordinates (x, y) of every cell centre, each shaped (height, width)."""
        x = np.repeat(self.row_to_x(np.arange(self.height))[:, None], self.width, axis=1)
        y = np.repeat(self.col_to_y(np.arange(self.width))[None, :], self.height, axis=0)
        return x, y


@dataclass(frozen=True)
class LaneLine:
    coeffs: tuple[float, float, float]  # y = c0 + c1*x + c2*x^2
    n_points: int
    x_span: float  # metres of the line actually observed

    def y_at(self, x):
        c0, c1, c2 = self.coeffs
        return c0 + c1 * x + c2 * x * x


@dataclass(frozen=True)
class LaneEstimate:
    valid: bool
    left: LaneLine | None = None
    right: LaneLine | None = None
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    lane_width: float = 0.0
    confidence: float = 0.0

    @property
    def lateral_offset(self) -> float:
        """Vehicle position relative to the lane centre in metres (positive = left of centre)."""
        return -self.center[0]

    @property
    def heading_error(self) -> float:
        """Vehicle heading relative to the lane direction in radians (positive = yawed left)."""
        return -math.atan(self.center[1])

    @property
    def curvature(self) -> float:
        """Lane curvature at the vehicle in 1/m (positive = road bends left)."""
        c1, c2 = self.center[1], self.center[2]
        return 2.0 * c2 / (1.0 + c1 * c1) ** 1.5

    def center_y_at(self, x: float) -> float:
        c0, c1, c2 = self.center
        return c0 + c1 * x + c2 * x * x

    def clearances(self, half_vehicle_width: float = 0.9) -> tuple[float, float]:
        """Gap (m) between the vehicle's left/right sides and the left/right lines at x = 0.

        Negative means the vehicle is already over that line.
        """
        left_y = self.left.coeffs[0] if self.left else self.center[0] + self.lane_width / 2
        right_y = self.right.coeffs[0] if self.right else self.center[0] - self.lane_width / 2
        return left_y - half_vehicle_width, -right_y - half_vehicle_width


INVALID_LANE = LaneEstimate(valid=False)


@dataclass(frozen=True)
class LaneDetectorConfig:
    threshold: float = 0.5          # BEV intensity above which a cell is "marking"
    n_windows: int = 10
    margin_m: float = 0.7           # half-width of each search window
    min_window_pixels: int = 6
    min_line_pixels: int = 40
    min_span_m: float = 8.0         # shorter observations get a straight-line fit
    expected_width: float = 3.7
    width_bounds: tuple[float, float] = (2.6, 4.8)
    min_confidence: float = 0.3


class LaneDetector:
    """Sliding-window lane detector for BEV rasters (values in [0, 1] or [0, 255])."""

    def __init__(self, spec: BevSpec | None = None, config: LaneDetectorConfig | None = None):
        self.spec = spec or BevSpec()
        self.cfg = config or LaneDetectorConfig()
        self._width = self.cfg.expected_width  # tracked lane width, used when one line is missing

    def detect(self, bev: np.ndarray) -> LaneEstimate:
        img = np.asarray(bev, dtype=np.float32)
        if img.shape != (self.spec.height, self.spec.width):
            raise ValueError(f"BEV must be {self.spec.height}x{self.spec.width}, got {img.shape}")
        if img.size and float(img.max()) > 1.0:
            img = img / 255.0
        mask = img >= self.cfg.threshold

        left_base, right_base = self._find_bases(mask)
        left = self._trace(mask, left_base) if left_base is not None else None
        right = self._trace(mask, right_base) if right_base is not None else None
        return self._combine(left, right)

    # -- internals -------------------------------------------------------

    def _find_bases(self, mask: np.ndarray) -> tuple[float | None, float | None]:
        h = mask.shape[0]
        hist = mask[int(h * 0.4):, :].sum(axis=0).astype(float)
        smooth = np.convolve(hist, np.ones(5) / 5.0, mode="same")
        peak = float(smooth.max()) if smooth.size else 0.0
        if peak < 2.0:
            return None, None
        floor = max(2.0, 0.12 * peak)
        is_peak = np.zeros_like(smooth, dtype=bool)
        is_peak[1:-1] = (smooth[1:-1] >= smooth[:-2]) & (smooth[1:-1] > smooth[2:]) & (smooth[1:-1] >= floor)
        cols = np.flatnonzero(is_peak).astype(float)
        mid = self.spec.center_col
        left_cands = cols[cols < mid]
        right_cands = cols[cols > mid]
        # nearest candidate on each side of the vehicle = our lane's lines
        left = float(left_cands.max()) if left_cands.size else None
        right = float(right_cands.min()) if right_cands.size else None
        return left, right

    def _trace(self, mask: np.ndarray, base_col: float) -> LaneLine | None:
        cfg, spec = self.cfg, self.spec
        h, w = mask.shape
        win_h = max(1, h // cfg.n_windows)
        margin = max(2, int(round(cfg.margin_m / spec.lat_res)))
        cur = base_col
        rows_acc: list[np.ndarray] = []
        cols_acc: list[np.ndarray] = []
        misses = 0

        for i in range(cfg.n_windows):
            r_hi = h - i * win_h
            r_lo = 0 if i == cfg.n_windows - 1 else max(0, r_hi - win_h)
            # widen the search after empty windows (dash gaps, worn paint)
            m = int(margin * min(2.0, 1.0 + 0.5 * misses))
            c_lo = max(0, int(cur) - m)
            c_hi = min(w, int(cur) + m + 1)
            if c_lo >= c_hi:
                break
            rr, cc = np.nonzero(mask[r_lo:r_hi, c_lo:c_hi])
            if rr.size >= cfg.min_window_pixels:
                rows_acc.append(rr + r_lo)
                cols_acc.append(cc + c_lo)
                misses = 0
            else:
                misses += 1
            if rows_acc:
                # predict the next window from everything seen so far: handles curves and dash gaps
                rows_all = np.concatenate(rows_acc).astype(float)
                cols_all = np.concatenate(cols_acc).astype(float)
                row_span = rows_all.max() - rows_all.min()
                next_row = r_lo - win_h / 2.0
                if row_span >= 3 * win_h:
                    cur = float(np.polyval(np.polyfit(rows_all, cols_all, 2), next_row))
                elif row_span >= 6:
                    cur = float(np.polyval(np.polyfit(rows_all, cols_all, 1), next_row))
                else:
                    cur = float(cols_all.mean())
            if not (0 <= cur < w):
                break

        if not rows_acc:
            return None
        rows = np.concatenate(rows_acc)
        cols = np.concatenate(cols_acc)
        if rows.size < cfg.min_line_pixels:
            return None
        x = spec.row_to_x(rows)
        y = spec.col_to_y(cols)
        span = float(x.max() - x.min())
        if span < 2.0:
            return None
        if span >= cfg.min_span_m:
            c2, c1, c0 = np.polyfit(x, y, 2)
        else:
            c1, c0 = np.polyfit(x, y, 1)
            c2 = 0.0
        return LaneLine((float(c0), float(c1), float(c2)), int(rows.size), span)

    def _combine(self, left: LaneLine | None, right: LaneLine | None) -> LaneEstimate:
        cfg = self.cfg
        half = self._width / 2.0
        if left and right:
            width = left.coeffs[0] - right.coeffs[0]
            lo, hi = cfg.width_bounds
            if not (lo <= width <= hi):
                # One "line" is probably a neighbouring lane's marking: keep the plausible one.
                if abs(left.coeffs[0] - half) <= abs(right.coeffs[0] + half):
                    right = None
                else:
                    left = None

        def quality(line: LaneLine) -> float:
            return min(1.0, line.x_span / 25.0) * min(1.0, line.n_points / 120.0)

        if left and right:
            width = left.coeffs[0] - right.coeffs[0]
            self._width = 0.9 * self._width + 0.1 * width
            center = tuple((a + b) / 2.0 for a, b in zip(left.coeffs, right.coeffs))
            confidence = (quality(left) + quality(right)) / 2.0
        elif left:
            width = self._width
            center = (left.coeffs[0] - half, left.coeffs[1], left.coeffs[2])
            confidence = 0.6 * quality(left)
        elif right:
            width = self._width
            center = (right.coeffs[0] + half, right.coeffs[1], right.coeffs[2])
            confidence = 0.6 * quality(right)
        else:
            return INVALID_LANE

        return LaneEstimate(
            valid=confidence >= cfg.min_confidence,
            left=left,
            right=right,
            center=(float(center[0]), float(center[1]), float(center[2])),
            lane_width=float(width),
            confidence=float(confidence),
        )

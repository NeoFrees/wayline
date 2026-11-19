import numpy as np
import pytest

from wayline.perception.camera import CameraLanePipeline, PinholeCamera
from wayline.perception.lanes import BevSpec, LaneDetector
from wayline.sim.render import CameraRenderer, LaneScene, render_bev

CASES = [
    (0.0, 0.0, 0.0),
    (0.5, 0.02, 0.002),
    (-0.8, -0.03, -0.004),
    (1.2, 0.05, 0.003),
    (-1.3, 0.0, 0.0),
    (0.3, -0.06, 0.005),   # tight bend + yaw: the left line leaves the raster
]


@pytest.mark.parametrize("offset,heading,curv", CASES)
@pytest.mark.parametrize("dash_phase", [0.0, 5.0, 8.5])
def test_bev_detection_recovers_geometry(offset, heading, curv, dash_phase):
    scene = LaneScene(offset=offset, heading=heading, curvature=curv, s=dash_phase)
    est = LaneDetector().detect(render_bev(scene, rng=np.random.default_rng(3)))
    assert est.valid
    assert est.lateral_offset == pytest.approx(offset, abs=0.06)
    assert est.heading_error == pytest.approx(heading, abs=0.006)
    assert est.curvature == pytest.approx(curv, abs=0.0004)
    assert est.lane_width == pytest.approx(3.7, abs=0.15)


@pytest.mark.parametrize("offset,heading,curv", CASES[:4])
def test_camera_pipeline_inverse_perspective(offset, heading, curv):
    cam = PinholeCamera()
    frame = CameraRenderer(cam).render(LaneScene(offset, heading, curv, s=2.0), rng=np.random.default_rng(1))
    est = CameraLanePipeline(cam).process(frame)
    assert est.valid
    assert est.lateral_offset == pytest.approx(offset, abs=0.1)
    assert est.heading_error == pytest.approx(heading, abs=0.01)


def test_camera_projection_round_trip():
    cam = PinholeCamera()
    x = np.array([5.0, 12.0, 30.0])
    y = np.array([-1.5, 0.0, 2.2])
    u, v, ok = cam.ground_to_pixel(x, y)
    assert ok.all()
    gx, gy, hit = cam.pixel_to_ground(u, v)
    assert hit.all()
    np.testing.assert_allclose(gx, x, atol=1e-6)
    np.testing.assert_allclose(gy, y, atol=1e-6)


def test_single_visible_line_still_gives_lane():
    scene = LaneScene(0.4, 0.0, 0.0, hide_right=True)
    est = LaneDetector().detect(render_bev(scene))
    assert est.valid and est.right is None and est.left is not None
    assert est.lateral_offset == pytest.approx(0.4, abs=0.1)
    assert est.confidence < 0.8   # single-line estimates are trusted less


def test_no_markings_is_invalid():
    spec = BevSpec()
    est = LaneDetector(spec).detect(np.full((spec.height, spec.width), 0.15, dtype=np.float32))
    assert not est.valid


def test_wrong_shape_rejected():
    with pytest.raises(ValueError):
        LaneDetector().detect(np.zeros((10, 10)))

import pytest

from wayline.control.lateral import LateralController
from wayline.control.longitudinal import LeadInfo, LongitudinalController
from wayline.control.safety import SafetyGate, SafetyLimits
from wayline.perception.lanes import INVALID_LANE, LaneEstimate

DT = 0.05


def gate(**kw):
    return SafetyGate(DT, SafetyLimits(**kw))


def apply(g, torque, accel=0.0, engaged=True, driver_torque=0.0, brake=False, gas=False):
    return g.apply(engaged=engaged, torque=torque, accel=accel, driver_torque=driver_torque,
                   brake_pressed=brake, gas_pressed=gas)


def test_gate_blocks_everything_when_disengaged():
    r = apply(gate(), 0.8, accel=1.0, engaged=False)
    assert r.torque == 0.0 and r.accel == 0.0
    assert r.violations


def test_gate_rate_limits_torque_up_and_releases_faster():
    g = gate(max_rate_up=1.0, max_rate_down=2.0)
    assert apply(g, 1.0).torque == pytest.approx(0.05)      # 1.0/s * 50 ms
    for _ in range(30):
        apply(g, 1.0)
    assert apply(g, 1.0).torque == pytest.approx(1.0)
    assert apply(g, 0.0).torque == pytest.approx(0.9)      # 2.0/s * 50 ms


def test_gate_clamps_magnitude():
    g = gate(max_torque=0.5, max_rate_up=100.0)
    r = apply(g, 3.0)
    assert r.torque == pytest.approx(0.5)
    assert "torque above limit" in r.violations


def test_driver_steering_overrides_lateral():
    g = gate(max_rate_up=100.0, max_rate_down=100.0)
    apply(g, 0.6)
    r = apply(g, 0.6, driver_torque=0.5)
    assert r.lateral_override and r.torque == 0.0


def test_brake_and_gas_override_longitudinal():
    g = gate()
    assert apply(g, 0.0, accel=-2.0, brake=True).accel == 0.0
    assert apply(g, 0.0, accel=-2.0, gas=True).accel == 0.0
    assert apply(g, 0.0, accel=1.0, gas=True).accel == 1.0
    assert apply(g, 0.0, accel=-9.0).accel == -3.5


def test_lateral_steers_back_toward_centre_and_feeds_forward_curvature():
    ctl = LateralController()
    left_of_centre = LaneEstimate(True, center=(-0.5, 0.0, 0.0), lane_width=3.7, confidence=1.0)
    assert ctl.update(left_of_centre, 25.0).torque < 0      # steer right
    bend_left = LaneEstimate(True, center=(0.0, 0.0, 0.0015), lane_width=3.7, confidence=1.0)
    out = ctl.update(bend_left, 25.0)
    assert out.desired_curvature == pytest.approx(0.003, rel=0.05)
    assert ctl.update(INVALID_LANE, 25.0).torque == 0.0


def test_acc_holds_speed_and_follows_lead():
    lon = LongitudinalController()
    assert lon.update(20.0, 25.0) > 0
    assert lon.update(25.0, 25.0) == pytest.approx(0.0)
    close = LeadInfo(distance=15.0, v_lead=15.0)
    assert lon.update(25.0, 25.0, close) == pytest.approx(lon.tuning.min_accel)
    assert lon.emergency_stop(20.0) < 0 and lon.emergency_stop(0.0) < 0

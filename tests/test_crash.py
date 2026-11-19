import math

import pytest

from wayline.guardian.crash import G, CrashDetector, ImuSample
from wayline.guardian.types import Severity

RATE = 100


def pulse(t, t0, dur, peak_g):
    return peak_g * G * math.sin(math.pi * (t - t0) / dur) if t0 <= t < t0 + dur else 0.0


def drive(detector, seconds, speed_fn, ax_fn=lambda t: 0.0, ay_fn=lambda t: 0.0, az_fn=lambda t: G,
          airbag_at=None, dt=0.05):
    """Feed the detector 20 Hz ticks of 100 Hz IMU data; return the events it reports."""
    events, t, k = [], 0.0, 0
    per_tick = int(RATE * dt)
    while t < seconds:
        samples = [ImuSample(ts, ax_fn(ts), ay_fn(ts), az_fn(ts))
                   for ts in (t + i / RATE for i in range(per_tick))]
        t += dt
        ev = detector.update(t, samples, speed_fn(t), airbag_deployed=airbag_at is not None and t >= airbag_at)
        if ev:
            events.append(ev)
        k += 1
    return events


def test_frontal_crash_detected_with_delta_v_and_wheel_speed_corroboration():
    v0 = 12.5
    ax = lambda t: pulse(t, 2.0, 0.105, 16.0)
    speed = lambda t: v0 if t < 2.0 else max(0.0, v0 - 10.5)
    events = drive(CrashDetector(), 5.0, speed, ax_fn=lambda t: -ax(t))
    assert len(events) == 1
    e = events[0]
    assert e.direction == "frontal"
    assert e.delta_v_kph == pytest.approx(37.8, abs=2.0)
    assert e.severity == Severity.MODERATE
    assert e.speed_before_kph == pytest.approx(45.0, abs=1.0)


def test_side_impact_with_airbag_is_one_severe_event_with_full_data():
    ay = lambda t: pulse(t, 2.0, 0.12, 20.0)
    events = drive(CrashDetector(), 4.0, lambda t: 15.0, ay_fn=ay, airbag_at=2.03)
    assert len(events) == 1
    e = events[0]
    assert e.airbag and e.direction == "right" and e.severity == Severity.SEVERE
    assert e.delta_v_kph > 40


def test_airbag_without_imu_pulse_still_reports():
    events = drive(CrashDetector(), 3.0, lambda t: 10.0, airbag_at=1.0)
    assert len(events) == 1 and events[0].airbag and events[0].severity == Severity.SEVERE


@pytest.mark.parametrize("name,kw", [
    ("pothole", {"az_fn": lambda t: G + pulse(t, 1.0, 0.025, 4.0), "ax_fn": lambda t: -pulse(t, 1.0, 0.025, 0.8)}),
    ("speed bump", {"az_fn": lambda t: G + pulse(t, 1.0, 0.08, 2.5)}),
    ("hard braking", {"ax_fn": lambda t: -0.95 * G if 1.0 <= t < 3.5 else 0.0}),
    ("device knock", {"ax_fn": lambda t: pulse(t, 1.0, 0.015, 3.5)}),
])
def test_non_crash_jolts_are_ignored(name, kw):
    assert drive(CrashDetector(), 4.0, lambda t: 13.0, **kw) == []


def test_imu_only_spike_without_speed_drop_is_rejected():
    # a big forward pulse but the wheels say the car never slowed: the device was knocked
    ax = lambda t: -pulse(t, 1.0, 0.1, 9.0)
    assert drive(CrashDetector(), 4.0, lambda t: 20.0, ax_fn=ax) == []


def test_rollover_from_gravity_vector():
    # car rolls onto its side: gravity moves from z to y
    ay = lambda t: G if t >= 1.0 else 0.0
    az = lambda t: 0.0 if t >= 1.0 else G
    events = drive(CrashDetector(), 4.0, lambda t: 0.0, ay_fn=ay, az_fn=az)
    assert any(e.rollover and e.severity == Severity.SEVERE for e in events)

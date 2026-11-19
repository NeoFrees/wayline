"""Closed-loop, end-to-end: every scenario in the simulator ends the way it should."""
import pytest

from wayline.controls import Mode
from wayline.guardian import IncidentKind, Phase
from wayline.sim.runner import main, run
from wayline.sim.scenarios import SCENARIOS


@pytest.fixture(scope="module")
def results():
    return {}


def get(results, name, **kw):
    key = (name, tuple(sorted(kw.items())))
    if key not in results:
        results[key] = run(SCENARIOS[name], **kw)
    return results[key]


def test_highway_lane_centering_and_acc(results):
    r = get(results, "highway")
    assert r.final_mode == Mode.ENGAGED
    assert r.max_offset_engaged < 0.15
    assert r.min_lead_gap is not None and r.min_lead_gap > 20.0
    assert r.final_speed == pytest.approx(27.0 - 1.2 * 6.0, abs=0.7)   # matched the slower lead car
    assert r.incident is None


def test_camera_perception_closes_the_loop(results):
    r = get(results, "highway", camera=True)
    assert r.final_mode == Mode.ENGAGED and r.max_offset_engaged < 0.25


def test_lane_departure_warns_before_the_line(results):
    r = get(results, "lane_departure")
    ldw = r.events.first("alerts", "ldw_right")
    assert ldw is not None and r.line_crossed_at is not None
    assert r.line_crossed_at - ldw.t >= 0.5
    assert len([e for e in r.events.of("alerts") if e.kind.startswith("ldw_")]) == 1


def test_drowsy_driver_gets_stopped_and_help_called(results):
    r = get(results, "drowsy")
    inc = r.incident
    assert inc.kind == IncidentKind.UNRESPONSIVE_DRIVER and inc.phase == Phase.ESCALATED
    assert r.final_mode == Mode.EMERGENCY_STOP and r.final_speed < 0.1
    esa = r.events.first("controls", "emergency_stop")
    assert esa is not None and 20.0 < esa.t < 26.0
    assert r.max_offset_engaged < 0.15          # stayed centred all the way to a stop
    assert len(r.response_center.cases) == 1
    assert any("complete stop" in body for _, _, body in r.notifier.outbox)


def test_microsleep_recovery_does_not_stop_the_car(results):
    r = get(results, "drowsy_wakes")
    assert r.incident is None and r.final_mode == Mode.ENGAGED
    assert r.events.first("alerts", "dm_critical") is not None


def test_crash_without_answer(results):
    r = get(results, "crash")
    inc = r.incident
    assert inc.kind == IncidentKind.CRASH and inc.phase == Phase.ESCALATED
    assert inc.escalated_at - inc.started_at == pytest.approx(10.0, abs=0.06)
    assert inc.crash.direction == "frontal" and 30 < inc.crash.delta_v_kph < 45
    assert r.final_mode == Mode.DISENGAGED


def test_crash_okay_cancels(results):
    r = get(results, "crash_okay")
    assert r.incident.phase == Phase.CANCELLED and r.notifier.outbox == []


def test_crash_injury_escalates_immediately_and_relays(results):
    r = get(results, "crash_injury")
    inc = r.incident
    assert inc.crash.airbag and inc.crash.direction == "right"
    assert inc.escalated_at == pytest.approx(10.5, abs=0.06)
    assert inc.escalation_reason == "occupant reported an injury"
    assert any("Please hurry" in body for _, _, body in r.notifier.outbox)


def test_voice_sos(results):
    r = get(results, "sos")
    inc = r.incident
    assert inc.kind == IncidentKind.MANUAL_SOS and inc.phase == Phase.ESCALATED
    assert inc.escalated_at == pytest.approx(9.0, abs=0.06)


def test_potholes_are_not_crashes(results):
    assert get(results, "pothole").incident is None


def test_cli_lists_and_runs(capsys):
    assert main(["--list"]) == 0
    assert "crash_injury" in capsys.readouterr().out
    assert main(["crash_okay", "--quiet"]) == 0
    assert "CANCELLED" in capsys.readouterr().out

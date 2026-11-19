import pytest

from conftest import FIX
from wayline.guardian import (EmergencyContact, EmergencyNumberBlocked, GpsFix, GuardianConfig, IncidentKind,
                              KeywordInterpreter, Phase, Severity, is_emergency_number, is_help_request)
from wayline.guardian.ai import Intent
from wayline.guardian.dispatch import DryRunNotifier


def tick(g, t0, t1, dt=0.05, fix=FIX):
    for i in range(int(round((t1 - t0) / dt)) + 1):
        g.update(t0 + i * dt, fix)


def test_no_answer_escalates_after_countdown(rig):
    r = rig()
    inc = r.guardian.trigger(1.0, IncidentKind.CRASH, Severity.MODERATE)
    tick(r.guardian, 1.0, 10.9)
    assert inc.phase == Phase.CHECK_IN
    tick(r.guardian, 11.0, 11.1)
    assert inc.phase == Phase.ESCALATED and inc.escalation_reason == "no response to the check-in"
    sent = [(kind, to) for kind, to, _ in r.notifier.outbox]
    assert ("sms", "+1 555-0100") in sent and ("sms", "+1 555-0142") in sent
    assert len(r.center.cases) == 1
    sms = r.notifier.outbox[0][2]
    assert FIX.maps_url in sms and "{" not in sms
    assert "Calling for help in 5 seconds." in r.guardian.voice.lines


def test_severe_crash_uses_short_countdown(rig):
    r = rig()
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    tick(r.guardian, 0.0, 5.0)
    assert inc.phase == Phase.ESCALATED


@pytest.mark.parametrize("said", ["I'm okay", "we're fine, false alarm", "yes", "no need to call, all good",
                                  "Cancel"])
def test_okay_cancels(rig, said):
    r = rig()
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.MINOR)
    r.guardian.hear(2.0, said)
    tick(r.guardian, 2.0, 20.0)
    assert inc.phase == Phase.CANCELLED
    assert r.notifier.outbox == [] and r.center.cases == {}


@pytest.mark.parametrize("said,reason", [
    ("I'm not okay", "occupant asked for help"),
    ("no", "occupant asked for help"),
    ("I'm fine but my wife is bleeding", "occupant reported an injury"),
    ("don't call... actually yes call for help", "occupant asked for help"),
    ("my chest hurts", "occupant reported an injury"),
])
def test_help_or_injury_escalates_immediately(rig, said, reason):
    r = rig()
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.MINOR)
    r.guardian.hear(1.0, said)
    assert inc.phase == Phase.ESCALATED and inc.escalation_reason == reason
    assert inc.escalated_at == 1.0


def test_unclear_reply_keeps_counting_down(rig):
    r = rig()
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.MINOR)
    r.guardian.hear(2.0, "uhh what")
    assert inc.phase == Phase.CHECK_IN and inc.deadline == 10.0
    tick(r.guardian, 2.0, 10.0)
    assert inc.phase == Phase.ESCALATED


def test_updates_after_escalation_go_to_everyone_reached(rig):
    r = rig()
    r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    tick(r.guardian, 0.0, 5.0)
    before = len(r.notifier.outbox)
    r.guardian.hear(8.0, "please hurry")
    texts = [b for _, _, b in r.notifier.outbox[before:]]
    assert len(texts) == 2 and all("please hurry" in t for t in texts)
    case = next(iter(r.center.cases.values()))
    assert any("please hurry" in u for u in case["updates"])


def test_core_plan_never_contacts_response_center(rig):
    r = rig(plan="core")
    r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    tick(r.guardian, 0.0, 6.0)
    assert r.center.cases == {}
    assert "call them or emergency services" in r.notifier.outbox[0][2]


def test_failed_delivery_does_not_block_others_and_retries(rig):
    r = rig(fail_numbers=("+1 555-0100",), center_up=False)
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.MODERATE)
    tick(r.guardian, 0.0, 10.0)
    oks = [d for d in inc.deliveries if d.ok]
    assert [d.recipient for d in oks] == ["Alex Rivera (+1 555-0142)"]
    assert any(not d.ok for d in inc.deliveries)


def test_retry_when_nobody_reachable(rig):
    r = rig(contacts=[EmergencyContact("Sam", "+1 555-0100")], fail_numbers=("+1 555-0100",), center_up=False)
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    tick(r.guardian, 0.0, 5.0)
    assert inc.retry_at == pytest.approx(5.0 + 30.0, abs=0.1)
    r.notifier.fail_numbers.clear()
    tick(r.guardian, 5.0, 36.0)
    assert inc.retry_at is None and any(d.ok for d in inc.deliveries)


def test_driver_taking_control_cancels_unresponsive_check_in(rig):
    r = rig()
    inc = r.guardian.trigger(0.0, IncidentKind.UNRESPONSIVE_DRIVER, Severity.MODERATE)
    r.guardian.driver_took_control(3.0, "brake")
    assert inc.phase == Phase.CANCELLED


def test_retrigger_upgrades_but_never_restarts_clock(rig):
    r = rig()
    inc = r.guardian.trigger(0.0, IncidentKind.UNRESPONSIVE_DRIVER, Severity.MODERATE)
    same = r.guardian.trigger(4.0, IncidentKind.CRASH, Severity.SEVERE)
    assert same is inc and inc.severity == Severity.SEVERE
    assert inc.deadline == pytest.approx(min(10.0, 4.0 + 5.0))


def test_voice_sos_detection_and_grace_period(rig):
    r = rig()
    r.guardian.hear(1.0, "Hey Wayline, call for help, I'm having chest pains")
    inc = r.guardian.incident
    assert inc.kind == IncidentKind.MANUAL_SOS and inc.severity == Severity.SEVERE
    tick(r.guardian, 1.0, 4.0)
    assert inc.phase == Phase.ESCALATED and inc.escalation_reason == "SOS was not cancelled"


def test_sos_can_be_cancelled(rig):
    r = rig()
    r.guardian.hear(1.0, "emergency")
    r.guardian.hear(2.0, "cancel, sorry")
    assert r.guardian.incident.phase == Phase.CANCELLED


@pytest.mark.parametrize("text,expected", [
    ("call for help", True), ("I need help", True), ("call 911", True),
    ("don't call for help", False), ("what's the weather", False), ("help me find a coffee shop", True),
])
def test_is_help_request(text, expected):
    assert is_help_request(text) is expected


def test_location_updates_while_escalated(rig):
    r = rig()
    r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    tick(r.guardian, 0.0, 5.0)
    moved = GpsFix(FIX.lat + 0.001, FIX.lon)
    before = len(r.notifier.outbox)
    tick(r.guardian, 5.0, 66.0, fix=moved)
    assert any(moved.maps_url in body for _, _, body in r.notifier.outbox[before:])


def test_broken_speaker_does_not_stop_escalation(rig):
    class Broken:
        def say(self, text):
            raise OSError("audio device gone")
    r = rig(voice=Broken())
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    tick(r.guardian, 0.0, 5.0)
    assert inc.phase == Phase.ESCALATED and r.notifier.outbox


def test_emergency_numbers_are_never_auto_dialled():
    for n in ["911", "+1 911", "112", "999", "000"]:
        assert is_emergency_number(n)
    assert not is_emergency_number("+1 555-0100")
    with pytest.raises(EmergencyNumberBlocked):
        DryRunNotifier().place_call("911", "test")


def test_keyword_interpreter_negation_and_short_answers():
    k = KeywordInterpreter()
    assert k.interpret("not okay").intent == Intent.HELP
    assert k.interpret("nobody's hurt, we're fine").intent == Intent.OKAY
    assert k.interpret("yes", asked_if_okay=False).intent == Intent.UNCLEAR
    assert k.interpret("").intent == Intent.UNCLEAR

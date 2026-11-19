"""Claude integration, tested against a fake client: request shape, validation and every fallback."""
import pytest

from conftest import FIX, FakeClaude, reply
from wayline.guardian import (ClaudeComposer, ClaudeInterpreter, ClaudeJSON, GuardianConfig, IncidentKind,
                              Phase, Severity)
from wayline.guardian.ai import Intent, TemplateComposer, validate_ai_brief
from wayline.guardian.report import IncidentReport

GOOD_BRIEF = {
    "dispatcher_script": "Automated alert: a moderate frontal collision at {location}. Silver RAV4. "
                         "The driver, Jordan Lee, did not answer voice prompts.",
    "contact_message": "Wayline: Jordan may have been in a crash at {time} and didn't answer. "
                       "Help has been requested. {maps_url}",
}


def report(**kw):
    base = dict(incident_id="INC-1", kind=IncidentKind.CRASH, severity=Severity.MODERATE,
                time_utc="2026-11-19T21:30:05Z", location=FIX, driver_name="Jordan Lee",
                vehicle="silver RAV4", statements=[], injuries=[])
    base.update(kw)
    return IncidentReport(**base)


def test_request_shape_and_privacy():
    client = FakeClaude(lambda kw: reply(GOOD_BRIEF))
    brief = ClaudeComposer(ClaudeJSON(client)).compose(report())
    assert brief.source == "ai"
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "low"
    assert "thinking" not in call and "temperature" not in call
    # the model never sees coordinates or the timestamp
    sent = call["messages"][0]["content"]
    assert "34.05" not in sent and "118.24" not in sent and "21:30" not in sent


def test_placeholders_are_filled_with_latest_facts():
    brief = ClaudeComposer(ClaudeJSON(FakeClaude(lambda kw: reply(GOOD_BRIEF)))).compose(report())
    final = brief.finalize(report())
    assert FIX.spoken in final.dispatcher_script
    assert final.contact_message.endswith(FIX.maps_url)
    assert "21:30 UTC" in final.contact_message


@pytest.mark.parametrize("bad", [
    {"dispatcher_script": "Crash at 34.05220, -118.24370.", "contact_message": "Help {maps_url}"},
    {"dispatcher_script": "Crash at {location}.", "contact_message": "Help needed, no link"},
    {"dispatcher_script": "Crash at {location} near {landmark}.", "contact_message": "Help {maps_url}"},
    {"dispatcher_script": "Crash at {location}.", "contact_message": "x" * 300 + "{maps_url}"},
])
def test_invalid_ai_wording_falls_back_to_template(bad):
    composer = ClaudeComposer(ClaudeJSON(FakeClaude(lambda kw: reply(bad))))
    brief = composer.compose(report())
    assert brief.source == "template" and composer.last_error


@pytest.mark.parametrize("response", [
    TimeoutError("slow network"),
    reply("not json"),
    reply(GOOD_BRIEF, stop_reason="refusal"),
    reply(GOOD_BRIEF, stop_reason="max_tokens"),
    reply({"unexpected": "shape"}),
])
def test_model_failures_fall_back_to_template(response):
    brief = ClaudeComposer(ClaudeJSON(FakeClaude(lambda kw: response))).compose(report())
    assert brief.source == "template"
    assert validate_ai_brief(brief.dispatcher_script, brief.contact_message.replace("Location: ", "")) is None


def test_template_is_always_valid():
    for kind in IncidentKind:
        b = TemplateComposer().compose(report(kind=kind, statements=["help"], injuries=["leg hurts"]))
        assert validate_ai_brief(b.dispatcher_script, b.contact_message) is None


def test_interpreter_never_waits_for_the_model_to_escalate():
    client = FakeClaude(lambda kw: reply({"intent": "okay", "injuries": [], "summary": ""}))
    interp = ClaudeInterpreter(ClaudeJSON(client))
    assert interp.interpret("I'm bleeding").intent == Intent.INJURY
    assert client.calls == []


def test_model_understands_nuance_keywords_miss():
    client = FakeClaude(lambda kw: reply({"intent": "injury", "injuries": ["can't feel my legs"],
                                          "summary": "Driver reports numb legs"}))
    out = ClaudeInterpreter(ClaudeJSON(client)).interpret("I'm okay I think, but I can't feel my legs")
    # keywords alone would catch "can't feel"; make the phrase subtler to exercise the model path:
    out2 = ClaudeInterpreter(ClaudeJSON(client)).interpret("everything's kind of spinning")
    assert out.intent == Intent.INJURY
    assert out2.intent == Intent.INJURY and out2.source == "ai"


def test_model_okay_can_cancel_but_model_unclear_blocks_keyword_cancel():
    ok = ClaudeInterpreter(ClaudeJSON(FakeClaude(lambda kw: reply({"intent": "okay", "injuries": [], "summary": ""}))))
    assert ok.interpret("yeah everything's fine here, just a fender bender").intent == Intent.OKAY
    unsure = ClaudeInterpreter(ClaudeJSON(FakeClaude(lambda kw: reply({"intent": "unclear", "injuries": [], "summary": ""}))))
    assert unsure.interpret("I'm okay").intent == Intent.UNCLEAR


def test_interpreter_falls_back_to_keywords_when_model_down():
    down = ClaudeInterpreter(ClaudeJSON(FakeClaude(lambda kw: ConnectionError("offline"))))
    assert down.interpret("I'm okay").intent == Intent.OKAY
    assert down.last_error


def test_guardian_uses_ai_draft_when_ready_and_template_when_not(rig):
    client = FakeClaude(lambda kw: reply(GOOD_BRIEF))
    r = rig(composer=ClaudeComposer(ClaudeJSON(client)), config=GuardianConfig(ai_wait_s=5.0))
    inc = r.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    for i in range(0, 101):
        r.guardian.update(i * 0.05, FIX)
    assert inc.phase == Phase.ESCALATED and inc.brief.source == "ai"
    assert FIX.maps_url in r.notifier.outbox[0][2]
    r.guardian.close()

    slow = FakeClaude(lambda kw: TimeoutError("model unreachable"))
    r2 = rig(composer=ClaudeComposer(ClaudeJSON(slow)))  # production default: never wait
    inc2 = r2.guardian.trigger(0.0, IncidentKind.CRASH, Severity.SEVERE)
    for i in range(0, 101):
        r2.guardian.update(i * 0.05, FIX)
    assert inc2.phase == Phase.ESCALATED and inc2.brief.source == "template"
    assert r2.notifier.outbox
    r2.guardian.close()

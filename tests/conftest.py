import json
from types import SimpleNamespace

import pytest

from wayline.events import EventLog
from wayline.guardian import (Dispatcher, DriverProfile, DryRunNotifier, EmergencyContact, GpsFix,
                              Guardian, GuardianConfig, SimulatedResponseCenter)

FIX = GpsFix(34.05220, -118.24370)


def make_profile(plan="plus", contacts=None):
    return DriverProfile(
        name="Jordan Lee",
        vehicle="silver 2023 Toyota RAV4 Hybrid, plate 8WAY123",
        contacts=contacts if contacts is not None else [
            EmergencyContact("Sam Lee", "+1 555-0100"), EmergencyContact("Alex Rivera", "+1 555-0142")],
        plan=plan,
        medical_notes="Type 1 diabetic", share_medical_notes=True,
    )


class Rig(SimpleNamespace):
    """A Guardian wired to dry-run delivery, with handy accessors."""

    def kinds(self, source="guardian"):
        return [e.kind for e in self.events.of(source)]


@pytest.fixture
def rig():
    def build(plan="plus", contacts=None, fail_numbers=(), center_up=True, config=None, **guardian_kw):
        events = EventLog()
        notifier = DryRunNotifier(fail_numbers=fail_numbers)
        center = SimulatedResponseCenter(available=center_up)
        guardian = Guardian(make_profile(plan, contacts), Dispatcher(notifier, center, events),
                            events=events, config=config or GuardianConfig(), **guardian_kw)
        guardian.update(0.0, FIX)
        return Rig(guardian=guardian, notifier=notifier, center=center, events=events)
    return build


# ---- a stand-in for anthropic.Anthropic() ---------------------------------------------

class FakeMessages:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.responder(kwargs)
        if isinstance(result, BaseException):
            raise result
        return result


class FakeClaude:
    def __init__(self, responder):
        self.beta = SimpleNamespace(messages=FakeMessages(responder))

    @property
    def calls(self):
        return self.beta.messages.calls


def reply(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])

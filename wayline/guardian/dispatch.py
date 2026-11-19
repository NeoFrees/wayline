"""Getting the message out: emergency contacts and the response center.

Delivery rules:
* Dispatch never raises. Each recipient is attempted independently and every
  attempt is recorded as a Delivery, so one failure can't block the others.
* Automated calls/texts to emergency short codes (911, 112, 999, ...) are refused.
  Many jurisdictions prohibit automated or pre-recorded calls to emergency lines;
  emergency services are reached through a certified response-center partner
  (the ``ResponseCenter`` interface) or by the occupant via their phone.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from xml.sax.saxutils import escape

from .types import DriverProfile, IncidentKind, Severity

if TYPE_CHECKING:
    from ..events import EventLog
    from .ai import IncidentBrief
    from .report import IncidentReport

EMERGENCY_SHORT_CODES = frozenset({
    "911", "112", "999", "000", "110", "119", "100", "101", "102", "108", "15", "17", "18",
    "113", "118", "190", "192", "193", "199", "911911",
})


class EmergencyNumberBlocked(ValueError):
    pass


def is_emergency_number(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone or "")
    return digits in EMERGENCY_SHORT_CODES or (len(digits) <= 4 and digits.endswith("911"))


def _guard(phone: str) -> None:
    if is_emergency_number(phone):
        raise EmergencyNumberBlocked(
            f"refusing automated contact with emergency number {phone!r}; "
            "route emergency services through a certified ResponseCenter instead")


def _speakable(sms: str) -> str:
    """SMS text -> something sensible to read aloud (no URLs, no sender prefix)."""
    s = re.sub(r"https?://\S+", "", sms)
    s = re.sub(r"\bLocation:\s*$", "", s.strip())
    s = s.replace("Wayline Guardian:", "").strip()
    return re.sub(r"\s+", " ", s)


@dataclass(frozen=True)
class Delivery:
    channel: str     # "sms" | "call" | "response_center" | "update"
    recipient: str
    ok: bool
    detail: str = ""   # provider reference / case id, or the error
    address: str = ""  # phone number or case id used for follow-ups


class Notifier(Protocol):
    def send_sms(self, to: str, body: str) -> str: ...
    def place_call(self, to: str, script: str) -> str: ...


class ResponseCenter(Protocol):
    name: str

    def open_case(self, report: "IncidentReport", brief: "IncidentBrief") -> str: ...
    def update_case(self, case_id: str, message: str) -> None: ...


class DryRunNotifier:
    """Records what would be sent. Used by the simulator, tests and demos."""

    def __init__(self, fail_numbers: tuple[str, ...] = ()):
        self.outbox: list[tuple[str, str, str]] = []
        self.fail_numbers = set(fail_numbers)

    def _send(self, kind: str, to: str, body: str) -> str:
        _guard(to)
        if to in self.fail_numbers:
            raise ConnectionError(f"simulated delivery failure to {to}")
        self.outbox.append((kind, to, body))
        return f"dry-run-{len(self.outbox)}"

    def send_sms(self, to: str, body: str) -> str:
        return self._send("sms", to, body)

    def place_call(self, to: str, script: str) -> str:
        return self._send("call", to, script)


class TwilioNotifier:
    """SMS + text-to-speech calls through Twilio's REST API (stdlib only, no SDK needed).

    Configure with WAYLINE_TWILIO_SID, WAYLINE_TWILIO_TOKEN and WAYLINE_TWILIO_FROM.
    """

    API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/{resource}.json"

    def __init__(self, account_sid: str, auth_token: str, from_number: str, timeout_s: float = 10.0):
        self.sid, self.token, self.from_number, self.timeout_s = account_sid, auth_token, from_number, timeout_s

    @classmethod
    def from_env(cls) -> "TwilioNotifier":
        try:
            return cls(os.environ["WAYLINE_TWILIO_SID"], os.environ["WAYLINE_TWILIO_TOKEN"],
                       os.environ["WAYLINE_TWILIO_FROM"])
        except KeyError as exc:
            raise RuntimeError(f"missing environment variable {exc.args[0]}") from exc

    def send_sms(self, to: str, body: str) -> str:
        _guard(to)
        return self._post("Messages", {"To": to, "From": self.from_number, "Body": body})["sid"]

    def place_call(self, to: str, script: str) -> str:
        _guard(to)
        said = escape(script)
        twiml = f"<Response><Say>{said}</Say><Pause length=\"1\"/><Say>{said}</Say></Response>"
        return self._post("Calls", {"To": to, "From": self.from_number, "Twiml": twiml})["sid"]

    def _post(self, resource: str, fields: dict[str, str]) -> dict:
        url = self.API.format(sid=urllib.parse.quote(self.sid), resource=resource)
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                     headers={"Authorization": f"Basic {auth}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise ConnectionError(f"Twilio {resource} failed: HTTP {exc.code}") from exc


class SimulatedResponseCenter:
    """Stand-in for a 24/7 human response center partner (Plus plan)."""

    name = "Wayline Response Center"

    def __init__(self, available: bool = True):
        self.available = available
        self.cases: dict[str, dict] = {}

    def open_case(self, report: "IncidentReport", brief: "IncidentBrief") -> str:
        if not self.available:
            raise ConnectionError("response center unreachable")
        case_id = f"RC-{len(self.cases) + 1:05d}"
        self.cases[case_id] = {"report": report, "brief": brief, "updates": []}
        return case_id

    def update_case(self, case_id: str, message: str) -> None:
        self.cases[case_id]["updates"].append(message)


class Dispatcher:
    def __init__(self, notifier: Notifier, response_center: ResponseCenter | None = None,
                 events: "EventLog | None" = None):
        self.notifier = notifier
        self.response_center = response_center
        self.events = events

    def _log(self, t: float, d: Delivery, preview: str = "") -> None:
        if self.events is None:
            return
        status = "delivered" if d.ok else f"FAILED ({d.detail})"
        msg = f"{d.channel} → {d.recipient}: {status}"
        self.events.emit(t, "dispatch", d.channel, msg, ok=d.ok, recipient=d.recipient,
                         detail=d.detail, preview=preview)

    def dispatch(self, t: float, profile: DriverProfile, report: "IncidentReport",
                 brief: "IncidentBrief") -> list[Delivery]:
        out: list[Delivery] = []
        if profile.plan == "plus" and self.response_center is not None:
            try:
                case_id = self.response_center.open_case(report, brief)
                d = Delivery("response_center", self.response_center.name, True, case_id, case_id)
            except Exception as exc:  # noqa: BLE001 - every failure is recorded, never raised
                d = Delivery("response_center", self.response_center.name, False, str(exc))
            out.append(d)
            self._log(t, d, brief.dispatcher_script)

        call_too = report.severity >= Severity.SEVERE or report.kind == IncidentKind.UNRESPONSIVE_DRIVER
        call_script = (f"This is an automated call from Wayline Guardian about {profile.first_name}. "
                       + _speakable(brief.contact_message)
                       + " A text message with the exact location has been sent to this number.")
        for contact in profile.contacts:
            label = f"{contact.name} ({contact.phone})"
            try:
                ref = self.notifier.send_sms(contact.phone, brief.contact_message)
                d = Delivery("sms", label, True, ref, contact.phone)
            except Exception as exc:  # noqa: BLE001
                d = Delivery("sms", label, False, str(exc), contact.phone)
            out.append(d)
            self._log(t, d, brief.contact_message)
            if call_too:
                try:
                    ref = self.notifier.place_call(contact.phone, call_script)
                    d = Delivery("call", label, True, ref, contact.phone)
                except Exception as exc:  # noqa: BLE001
                    d = Delivery("call", label, False, str(exc), contact.phone)
                out.append(d)
                self._log(t, d, call_script)
        return out

    def send_update(self, t: float, profile: DriverProfile, deliveries: list[Delivery], message: str) -> list[Delivery]:
        """Follow-up to everyone who was successfully reached for this incident."""
        out: list[Delivery] = []
        reached = {d.recipient: d for d in deliveries
                   if d.ok and d.channel in ("sms", "response_center")}
        for d in reached.values():
            try:
                if d.channel == "response_center":
                    if self.response_center is None:
                        continue
                    self.response_center.update_case(d.address, message)
                else:
                    self.notifier.send_sms(d.address, message)
                u = Delivery("update", d.recipient, True, address=d.address)
            except Exception as exc:  # noqa: BLE001
                u = Delivery("update", d.recipient, False, str(exc), d.address)
            out.append(u)
            self._log(t, u, message)
        return out

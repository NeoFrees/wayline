"""Guardian: the incident state machine that decides when to call for help.

    trigger ──► CHECK_IN ──(no answer / "help" / injury)──► ESCALATED ──► RESOLVED
                   │
                   └──("I'm okay" / driver takes control)──► CANCELLED

Everything that decides *whether and when* help is called is here, in plain
deterministic code with fixed countdowns. The language model (ai.py) only helps
interpret replies and word the alert. AI wording is drafted in the background
during the countdown and used only if it is ready and still matches the facts;
escalation never waits on it.

On the device this runs in its own process, powered by the Guardian Reserve
backup cell, so it keeps working if the main computer or the car's power fails.
"""
from __future__ import annotations

import math
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Protocol

from ..events import EventLog
from .ai import (BriefComposer, IncidentBrief, Intent, Interpretation, KeywordInterpreter,
                 ResponseInterpreter, TemplateComposer, is_help_request, severity_for_sos)
from .crash import CrashEvent
from .dispatch import Delivery, Dispatcher
from .report import IncidentReport
from .types import DriverProfile, GpsFix, IncidentKind, Severity


class Phase(str, Enum):
    CHECK_IN = "check_in"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class GuardianConfig:
    check_in_s: float = 10.0          # crash / unresponsive driver
    severe_check_in_s: float = 5.0    # airbag, rollover, very high delta-V
    sos_grace_s: float = 3.0          # manual SOS: time to cancel an accidental press
    reminder_at_s: float = 5.0        # spoken reminder when this many seconds remain
    retry_s: float = 30.0             # retry if nobody could be reached
    location_update_s: float = 60.0
    location_update_min_m: float = 25.0
    ai_wait_s: float = 0.0            # wall-clock wait for an AI draft at escalation (0 = never wait)


class Voice(Protocol):
    def say(self, text: str) -> None: ...


class RecordingVoice:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str) -> None:
        self.lines.append(text)


@dataclass
class Incident:
    id: str
    kind: IncidentKind
    severity: Severity
    started_at: float
    deadline: float
    crash: CrashEvent | None = None
    phase: Phase = Phase.CHECK_IN
    statements: list[str] = field(default_factory=list)
    injuries: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    escalated_at: float | None = None
    escalation_reason: str = ""
    ended_at: float | None = None
    end_reason: str = ""
    report: IncidentReport | None = None
    brief: IncidentBrief | None = None
    deliveries: list[Delivery] = field(default_factory=list)
    reminded: bool = False
    retry_at: float | None = None
    control_update_sent: bool = False
    draft: tuple[tuple, Future] | None = None


def _distance_m(a: GpsFix, b: GpsFix) -> float:
    dlat = (a.lat - b.lat) * 111_320.0
    dlon = (a.lon - b.lon) * 111_320.0 * math.cos(math.radians(a.lat))
    return math.hypot(dlat, dlon)


class Guardian:
    def __init__(self, profile: DriverProfile, dispatcher: Dispatcher, *,
                 interpreter: ResponseInterpreter | None = None,
                 composer: BriefComposer | None = None,
                 voice: Voice | None = None,
                 config: GuardianConfig | None = None,
                 events: EventLog | None = None,
                 utc_now: Callable[[float], datetime] | None = None):
        self.profile = profile
        self.dispatcher = dispatcher
        self.interpreter = interpreter or KeywordInterpreter()
        self.composer = composer or TemplateComposer()
        self.template = TemplateComposer()
        self.voice = voice or RecordingVoice()
        self.config = config or GuardianConfig()
        self.events = events or EventLog()
        self.utc_now = utc_now or (lambda _t: datetime.now(timezone.utc))
        self.incident: Incident | None = None
        self.history: list[Incident] = []
        self._fix: GpsFix | None = None
        self._last_push: tuple[float, GpsFix | None] | None = None
        self._pool: ThreadPoolExecutor | None = None

    # -- public API -------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.incident is not None and self.incident.phase in (Phase.CHECK_IN, Phase.ESCALATED)

    def trigger(self, t: float, kind: IncidentKind, severity: Severity, *,
                crash: CrashEvent | None = None, actions: tuple[str, ...] = (),
                statement: str | None = None) -> Incident:
        if self.active:
            return self._merge(t, kind, severity, crash, actions)
        countdown = self._countdown(kind, severity)
        inc = Incident(id=f"INC-{len(self.history) + 1:04d}", kind=kind, severity=severity,
                       started_at=t, deadline=t + countdown, crash=crash, actions=list(actions))
        if statement:
            inc.statements.append(statement)
        self.incident = inc
        self.history.append(inc)
        what = f"crash — {crash.describe()}" if crash else kind.value.replace("_", " ")
        self._log(t, "incident", f"Incident {inc.id}: {what} · severity {severity.label} · "
                                 f"check-in {countdown:.0f}s", incident=inc.id)
        self._say(t, self._prompt(inc, countdown))
        self._refresh_draft(inc, t)
        if countdown <= 0:
            self._escalate(t, "immediate")
        return inc

    def hear(self, t: float, text: str) -> None:
        """Occupant speech (already transcribed on-device)."""
        text = text.strip()
        if not text:
            return
        if not self.active:
            # Idle: only on-device keyword spotting runs; nothing leaves the car.
            if is_help_request(text):
                interp = KeywordInterpreter().interpret(text, asked_if_okay=False)
                inc = self.trigger(t, IncidentKind.MANUAL_SOS, severity_for_sos(interp), statement=text)
                inc.injuries.extend(interp.injuries)
            return

        inc = self.incident
        inc.statements.append(text)
        self._log(t, "heard", f'Occupant: "{text}"')
        interp = self._interpret(text, inc)
        for injury in interp.injuries:
            if injury not in inc.injuries:
                inc.injuries.append(injury)
        self._log(t, "understood", f"{interp.intent.value} (via {interp.source})"
                  + (f" — {interp.summary}" if interp.summary else ""))

        if inc.phase == Phase.CHECK_IN:
            if interp.intent == Intent.INJURY:
                self._escalate(t, "occupant reported an injury")
            elif interp.intent == Intent.HELP:
                self._escalate(t, "occupant asked for help")
            elif interp.intent == Intent.OKAY:
                self._cancel(t, "occupant said they are okay")
            else:
                remaining = max(1, round(inc.deadline - t))
                self._say(t, f"Sorry, I didn't catch that. I'll call for help in {remaining} seconds "
                             "unless you say \"I'm okay\".")
                self._refresh_draft(inc, t)
        else:  # escalated: relay what they said
            self._send_update(t, inc, f'Wayline Guardian update for {self.profile.first_name}\'s incident: '
                                      f'occupant says "{text}".')
            if interp.intent == Intent.OKAY:
                self._say(t, "Thanks — I've let them know you said you're okay. Help has already been "
                             "requested, so please stay where you are if it's safe.")
            else:
                self._say(t, "I've passed that on.")

    def driver_took_control(self, t: float, how: str = "steering or pedal input") -> None:
        if not self.active:
            return
        inc = self.incident
        if inc.kind != IncidentKind.UNRESPONSIVE_DRIVER:
            return
        if inc.phase == Phase.CHECK_IN:
            self._cancel(t, f"driver responded ({how})")
        elif not inc.control_update_sent:
            inc.control_update_sent = True
            self._send_update(t, inc, f"Wayline Guardian update: {self.profile.first_name} is responsive "
                                      "again and has taken control of the car.")

    def note(self, t: float, action: str) -> None:
        """Record something Wayline did (e.g. 'the car has stopped'); relayed if help was already called."""
        if not self.active:
            return
        inc = self.incident
        if action not in inc.actions:
            inc.actions.append(action)
            self._log(t, "note", action)
            if inc.phase == Phase.ESCALATED:
                self._send_update(t, inc, f"Wayline Guardian update: {action}.")

    def update(self, t: float, fix: GpsFix | None = None) -> None:
        if fix is not None:
            self._fix = fix
        if not self.active:
            return
        inc = self.incident
        cfg = self.config
        if inc.phase == Phase.CHECK_IN:
            remaining = inc.deadline - t
            if (not inc.reminded and inc.deadline - inc.started_at >= 2 * cfg.reminder_at_s
                    and remaining <= cfg.reminder_at_s and remaining > 0):
                inc.reminded = True
                self._say(t, f"Calling for help in {max(1, round(remaining))} seconds.")
            if t >= inc.deadline:
                self._escalate(t, "SOS was not cancelled" if inc.kind == IncidentKind.MANUAL_SOS
                               else "no response to the check-in")
            return
        # ESCALATED
        if inc.retry_at is not None and t >= inc.retry_at:
            self._log(t, "retry", "Retrying notifications")
            self._dispatch(t, inc)
        if (self._fix is not None and self._last_push is not None
                and t - self._last_push[0] >= cfg.location_update_s
                and (self._last_push[1] is None
                     or _distance_m(self._fix, self._last_push[1]) >= cfg.location_update_min_m)):
            self._send_update(t, inc, f"Wayline Guardian location update: {self._fix.maps_url}")
            self._last_push = (t, self._fix)

    def resolve(self, t: float, reason: str = "closed by responders") -> None:
        if self.active:
            self._end(t, Phase.RESOLVED, reason)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)

    # -- internals --------------------------------------------------------------

    def _merge(self, t: float, kind: IncidentKind, severity: Severity,
               crash: CrashEvent | None, actions: tuple[str, ...]) -> Incident:
        """A new trigger during an active incident upgrades it; it never restarts the clock."""
        inc = self.incident
        for a in actions:
            if a not in inc.actions:
                inc.actions.append(a)
        if crash is not None and (inc.crash is None or crash.severity >= inc.crash.severity):
            inc.crash = crash
            if inc.kind != IncidentKind.CRASH:
                self._log(t, "upgrade", f"Crash detected during {inc.kind.value}: {crash.describe()}")
        if severity > inc.severity:
            inc.severity = severity
            self._log(t, "upgrade", f"Severity raised to {severity.label}")
            if inc.phase == Phase.CHECK_IN:
                inc.deadline = min(inc.deadline, t + self._countdown(inc.kind, severity))
        if inc.phase == Phase.ESCALATED and crash is not None:
            self._send_update(t, inc, f"Wayline Guardian update: {crash.describe()} detected.")
        return inc

    def _countdown(self, kind: IncidentKind, severity: Severity) -> float:
        c = self.config
        if kind == IncidentKind.MANUAL_SOS:
            return c.sos_grace_s
        if severity >= Severity.SEVERE:
            return c.severe_check_in_s
        return c.check_in_s

    @staticmethod
    def _prompt(inc: Incident, countdown: float) -> str:
        n = int(round(countdown))
        if inc.kind == IncidentKind.CRASH:
            return (f"This is Wayline Guardian. I detected a crash. Are you okay? "
                    f"I'll call for help in {n} seconds. Say \"I'm okay\" to cancel.")
        if inc.kind == IncidentKind.UNRESPONSIVE_DRIVER:
            return (f"This is Wayline Guardian. You're not responding, so I'm bringing the car to a stop. "
                    f"Are you okay? I'll call for help in {n} seconds unless you answer.")
        return f"Calling for help in {n} seconds. Say \"cancel\" to stop."

    def _interpret(self, text: str, inc: Incident) -> Interpretation:
        asked_if_okay = inc.kind != IncidentKind.MANUAL_SOS
        try:
            return self.interpreter.interpret(text, asked_if_okay=asked_if_okay)
        except Exception:  # noqa: BLE001 - interpretation must never break the flow
            return KeywordInterpreter().interpret(text, asked_if_okay=asked_if_okay)

    def _build_report(self, inc: Incident, t: float) -> IncidentReport:
        p = self.profile
        actions = list(inc.actions)
        if p.plan == "plus":
            actions.append("Wayline response center notified")
        if p.contacts:
            actions.append("Emergency contacts notified: " + ", ".join(c.name for c in p.contacts))
        return IncidentReport(
            incident_id=inc.id, kind=inc.kind, severity=inc.severity,
            time_utc=self.utc_now(t).strftime("%Y-%m-%dT%H:%M:%SZ"), location=self._fix,
            driver_name=p.name, vehicle=p.vehicle, statements=list(inc.statements),
            injuries=list(inc.injuries), crash=inc.crash,
            medical_notes=p.medical_notes if p.share_medical_notes else None,
            actions_taken=actions, plan=p.plan)

    def _refresh_draft(self, inc: Incident, t: float) -> None:
        if getattr(self.composer, "remote", False):
            self._submit_draft(inc, self._build_report(inc, t))

    def _submit_draft(self, inc: Incident, report: IncidentReport) -> None:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="guardian-ai")
        inc.draft = (report.fingerprint(), self._pool.submit(self.composer.compose, report))

    def _final_brief(self, inc: Incident, report: IncidentReport) -> IncidentBrief:
        brief: IncidentBrief | None = None
        if not getattr(self.composer, "remote", False):
            try:
                brief = self.composer.compose(report)
            except Exception:  # noqa: BLE001
                brief = None
        else:
            fp = report.fingerprint()
            stale = inc.draft is None or inc.draft[0] != fp
            if stale and self.config.ai_wait_s > 0:
                self._submit_draft(inc, report)  # only when explicitly allowed to wait (simulator)
            if inc.draft is not None and inc.draft[0] == fp:
                fut = inc.draft[1]
                try:
                    if self.config.ai_wait_s > 0:
                        brief = fut.result(timeout=self.config.ai_wait_s)
                    elif fut.done():
                        brief = fut.result()
                except Exception:  # noqa: BLE001 - timeout or failure: use the template
                    brief = None
        return (brief or self.template.compose(report)).finalize(report)

    def _escalate(self, t: float, reason: str) -> None:
        inc = self.incident
        inc.phase = Phase.ESCALATED
        inc.escalated_at = t
        inc.escalation_reason = reason
        self._log(t, "escalate", f"Calling for help — {reason}")
        inc.report = self._build_report(inc, t)
        inc.brief = self._final_brief(inc, inc.report)
        self._log(t, "brief", f"Alert written ({inc.brief.source})",
                  dispatcher_script=inc.brief.dispatcher_script, contact_message=inc.brief.contact_message)
        self._dispatch(t, inc)

    def _dispatch(self, t: float, inc: Incident) -> None:
        deliveries = self.dispatcher.dispatch(t, self.profile, inc.report, inc.brief)
        inc.deliveries.extend(deliveries)
        ok = [d for d in deliveries if d.ok]
        if ok:
            inc.retry_at = None
            self._last_push = (t, self._fix)
            self._say(t, self._confirmation(ok))
        else:
            inc.retry_at = t + self.config.retry_s
            self._say(t, "I couldn't reach anyone yet, and I'll keep trying. "
                         "If you can, call emergency services from your phone.")

    @staticmethod
    def _confirmation(ok: list[Delivery]) -> str:
        who: list[str] = []
        center = any(d.channel == "response_center" for d in ok)
        if center:
            who.append("the Wayline response center")
        for d in ok:
            if d.channel == "sms":
                name = d.recipient.split(" (")[0]
                if name not in who:
                    who.append(name)
        listed = who[0] if len(who) == 1 else ", ".join(who[:-1]) + " and " + who[-1]
        text = f"I've shared your location and what happened with {listed}."
        if center:
            text += " The response center can send emergency services."
        return (text + " I'm still here — tell me if anything changes. If you see smoke or smell "
                "fuel, get out and away from traffic if you can.")

    def _send_update(self, t: float, inc: Incident, message: str) -> None:
        self.dispatcher.send_update(t, self.profile, inc.deliveries, message)

    def _cancel(self, t: float, reason: str) -> None:
        self._end(t, Phase.CANCELLED, reason)
        self._say(t, "Okay — I won't call anyone. If you need help later, just say \"call for help\".")

    def _end(self, t: float, phase: Phase, reason: str) -> None:
        inc = self.incident
        inc.phase = phase
        inc.ended_at = t
        inc.end_reason = reason
        if inc.draft is not None:
            inc.draft[1].cancel()
        self._log(t, phase.value, f"Incident {phase.value} — {reason}")

    def _say(self, t: float, text: str) -> None:
        self.events.emit(t, "voice", "say", text)
        try:
            self.voice.say(text)
        except Exception as exc:  # noqa: BLE001 - a broken speaker must not stop the call for help
            self.events.emit(t, "voice", "error", f"voice output failed: {exc}")

    def _log(self, t: float, kind: str, message: str, **data) -> None:
        self.events.emit(t, "guardian", kind, message, **data)

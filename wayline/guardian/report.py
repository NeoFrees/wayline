"""The incident report: the facts Guardian shares with contacts and responders."""
from __future__ import annotations

from dataclasses import dataclass, field

from .crash import CrashEvent
from .types import GpsFix, IncidentKind, Severity

KIND_SUMMARY = {
    IncidentKind.CRASH: "a crash",
    IncidentKind.UNRESPONSIVE_DRIVER: "an unresponsive driver",
    IncidentKind.MANUAL_SOS: "an emergency help request from an occupant",
}


@dataclass
class IncidentReport:
    incident_id: str
    kind: IncidentKind
    severity: Severity
    time_utc: str
    location: GpsFix | None
    driver_name: str
    vehicle: str
    statements: list[str] = field(default_factory=list)
    injuries: list[str] = field(default_factory=list)
    crash: CrashEvent | None = None
    medical_notes: str | None = None
    actions_taken: list[str] = field(default_factory=list)
    plan: str = "core"

    @property
    def what(self) -> str:
        """Short description of what happened, e.g. 'a moderate frontal collision'."""
        c = self.crash
        if self.kind == IncidentKind.CRASH and c is not None:
            if c.rollover:
                return "a rollover crash"
            if c.direction == "unknown":
                return "a crash with airbag deployment" if c.airbag else "a crash"
            side = {"frontal": "frontal", "rear": "rear-end", "left": "left-side", "right": "right-side"}
            return f"a {self.severity.label} {side.get(c.direction, '')} collision".replace("  ", " ")
        return KIND_SUMMARY[self.kind]

    @property
    def location_spoken(self) -> str:
        return self.location.spoken if self.location else "an unknown location (no GPS fix)"

    @property
    def maps_url(self) -> str:
        return self.location.maps_url if self.location else "(location unavailable)"

    def fingerprint(self) -> tuple:
        """Everything the wording depends on, except time and location (filled in at send time)."""
        return (self.kind, self.severity, tuple(self.statements), tuple(self.injuries),
                self.crash, self.medical_notes, tuple(self.actions_taken), self.plan)

    def facts_for_ai(self) -> dict:
        """Facts given to the language model. Deliberately excludes coordinates and time:
        the model writes {location}/{maps_url}/{time} placeholders that code fills in, so
        the location sent to responders is always the latest fix and is never paraphrased."""
        crash = None
        if self.crash is not None:
            crash = {
                "direction": self.crash.direction,
                "delta_v_kph": round(self.crash.delta_v_kph, 1),
                "peak_g": round(self.crash.peak_g, 1),
                "airbag_deployed": self.crash.airbag,
                "rollover": self.crash.rollover,
                "speed_before_kph": round(self.crash.speed_before_kph),
            }
        return {
            "incident": self.what,
            "kind": self.kind.value,
            "severity": self.severity.label,
            "driver_name": self.driver_name,
            "vehicle": self.vehicle,
            "occupant_statements": self.statements,
            "injuries_reported": self.injuries,
            "crash_data": crash,
            "medical_notes_shared_by_driver": self.medical_notes,
            "actions_taken": self.actions_taken,
        }

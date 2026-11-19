"""Shared Guardian data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class Severity(IntEnum):
    MINOR = 1
    MODERATE = 2
    SEVERE = 3

    @property
    def label(self) -> str:
        return self.name.lower()


class IncidentKind(str, Enum):
    CRASH = "crash"
    UNRESPONSIVE_DRIVER = "unresponsive_driver"
    MANUAL_SOS = "manual_sos"


@dataclass(frozen=True)
class GpsFix:
    lat: float
    lon: float
    accuracy_m: float = 5.0
    speed_mps: float = 0.0
    heading_deg: float = 0.0

    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.lat:.5f},{self.lon:.5f}"

    @property
    def spoken(self) -> str:
        ns = "north" if self.lat >= 0 else "south"
        ew = "east" if self.lon >= 0 else "west"
        return f"latitude {abs(self.lat):.5f} {ns}, longitude {abs(self.lon):.5f} {ew}"


@dataclass(frozen=True)
class EmergencyContact:
    name: str
    phone: str
    relation: str = ""


@dataclass
class DriverProfile:
    name: str
    vehicle: str                       # e.g. "white 2024 Hyundai Ioniq 5, plate 8ABC123"
    contacts: list[EmergencyContact] = field(default_factory=list)
    plan: str = "core"                 # "core" (free) or "plus" (24/7 response center)
    medical_notes: str | None = None   # shared with responders only if the user opted in
    share_medical_notes: bool = False

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name else "The driver"

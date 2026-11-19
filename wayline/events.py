"""Timeline of everything the copilot did — the basis for logs, the simulator output and tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    t: float
    source: str    # controls | lanes | driver | guardian | voice | dispatch
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"t": round(self.t, 3), "source": self.source, "kind": self.kind,
                "message": self.message, "data": self.data}


class EventLog:
    def __init__(self, sink: Callable[[Event], None] | None = None):
        self.events: list[Event] = []
        self.sink = sink

    def emit(self, t: float, source: str, kind: str, message: str, **data: Any) -> Event:
        ev = Event(t, source, kind, message, data)
        self.events.append(ev)
        if self.sink is not None:
            self.sink(ev)
        return ev

    def of(self, source: str | None = None, kind: str | None = None) -> list[Event]:
        return [e for e in self.events
                if (source is None or e.source == source) and (kind is None or e.kind == kind)]

    def first(self, source: str | None = None, kind: str | None = None) -> Event | None:
        found = self.of(source, kind)
        return found[0] if found else None

"""Scripted drives that exercise lane assist, driver monitoring and Guardian end to end."""
from __future__ import annotations

from dataclasses import dataclass

from .world import Bump, Impact


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    summary: str
    duration: float
    segments: tuple[tuple[float, float], ...]   # (length m, curvature 1/m)
    v0: float                                   # m/s
    engage_at: float | None = 1.0               # press "set" at this time (None = manual driving)
    eyes_closed: tuple[float, float] | None = None   # driver's eyes closed from..until (s)
    distracted: tuple[float, float] | None = None    # manual driver looks away from..until (s)
    takeover_at: float | None = None            # driver grabs the wheel
    speech: tuple[tuple[float, str], ...] = ()
    impacts: tuple[Impact, ...] = ()
    bumps: tuple[Bump, ...] = ()
    sos_at: float | None = None
    lead: tuple[float, float, tuple[tuple[float, float], ...]] | None = None  # gap, speed, (t, accel)...
    plan: str = "plus"


CURVY_HIGHWAY = ((250.0, 0.0), (450.0, 0.0025), (250.0, 0.0), (450.0, -0.003), (300.0, 0.0),
                 (400.0, 0.002), (2000.0, 0.0))
GENTLE_HIGHWAY = ((300.0, 0.0), (600.0, 0.0015), (300.0, 0.0), (600.0, -0.0015), (2000.0, 0.0))
CITY_STREET = ((1000.0, 0.0),)

SCENARIOS: dict[str, Scenario] = {s.name: s for s in [
    Scenario(
        "highway", "Lane centering + adaptive cruise on a curvy highway",
        "Engages at 97 km/h, follows S-bends, and slows smoothly when the car ahead brakes.",
        duration=60.0, segments=CURVY_HIGHWAY, v0=27.0,
        lead=(55.0, 27.0, ((24.0, -1.2), (30.0, 0.0))),
    ),
    Scenario(
        "lane_departure", "Lane departure warning while driving manually",
        "The driver looks at their phone on a bend; Wayline warns before the car leaves its lane.",
        duration=22.0, segments=((150.0, 0.0), (2000.0, 0.003)), v0=27.0, engage_at=None,
        distracted=(9.0, 11.5),
    ),
    Scenario(
        "drowsy", "Driver falls asleep → Emergency Stop Assist → Guardian calls for help",
        "Eyes close at 8 s. Alerts escalate; with no response Wayline keeps the lane, slows to a stop "
        "with hazards on, and Guardian alerts contacts and the response center.",
        duration=52.0, segments=GENTLE_HIGHWAY, v0=29.0, eyes_closed=(8.0, 1e9),
    ),
    Scenario(
        "drowsy_wakes", "Microsleep, driver recovers",
        "Eyes close at 8 s; the escalating alerts wake the driver at 19 s. No emergency stop.",
        duration=30.0, segments=GENTLE_HIGHWAY, v0=29.0, eyes_closed=(8.0, 19.0),
    ),
    Scenario(
        "crash", "Frontal crash, driver doesn't answer",
        "A 45 km/h frontal collision. Guardian asks if everyone is okay, hears nothing, and "
        "calls for help after 10 seconds.",
        duration=26.0, segments=CITY_STREET, v0=12.5,
        impacts=(Impact(8.0, peak_g=16.0, duration=0.105),),
    ),
    Scenario(
        "crash_okay", "Minor bump, driver says they're fine",
        "A low-speed bump. The driver answers \"I'm okay\" and Guardian stands down.",
        duration=20.0, segments=CITY_STREET, v0=8.3,
        impacts=(Impact(8.0, peak_g=8.0, duration=0.1),),
        speech=((11.0, "I'm okay, it was just a little bump."),),
    ),
    Scenario(
        "crash_injury", "Side impact with airbags, injury reported",
        "Struck from the right with airbag deployment (5 s check-in). The driver reports an injury, "
        "so Guardian escalates immediately and relays later updates.",
        duration=25.0, segments=CITY_STREET, v0=15.0,
        impacts=(Impact(8.0, peak_g=20.0, duration=0.12, direction="right", airbag=True),),
        speech=((10.5, "My passenger is bleeding and I can't open my door."), (16.0, "Please hurry.")),
    ),
    Scenario(
        "sos", "Voice SOS: \"call for help\"",
        "The driver says they have chest pain. Guardian gives 3 seconds to cancel, then calls for help.",
        duration=15.0, segments=GENTLE_HIGHWAY, v0=27.0,
        speech=((6.0, "Wayline, call for help. I'm having chest pains."),),
    ),
    Scenario(
        "pothole", "Potholes, a speed bump and a knock — no false alarm",
        "Hard jolts that are not crashes. Guardian stays quiet.",
        duration=16.0, segments=CITY_STREET, v0=13.0, engage_at=None,
        bumps=(Bump(5.0, vertical_g=4.0, horizontal_g=0.8, duration=0.025),
               Bump(9.0, vertical_g=2.5, duration=0.08),
               Bump(12.0, horizontal_g=3.5, duration=0.015)),
    ),
]}

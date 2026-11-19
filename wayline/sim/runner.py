"""Run simulator scenarios from the command line.

    python -m wayline.sim --list
    python -m wayline.sim crash
    python -m wayline.sim drowsy --camera        # lane perception from rendered camera frames
    python -m wayline.sim all --quiet
    python -m wayline.sim crash_injury --ai      # Claude writes the alert (needs `pip install -e .[ai]`)
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

from ..controls import CarState, Copilot, Mode, SensorFrame
from ..events import Event, EventLog
from ..guardian.ai import ClaudeComposer, ClaudeInterpreter, ClaudeJSON
from ..guardian.dispatch import Dispatcher, DryRunNotifier, SimulatedResponseCenter
from ..guardian.incident import Guardian, GuardianConfig
from ..guardian.types import DriverProfile, EmergencyContact
from ..control.longitudinal import LeadInfo
from ..monitoring.driver import DriverObservation
from ..perception.camera import CameraLanePipeline
from .render import CameraRenderer, render_bev
from .scenarios import SCENARIOS, Scenario
from .world import HumanDriver, ImuSim, LeadCar, Road, Vehicle

DT = 0.05
SIM_EPOCH = datetime(2026, 11, 19, 21, 30, 0, tzinfo=timezone.utc)


def demo_profile(plan: str = "plus") -> DriverProfile:
    # 555-01xx numbers are reserved for fiction; nothing is ever sent in the simulator.
    return DriverProfile(
        name="Jordan Lee",
        vehicle="silver 2023 Toyota RAV4 Hybrid, plate 8WAY123",
        contacts=[EmergencyContact("Sam Lee", "+1 555-0100", "partner"),
                  EmergencyContact("Alex Rivera", "+1 555-0142", "friend")],
        plan=plan,
        medical_notes="Type 1 diabetic; allergic to penicillin",
        share_medical_notes=True,
    )


@dataclass
class SimResult:
    scenario: Scenario
    events: EventLog
    guardian: Guardian
    notifier: DryRunNotifier
    response_center: SimulatedResponseCenter
    trace: list[dict] = field(default_factory=list)
    max_offset_engaged: float = 0.0
    mean_offset_engaged: float = 0.0
    min_lead_gap: float | None = None
    line_crossed_at: float | None = None
    final_speed: float = 0.0
    final_mode: Mode = Mode.DISENGAGED
    engaged_seconds: float = 0.0

    @property
    def incident(self):
        return self.guardian.history[-1] if self.guardian.history else None


def build_guardian(profile: DriverProfile, events: EventLog, *, ai: bool = False,
                   notifier: DryRunNotifier | None = None,
                   response_center: SimulatedResponseCenter | None = None) -> Guardian:
    notifier = notifier or DryRunNotifier()
    response_center = response_center or SimulatedResponseCenter()
    dispatcher = Dispatcher(notifier, response_center, events)
    kwargs = {}
    if ai:
        llm = ClaudeJSON()
        kwargs = {"interpreter": ClaudeInterpreter(llm), "composer": ClaudeComposer(llm)}
    return Guardian(profile, dispatcher, events=events,
                    config=GuardianConfig(ai_wait_s=12.0 if ai else 0.0),
                    utc_now=lambda t: SIM_EPOCH + timedelta(seconds=t), **kwargs)


def run(scenario: Scenario, *, ai: bool = False, camera: bool = False, sink=None, seed: int = 0,
        realtime: bool = False) -> SimResult:
    events = EventLog(sink)
    notifier = DryRunNotifier()
    rc = SimulatedResponseCenter()
    guardian = build_guardian(demo_profile(scenario.plan), events, ai=ai, notifier=notifier, response_center=rc)
    copilot = Copilot(guardian, dt=DT, events=events)
    if camera:
        copilot.camera_pipeline = CameraLanePipeline(detector=copilot.detector)
        cam_renderer = CameraRenderer(copilot.camera_pipeline.projector.camera)

    road = Road(scenario.segments)
    car = Vehicle(road, scenario.v0)
    human = HumanDriver()
    imu = ImuSim(seed=seed)
    rng = np.random.default_rng(seed)
    lead = LeadCar(*scenario.lead[:2], scenario.lead[2]) if scenario.lead else None
    result = SimResult(scenario, events, guardian, notifier, rc)

    first_impact = min((i.t for i in scenario.impacts), default=None)
    airbag_t = min((i.t + 0.03 for i in scenario.impacts if i.airbag), default=None)
    offsets: list[float] = []
    engaged_since: float | None = None
    speech = sorted(scenario.speech)
    n_steps = int(round(scenario.duration / DT))
    wall0 = time.perf_counter()

    for k in range(n_steps + 1):
        t = k * DT
        st = car.state
        crashed = first_impact is not None and t >= first_impact

        # --- what the driver is doing -------------------------------------------------
        eyes_closed = scenario.eyes_closed is not None and scenario.eyes_closed[0] <= t < scenario.eyes_closed[1]
        looking_away = scenario.distracted is not None and scenario.distracted[0] <= t < scenario.distracted[1]
        grabbing = scenario.takeover_at is not None and scenario.takeover_at <= t < scenario.takeover_at + 0.5
        obs = DriverObservation(face_detected=True, gaze_on_road=not looking_away,
                                eyes_closed=0.95 if eyes_closed else 0.05, interacted=grabbing)
        engaged = copilot.mode != Mode.DISENGAGED
        if crashed:
            human_torque, human_accel = 0.0, -6.0 if st.v > 0 else 0.0
        elif engaged:
            human_torque, human_accel = (0.6 if grabbing else 0.0), 0.0
        else:
            human_torque = human.steer(car, DT, attentive=not (looking_away or eyes_closed))
            human_accel = human.pedal(st.v, scenario.v0)

        # --- sensors ---------------------------------------------------------------------
        scene = car.scene()
        frame = SensorFrame(
            t=t,
            car=CarState(
                v_ego=st.v, yaw_rate=st.v * st.kappa,
                driver_torque=human_torque if not engaged else (0.6 if grabbing else 0.0),
                set_pressed=scenario.engage_at is not None and abs(t - scenario.engage_at) < DT / 2,
                airbag_deployed=airbag_t is not None and t >= airbag_t),
            driver=obs,
            speech=[text for (ts, text) in speech if t - DT < ts <= t],
            sos_pressed=scenario.sos_at is not None and abs(t - scenario.sos_at) < DT / 2,
        )
        if camera:
            frame.camera = cam_renderer.render(scene, rng=rng)
        else:
            frame.bev = render_bev(scene, rng=rng)
        samples, impulse_dv = imu.sample(t + DT, car, scenario.impacts, scenario.bumps)
        frame.imu = samples
        if k % 20 == 0:
            frame.gps = car.gps()
        if lead is not None:
            frame.lead = LeadInfo(distance=lead.s - st.s - 4.5, v_lead=lead.v)

        # --- copilot ---------------------------------------------------------------------
        out = copilot.step(frame)

        # --- actuate + advance the world --------------------------------------------------
        if crashed:
            torque, accel = 0.0, human_accel
        elif out.mode == Mode.DISENGAGED:
            torque, accel = human_torque, human_accel
        else:
            torque, accel = out.steer_torque + frame.car.driver_torque, out.accel
        car.step(DT, torque, accel, impulse_dv)
        if lead is not None:
            lead.step(t, DT)
            gap = lead.s - car.state.s - 4.5
            result.min_lead_gap = gap if result.min_lead_gap is None else min(result.min_lead_gap, gap)

        if out.mode != Mode.DISENGAGED and not crashed:
            engaged_since = t if engaged_since is None else engaged_since
            if t - engaged_since >= 3.0:
                offsets.append(abs(car.state.d))
        else:
            engaged_since = None
        if result.line_crossed_at is None and abs(car.state.d) + 0.9 > road.lane_width / 2:
            result.line_crossed_at = t
            events.emit(t, "world", "line_crossed", "Vehicle edge crossed a lane line (ground truth)")
        if k % 4 == 0:
            result.trace.append({
                "t": round(t, 2), "s": round(car.state.s, 2), "offset": round(car.state.d, 3),
                "heading": round(car.state.psi, 4), "speed": round(car.state.v, 2),
                "mode": out.mode.value, "torque": round(out.steer_torque, 3), "accel": round(out.accel, 2),
                "lane_valid": out.lane.valid, "offset_est": round(out.lane.lateral_offset, 3),
                "awareness": round(out.driver.awareness, 2), "hazards": out.hazards,
            })
        if realtime:
            time.sleep(max(0.0, (wall0 + t) - time.perf_counter()))

    guardian.close()
    result.max_offset_engaged = max(offsets, default=0.0)
    result.mean_offset_engaged = float(np.mean(offsets)) if offsets else 0.0
    result.engaged_seconds = len(offsets) * DT
    result.final_speed = car.state.v
    result.final_mode = copilot.mode
    return result


# ------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------

def _printer(width: int):
    def sink(ev: Event) -> None:
        if ev.source == "voice":
            line = f'  {ev.t:6.2f}s  voice     "{ev.message}"'
        else:
            line = f"  {ev.t:6.2f}s  {ev.source:<9} {ev.message}"
        print(textwrap.fill(line, width=width, subsequent_indent=" " * 28))
        if ev.source == "guardian" and ev.kind == "brief":
            for label, key in (("operator script", "dispatcher_script"), ("text to contacts", "contact_message")):
                print(textwrap.fill(f"{label}: {ev.data[key]}", width=width,
                                    initial_indent=" " * 28, subsequent_indent=" " * 30))
    return sink


def summarize(r: SimResult) -> str:
    lines = []
    inc = r.incident
    if inc is None:
        lines.append("Guardian: no incident")
    else:
        ok = sum(d.ok for d in inc.deliveries)
        bad = len(inc.deliveries) - ok
        when = inc.escalated_at if inc.escalated_at is not None else inc.ended_at
        why = inc.escalation_reason or inc.end_reason
        lines.append(f"Guardian: {inc.id} {inc.kind.value} -> {inc.phase.value.upper()} at {when:.1f}s ({why})")
        if inc.brief:
            lines.append(f"  alert wording: {inc.brief.source}; deliveries: {ok} ok, {bad} failed")
    if r.engaged_seconds >= 10.0:
        lines.append(f"Lane centering: max |offset| {r.max_offset_engaged:.2f} m, "
                     f"mean {r.mean_offset_engaged:.2f} m while engaged")
    if r.min_lead_gap is not None:
        lines.append(f"Adaptive cruise: closest gap to lead car {r.min_lead_gap:.1f} m")
    ldw = r.events.first("alerts", "ldw_right") or r.events.first("alerts", "ldw_left")
    if ldw:
        crossed = f"{r.line_crossed_at:.2f}s" if r.line_crossed_at is not None else "never"
        lines.append(f"Lane departure warning at {ldw.t:.2f}s; lane line crossed: {crossed}")
    lines.append(f"Final: {r.final_mode.value}, {r.final_speed * 3.6:.0f} km/h")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m wayline.sim", description="Wayline closed-loop simulator")
    ap.add_argument("scenario", nargs="?", default="crash", help="scenario name, or 'all'")
    ap.add_argument("--list", action="store_true", help="list scenarios")
    ap.add_argument("--camera", action="store_true", help="perceive lanes from rendered camera frames")
    ap.add_argument("--ai", action="store_true", help="use Claude for Guardian's language layer")
    ap.add_argument("--quiet", action="store_true", help="only print the summary")
    ap.add_argument("--realtime", action="store_true", help="run at wall-clock speed")
    ap.add_argument("--json", metavar="PATH", help="write events + trace to a JSON file")
    args = ap.parse_args(argv)

    if args.list:
        for s in SCENARIOS.values():
            print(f"  {s.name:<15} {s.title}")
        return 0
    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        ap.error(f"unknown scenario {unknown[0]!r}; try --list")

    dump = {}
    for name in names:
        sc = SCENARIOS[name]
        print(f"\n=== {sc.name}: {sc.title}")
        print(textwrap.fill(sc.summary, width=96, initial_indent="    ", subsequent_indent="    "))
        sink = None if args.quiet else _printer(96)
        r = run(sc, ai=args.ai, camera=args.camera, sink=sink, realtime=args.realtime)
        print(textwrap.indent(summarize(r), "  > "))
        dump[name] = {"events": [e.to_dict() for e in r.events.events], "trace": r.trace}
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(dump, fh, indent=1, default=str)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

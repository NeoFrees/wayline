"""The copilot main loop.

Every tick (20 Hz here, 100 Hz on the device):

    sensors ─► lane perception ─► driver monitoring ─► engagement state machine
            ─► lateral + longitudinal planning ─► safety gate ─► actuators
    and, in parallel, crash detection + voice ─► Guardian

Modes:
    DISENGAGED       the driver drives; Wayline only warns (lane departure) and watches (Guardian)
    ENGAGED          lane centering + adaptive cruise; driver supervises (hands-off, eyes-on)
    EMERGENCY_STOP   driver unresponsive: keep the lane, slow to a stop, hazards on, call for help
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .control.lateral import LateralController
from .control.longitudinal import LeadInfo, LongitudinalController
from .control.safety import GateResult, SafetyGate
from .events import EventLog
from .guardian.crash import CrashDetector, ImuSample
from .guardian.incident import Guardian
from .guardian.types import GpsFix, IncidentKind, Severity
from .monitoring.driver import AlertLevel, DriverMonitor, DriverObservation, DriverState
from .perception.camera import CameraLanePipeline
from .perception.lanes import INVALID_LANE, LaneDetector, LaneEstimate


@dataclass(frozen=True)
class CarState:
    v_ego: float
    yaw_rate: float = 0.0          # rad/s, + = turning left (from the car's stability-control sensor)
    driver_torque: float = 0.0     # normalised, from the steering torque sensor
    brake_pressed: bool = False
    gas_pressed: bool = False
    left_blinker: bool = False
    right_blinker: bool = False
    set_pressed: bool = False      # cruise "set" button: request to engage
    cancel_pressed: bool = False
    airbag_deployed: bool = False


@dataclass
class SensorFrame:
    t: float
    car: CarState
    bev: np.ndarray | None = None      # bird's-eye road raster, or ...
    camera: np.ndarray | None = None   # ... a forward camera frame, or ...
    lane: LaneEstimate | None = None   # ... an already-computed lane estimate
    driver: DriverObservation = field(default_factory=DriverObservation)
    imu: list[ImuSample] = field(default_factory=list)
    gps: GpsFix | None = None
    lead: LeadInfo | None = None
    speech: list[str] = field(default_factory=list)
    sos_pressed: bool = False


class Mode(str, Enum):
    DISENGAGED = "disengaged"
    ENGAGED = "engaged"
    EMERGENCY_STOP = "emergency_stop"


@dataclass(frozen=True)
class Alert:
    code: str
    text: str
    severity: str  # info | warning | critical


@dataclass
class ControlsOutput:
    t: float
    mode: Mode
    steer_torque: float
    accel: float
    hazards: bool
    horn: bool
    alerts: list[Alert]
    lane: LaneEstimate
    driver: DriverState
    gate: GateResult


ESA_ACTION = "Wayline is bringing the car to a controlled stop in its lane with hazard lights on"


class Copilot:
    def __init__(self, guardian: Guardian, *, dt: float = 0.05,
                 detector: LaneDetector | None = None,
                 camera_pipeline: CameraLanePipeline | None = None,
                 lateral: LateralController | None = None,
                 longitudinal: LongitudinalController | None = None,
                 gate: SafetyGate | None = None,
                 monitor: DriverMonitor | None = None,
                 crash_detector: CrashDetector | None = None,
                 events: EventLog | None = None,
                 ldw_min_speed: float = 15.0, ldw_tlc_s: float = 1.0):
        self.guardian = guardian
        self.dt = dt
        self.detector = detector or LaneDetector()
        self.camera_pipeline = camera_pipeline
        self.lateral = lateral or LateralController()
        self.longitudinal = longitudinal or LongitudinalController()
        self.gate = gate or SafetyGate(dt)
        self.monitor = monitor or DriverMonitor()
        self.crash = crash_detector or CrashDetector()
        self.events = events or guardian.events
        self.ldw_min_speed = ldw_min_speed
        self.ldw_tlc_s = ldw_tlc_s
        self.mode = Mode.DISENGAGED
        self.v_set = 0.0
        self._alerts_on: set[str] = set()
        self._hazards_latched = False
        self._esa_stopped = False
        self._ldw_side: str | None = None
        self._ldw_centered_for = 0.0

    # ---------------------------------------------------------------------------

    def step(self, f: SensorFrame) -> ControlsOutput:
        t, car = f.t, f.car
        lane = self._perceive(f)

        crash = self.crash.update(t, f.imu, car.v_ego, car.airbag_deployed)
        if crash is not None:
            if self.mode != Mode.DISENGAGED:
                self._set_mode(t, Mode.DISENGAGED, "crash detected — hands back to the driver, hazards on")
            self._hazards_latched = True
            self.guardian.trigger(t, IncidentKind.CRASH, crash.severity, crash=crash,
                                  actions=("Hazard lights switched on automatically",))
        if f.sos_pressed:
            self.guardian.trigger(t, IncidentKind.MANUAL_SOS, Severity.MODERATE,
                                  statement="(SOS button pressed)")
        for utterance in f.speech:
            self.guardian.hear(t, utterance)

        steering = self.mode in (Mode.ENGAGED, Mode.EMERGENCY_STOP)
        dstate = self.monitor.update(f.driver, self.dt, active=steering)
        override_torque = self.gate.limits.driver_override_torque
        took_control = car.brake_pressed or car.gas_pressed or abs(car.driver_torque) >= override_torque

        if self.mode == Mode.DISENGAGED:
            if car.set_pressed:
                self._try_engage(t, car, lane, dstate)
        elif self.mode == Mode.ENGAGED:
            if car.brake_pressed or car.cancel_pressed:
                self._set_mode(t, Mode.DISENGAGED, "driver braked" if car.brake_pressed else "driver cancelled")
            elif dstate.unresponsive:
                self._start_emergency_stop(t)
        elif self.mode == Mode.EMERGENCY_STOP:
            if took_control:
                how = ("brake" if car.brake_pressed else "accelerator" if car.gas_pressed else "steering")
                self._set_mode(t, Mode.DISENGAGED, f"driver took control ({how}) — emergency stop cancelled")
                self.guardian.driver_took_control(t, how)
            elif car.v_ego < 0.3 and not self._esa_stopped:
                self._esa_stopped = True
                self.events.emit(t, "controls", "stopped", "Car stopped in lane — holding brake, hazards on")
                self.guardian.note(t, "The car has come to a complete stop in its lane, hazard lights on")

        torque_req = accel_req = 0.0
        if self.mode in (Mode.ENGAGED, Mode.EMERGENCY_STOP):
            torque_req = self.lateral.update(lane, car.v_ego).torque
            if self.mode == Mode.ENGAGED:
                accel_req = self.longitudinal.update(car.v_ego, self.v_set, f.lead)
            else:
                accel_req = self.longitudinal.emergency_stop(car.v_ego)
        gate = self.gate.apply(engaged=self.mode != Mode.DISENGAGED, torque=torque_req, accel=accel_req,
                               driver_torque=car.driver_torque, brake_pressed=car.brake_pressed,
                               gas_pressed=car.gas_pressed)

        alerts = self._alerts(t, car, lane, dstate, gate)
        self.guardian.update(t, f.gps)

        esa = self.mode == Mode.EMERGENCY_STOP
        hazards = esa or self._hazards_latched or self.guardian.active
        horn = esa and car.v_ego > 0.3 and (t % 4.0) < 0.4  # short horn pulses to warn traffic and wake the driver
        return ControlsOutput(t, self.mode, gate.torque, gate.accel, hazards, horn, alerts, lane, dstate, gate)

    # ---------------------------------------------------------------------------

    def _perceive(self, f: SensorFrame) -> LaneEstimate:
        if f.lane is not None:
            return f.lane
        if f.camera is not None:
            if self.camera_pipeline is None:
                self.camera_pipeline = CameraLanePipeline(detector=self.detector)
            return self.camera_pipeline.process(f.camera)
        if f.bev is not None:
            return self.detector.detect(f.bev)
        return INVALID_LANE

    def _try_engage(self, t: float, car: CarState, lane: LaneEstimate, d: DriverState) -> None:
        reason = None
        if car.brake_pressed:
            reason = "brake pressed"
        elif not lane.valid:
            reason = "lane lines not visible"
        elif d.level >= AlertLevel.AUDIBLE:
            reason = "driver not paying attention"
        elif self.guardian.active:
            reason = "Guardian incident in progress"
        if reason:
            self.events.emit(t, "controls", "engage_denied", f"Cannot engage: {reason}")
            return
        self.v_set = car.v_ego
        self._set_mode(t, Mode.ENGAGED, f"lane centering + adaptive cruise at {car.v_ego * 3.6:.0f} km/h")

    def _start_emergency_stop(self, t: float) -> None:
        self._set_mode(t, Mode.EMERGENCY_STOP, "driver unresponsive — slowing to a stop in lane")
        self._esa_stopped = False
        self.guardian.trigger(t, IncidentKind.UNRESPONSIVE_DRIVER, Severity.MODERATE, actions=(ESA_ACTION,))

    def _set_mode(self, t: float, mode: Mode, why: str) -> None:
        if mode == self.mode:
            return
        self.events.emit(t, "controls", mode.value, f"{mode.value.replace('_', ' ').upper()}: {why}")
        self.mode = mode

    def _lane_departure(self, car: CarState, lane: LaneEstimate, half_width: float = 0.9) -> str | None:
        """Predict the car's path (from its yaw rate) against the fitted lane lines over the
        next ``ldw_tlc_s`` seconds; warn if a wheel would cross a line without a turn signal."""
        if not lane.valid or car.v_ego < self.ldw_min_speed:
            return None
        kappa_car = car.yaw_rate / car.v_ego
        half_lane = lane.lane_width / 2
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = car.v_ego * self.ldw_tlc_s * frac
            y_car = 0.5 * kappa_car * x * x
            y_left = lane.left.y_at(x) if lane.left else lane.center_y_at(x) + half_lane
            y_right = lane.right.y_at(x) if lane.right else lane.center_y_at(x) - half_lane
            if y_left - (y_car + half_width) < 0 and not car.left_blinker:
                return "left"
            if (y_car - half_width) - y_right < 0 and not car.right_blinker:
                return "right"
        return None

    def _alerts(self, t: float, car: CarState, lane: LaneEstimate, d: DriverState,
                gate: GateResult) -> list[Alert]:
        alerts: list[Alert] = []
        if self.mode == Mode.EMERGENCY_STOP:
            alerts.append(Alert("esa", "Driver unresponsive — Wayline is stopping the car", "critical"))
        elif self.mode == Mode.ENGAGED:
            if d.level == AlertLevel.CRITICAL:
                alerts.append(Alert("dm_critical", "TAKE CONTROL NOW — Wayline will stop the car", "critical"))
            elif d.level == AlertLevel.AUDIBLE:
                alerts.append(Alert("dm_audible", "Pay attention to the road", "warning"))
            elif d.level == AlertLevel.VISUAL:
                alerts.append(Alert("dm_visual", "Keep your eyes on the road", "info"))
            if not lane.valid:
                alerts.append(Alert("lanes_lost", "Lane lines not visible — steer manually", "warning"))
        if self.mode == Mode.DISENGAGED or gate.lateral_override:
            side = self._lane_departure(car, lane)
            if side and self._ldw_side is None:
                # one warning per departure: latch until the car is re-centred for a second
                self._ldw_side, self._ldw_centered_for = side, 0.0
                self.events.emit(t, "alerts", f"ldw_{side}", f"Lane departure — drifting {side}",
                                 severity="warning")
            if self._ldw_side is not None:
                if side:
                    alerts.append(Alert(f"ldw_{self._ldw_side}",
                                        f"Lane departure — drifting {self._ldw_side}", "warning"))
                centered = side is None and lane.valid and abs(lane.lateral_offset) < 0.6
                self._ldw_centered_for = self._ldw_centered_for + self.dt if centered else 0.0
                if self._ldw_centered_for >= 1.0:
                    self._ldw_side = None
        if self.guardian.active:
            phase = self.guardian.incident.phase.value
            text = "Guardian: checking on you" if phase == "check_in" else "Guardian: help requested"
            alerts.append(Alert(f"guardian_{phase}", text, "critical"))

        codes = {a.code for a in alerts}
        for a in alerts:
            if a.code not in self._alerts_on and not a.code.startswith("ldw_"):
                self.events.emit(t, "alerts", a.code, a.text, severity=a.severity)
        self._alerts_on = codes
        return alerts

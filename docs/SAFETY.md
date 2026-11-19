# Safety

## This is a prototype

Wayline is a **concept-stage reference implementation**. Everything in this repository runs
in simulation. It has **not** been validated on a real vehicle, is **not** certified for any
road use, and **must not** be connected to a car on public roads.

Driver-assistance features (SAE Level 2) require an attentive driver who is ready to take over
at all times. Wayline is "hands-off, eyes-on", never "self-driving".

## Design principles

1. **The safety gate is the boss.** Whatever the planner requests, `control/safety.py` enforces
   torque/acceleration limits, ramp rates, and immediate driver override. On hardware the same
   rules run in firmware on a separate microcontroller.
2. **Never hand the car to someone who can't take it.** An unresponsive driver gets a controlled
   stop in lane with hazards on (Emergency Stop Assist), not a disengagement.
3. **AI never decides whether help is called.** Escalation is fixed, deterministic timing.
   The language model only interprets replies and words alerts, behind validators, with offline twins.
4. **Bias toward help.** Mixed or unclear replies keep the countdown running. Any mention of
   injury escalates immediately. Cancelling requires a clear "I'm okay".
5. **Never auto-dial emergency numbers.** Many jurisdictions restrict automated or pre-recorded
   calls to emergency lines. Emergency services are reached through a certified response partner,
   or by the occupant. The dispatch code refuses emergency short codes.
6. **Fail loud, keep going.** A failed SMS, a dead speaker or an unreachable model is logged and
   routed around. It never stops an escalation.
7. **Privacy by default.** Speech is processed on-device; nothing leaves the car outside an active
   incident. The model never receives coordinates. Medical notes are shared only if the driver
   opted in.

## Known limitations

- Perception is a classical lane-line fit validated on synthetic frames. Production needs learned
  models, online camera calibration, and validation on large real-world datasets (night, rain,
  glare, worn paint, construction zones).
- No lead-vehicle perception: the simulator supplies the lead car directly.
- Crash detection thresholds are first-principles values. They must be tuned against real crash
  pulses and false-positive driving data.
- Emergency Stop Assist stops in the current lane. Moving to the shoulder first is on the roadmap.
- Speech-to-text and text-to-speech are interfaces only.

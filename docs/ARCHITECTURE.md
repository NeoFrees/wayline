# Architecture

Wayline is two systems on one device:

1. **The driving stack:** perception → driver monitoring → planning → safety gate → car.
2. **Guardian:** crash and incapacitation detection → check-in → calling for help.

They share sensors but not failure modes. Guardian runs in its own process on
backup power, so it keeps working if the driving stack, the main computer or the car's
12 V supply fails.

```
                 ┌────────────────────────────── Wayline One ──────────────────────────────┐
 road cameras ──►│ perception/   lanes.py: BEV sliding-window lane fit (y = c0 + c1·x + c2·x²) │
                 │               camera.py: pinhole model + inverse perspective mapping      │
 IR camera ─────►│ monitoring/   driver.py: awareness ↓ while distracted → alerts → UNRESPONSIVE│
                 │                                                                           │
                 │ controls.py   mode machine: DISENGAGED ⇄ ENGAGED → EMERGENCY_STOP         │
                 │   control/lateral.py       pure pursuit on the lane centre (+ feed-forward)│
                 │   control/longitudinal.py  ACC: speed hold + time-gap following; ESA decel │
                 │   control/safety.py        hard limits, torque rate limits, driver override│──► CAN: steer / accel
                 │                                                                           │
 high-g IMU ────►│ guardian/crash.py      impact pulse → Δv, wheel-speed corroboration,      │
 car CAN ───────►│                        rollover (gravity vector), airbag                  │
 cabin mics ────►│ guardian/incident.py   CHECK_IN → ESCALATED / CANCELLED (deterministic)    │
 GNSS ──────────►│ guardian/ai.py         Claude: understand replies, word the alert         │
                 │                        + keyword / template twins (always available)      │
                 │ guardian/dispatch.py   contacts (SMS/call) · response center · updates    │──► LTE / phone
                 └───────────────────────── Guardian Reserve backup cell ────────────────────┘
```

## Driving stack

| Module | What it does | Key numbers |
|---|---|---|
| `perception/lanes.py` | Histogram seeds, sliding windows that re-predict their next position from a running polynomial fit (survives dash gaps and tight bends), quadratic fit per line, lane-width tracking for single-line frames | ≤ 6 cm offset error on synthetic frames, ~4 ms/frame in NumPy |
| `perception/camera.py` | Analytic ground-plane projection (no 4-point calibration needed), cached nearest-neighbour IPM lookup, ridge filter that keeps 10–20 cm paint and drops wide bright patches | ~13 ms/frame |
| `control/lateral.py` | Pure pursuit toward the lane centre `v·1 s` ahead. The target lies on the fitted quadratic, so curvature is fed forward and offset dynamics are ≈ critically damped (ζ ≈ 0.71) at every speed | max 4 cm offset on the S-bend highway scenario |
| `control/longitudinal.py` | min(speed-hold, time-gap follow); Emergency Stop Assist profile −1.5 m/s² | 1.6 s time gap, 4 m standstill gap |
| `control/safety.py` | Blocks actuation when disengaged, clamps torque/accel, ramps torque up ≤ 1.0/s and down ≤ 2.0/s, yields to driver steering / brake / gas | On hardware this is duplicated in MCU firmware |
| `monitoring/driver.py` | Awareness drains over 9 s of distraction; microsleep (eyes closed 1.5 s) → immediate audible alert; 6 s at CRITICAL with no reaction → UNRESPONSIVE | Recovery needs 0.5 s attentive or a deliberate input |
| `controls.py` | Engagement rules, lane-departure warning (yaw-rate path prediction against the fitted lines, one warning per departure), alerts, hazards, horn pulses during ESA | 20 Hz in sim, 100 Hz on device |

### Emergency Stop Assist

When the driver monitor declares the driver **UNRESPONSIVE** while Wayline is steering, the
copilot does **not** hand control back. It:

1. keeps lane centering active,
2. decelerates at −1.5 m/s² to a stop in the current lane and holds the brake,
3. turns on hazards and pulses the horn,
4. starts a Guardian incident (voice check-in, then escalation),
5. tells responders when the car has come to a complete stop.

Any deliberate driver input (brake, accelerator, steering torque) cancels the stop and the check-in.

## Guardian

### Detection (`guardian/crash.py`)

| Signal | Rule |
|---|---|
| Impact | Horizontal ≥ 3 g opens a window (≤ 300 ms); integrate to Δv; ≥ 12 km/h is a candidate |
| Corroboration | Frontal/rear candidates must be confirmed by wheel speed dropping ≥ 50% of the longitudinal Δv within 1.5 s. Side impacts, Δv ≥ 40 km/h, and standstill hits skip this |
| Airbag | CAN airbag signal → SEVERE; merged with the impact pulse when one is in progress |
| Rollover | Low-pass gravity vector tilted ≥ 60° for 1 s → SEVERE |
| Rejected | Potholes / speed bumps (vertical), hard braking (never reaches 3 g), knocks (tiny Δv), IMU-only spikes with no speed change |

Severity: MINOR < 20 km/h ≤ MODERATE < 40 km/h ≤ SEVERE (or airbag / rollover).

### Escalation (`guardian/incident.py`)

| Trigger | Check-in window |
|---|---|
| Crash, minor/moderate | 10 s |
| Crash, severe | 5 s |
| Unresponsive driver | 10 s (after ~15 s of escalating alerts) |
| Voice / button SOS | 3 s to cancel an accident |

- "I'm okay" / "cancel" → CANCELLED, nothing sent.
- "Help", "not okay", any injury → ESCALATED immediately.
- Silence or unclear speech → keep counting down (with a spoken reminder at 5 s).
- A second trigger during an incident can raise severity or shorten the clock, never restart it.
- After escalation, occupant speech, location changes (> 25 m, every 60 s) and "car has stopped"
  are relayed to everyone who was reached. If nobody could be reached, it retries every 30 s.

### The AI layer (`guardian/ai.py`)

**Rule: AI helps the call happen faster and clearer. It never decides whether help is called.**

| Job | AI path (Claude) | Deterministic twin | Safety rules |
|---|---|---|---|
| Understand replies | `ClaudeInterpreter`: structured output `{intent, injuries, summary}` | `KeywordInterpreter`: negation-aware, conservative | Keyword HELP/INJURY escalates *without waiting for the model*. A cancel needs the model to say OKAY and keywords not to object. If the model is down, keywords decide |
| Write the alert | `ClaudeComposer`: operator script + SMS, drafted in the background during the countdown | `TemplateComposer` | Escalation never waits for the model (`ai_wait_s = 0` in production). Output must pass `validate_ai_brief` (placeholders, length, no invented coordinates) or the template is used |
| Location | Never sent to the model | — | The model writes `{location}`, `{maps_url}`, `{time}`; code fills them with the latest fix at send time |

API usage: `claude-opus-5-5` through the Anthropic SDK, structured outputs (`output_config.format`),
`effort: "low"` for latency, server-side refusal fallbacks (`fallbacks: "default"`), an 8 s timeout and
1 retry. Any failure (timeout, refusal, truncation, invalid JSON, failed validation) falls back to the
deterministic twin.

### Delivery (`guardian/dispatch.py`)

- `DryRunNotifier` (simulator/tests), `TwilioNotifier` (SMS + text-to-speech calls, stdlib only),
  `SimulatedResponseCenter` (stand-in for a certified 24/7 partner).
- Every recipient is tried independently, and every attempt is recorded as a `Delivery`.
- **Automated contact with emergency short codes (911, 112, 999, …) is refused in code.**
  Emergency services are reached through the response-center partner, or by the occupant.
- Core plan: emergency contacts. Plus plan: response center + contacts. Severe crashes and
  unresponsive drivers also trigger voice calls to contacts.

## Simulator (`wayline/sim`)

Frenet-frame vehicle model (lateral-accel steering authority + actuator lag), clothoid-like
roads, BEV and camera renderers, 100 Hz IMU synthesis with crash pulses and jolts, GPS, a lead
car, and a simple human driver (with distraction) for manual-driving scenarios. `python -m wayline.sim --list`.

## Testing

`pytest`: 100+ tests covering perception accuracy (BEV and camera), controller and safety-gate
limits, driver-monitor timing, crash detection (true and false positives), every Guardian path,
the AI layer against a fake Claude client (request shape, privacy, validation, every fallback),
and every simulator scenario closed-loop.

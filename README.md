# Wayline

**The AI copilot that keeps you in your lane, and calls for help when you can't.**

[![CI](https://github.com/NeoFrees/wayline/actions/workflows/ci.yml/badge.svg)](https://github.com/NeoFrees/wayline/actions/workflows/ci.yml)
[Website](https://neofrees.github.io/wayline/) · [Business model](docs/BUSINESS_MODEL.md) · [Hardware blueprint](hardware/) · [Architecture](docs/ARCHITECTURE.md) · [Safety](docs/SAFETY.md)

> ⚠️ **Concept-stage prototype.** Everything here runs in simulation. It is not certified for
> road use and must not be connected to a vehicle on public roads. See [SAFETY.md](docs/SAFETY.md).

Wayline is an aftermarket driving copilot. It takes the proven open-source template (hands-free
lane centering and adaptive cruise for cars people already own) and adds the part that template
leaves out: **what happens when the drive goes wrong.**

| | |
|---|---|
| 🛣️ **Lane assist** | Lane-line perception (bird's-eye or camera with inverse perspective mapping), pure-pursuit lane centering with curvature feed-forward, adaptive cruise with time-gap following, lane-departure warning from yaw-rate path prediction |
| 👁️ **Driver monitoring** | Awareness model with escalating alerts and microsleep detection: hands-off, eyes-on |
| 🛑 **Emergency Stop Assist** | If the driver stops responding, Wayline keeps the lane and brings the car to a controlled stop with hazards on, instead of handing control back to someone who can't take it |
| 🚨 **Guardian** | Crash detection (high-g pulse → Δv, wheel-speed corroboration, airbag, rollover) → voice check-in → automatic alerts to emergency contacts and a 24/7 response center, with location, crash data and the occupants' own words |
| 🤖 **AI that can call for help** | Claude interprets what occupants say and writes dispatcher-grade alerts. **The AI never decides whether help is called**: deterministic escalation, keyword and template fallbacks that work offline, and the model never sees raw coordinates |
| 🔒 **Safety gate** | Hard limits, torque rate limits and instant driver override on every command |

## Quick start

```bash
git clone https://github.com/NeoFrees/wayline && cd wayline
python -m pip install -e ".[dev]"     # numpy + pytest
python -m wayline.sim --list
python -m wayline.sim crash           # also: drowsy, crash_injury, highway, lane_departure, sos, ...
python -m pytest -q                   # 100+ tests, all closed-loop scenarios included
```

```
=== crash: Frontal crash, driver doesn't answer
    1.00s  controls  ENGAGED: lane centering + adaptive cruise at 45 km/h
    8.10s  controls  DISENGAGED: crash detected — hands back to the driver, hazards on
    8.10s  guardian  Incident INC-0001: crash — frontal impact · Δv 38 km/h · peak 16.1 g · severity moderate · check-in 10s
    8.10s  voice     "This is Wayline Guardian. I detected a crash. Are you okay? I'll call for help in 10 seconds. Say "I'm okay" to cancel."
   13.10s  voice     "Calling for help in 5 seconds."
   18.10s  guardian  Calling for help — no response to the check-in
                     text to contacts: Wayline Guardian: Jordan may need help: a moderate frontal collision was detected
                       at 21:30 UTC. No answer to the voice check-in. Wayline's response center is arranging help.
                       Location: https://maps.google.com/?q=34.05311,-118.24370
   18.10s  dispatch  response_center → Wayline Response Center: delivered
   18.10s  dispatch  sms → Sam Lee (+1 555-0100): delivered
   18.10s  dispatch  sms → Alex Rivera (+1 555-0142): delivered
```

### Scenarios

| Scenario | What it shows |
|---|---|
| `highway` | Lane centering through S-bends at 97 km/h (max offset ≈ 4 cm) + ACC slowing for a braking lead car |
| `lane_departure` | Manual driving; driver looks at a phone on a bend; warning ≈ 0.9 s before the line |
| `drowsy` | Eyes close → alerts → unresponsive → Emergency Stop Assist → Guardian calls for help, then reports "car has stopped" |
| `drowsy_wakes` | Microsleep; alerts wake the driver; no stop |
| `crash` | 45 km/h frontal crash, no answer → help called after 10 s |
| `crash_okay` | Minor bump, "I'm okay" → stands down, nothing sent |
| `crash_injury` | Side impact + airbag, injury reported → immediate escalation; later words relayed |
| `sos` | "Wayline, call for help, I'm having chest pains" → 3 s to cancel → help called |
| `pothole` | Potholes, a speed bump and a knock → no false alarm |

Add `--camera` to run perception on rendered camera frames instead of a bird's-eye raster.

## Using Claude for Guardian's language layer

```bash
python -m pip install -e ".[ai]"
export ANTHROPIC_API_KEY=...          # or `ant auth login`
python -m wayline.sim crash_injury --ai
```

- Model: `claude-opus-5-5` (override with `WAYLINE_AI_MODEL`), structured JSON outputs, `effort: "low"`
  for latency, 8 s timeout. **Server-side refusal fallbacks are enabled** (`fallbacks: "default"`),
  so a declined request is retried on a fallback model inside the same call.
- In production the alert is drafted in the background during the countdown. If it isn't ready,
  or fails validation, the template goes out instead. Escalation never waits.

## Real notifications

`TwilioNotifier` sends SMS and text-to-speech calls (set `WAYLINE_TWILIO_SID`, `WAYLINE_TWILIO_TOKEN`,
`WAYLINE_TWILIO_FROM`). The simulator always uses `DryRunNotifier`. Automated contact with emergency
numbers (911, 112, 999, …) is refused in code. Emergency services are reached through a certified
response-center partner (the `ResponseCenter` interface).

## Repository layout

```
wayline/
  perception/   lanes.py (BEV lane fit), camera.py (pinhole model + inverse perspective mapping)
  control/      lateral.py, longitudinal.py, safety.py (the safety gate)
  monitoring/   driver.py (awareness → alerts → unresponsive)
  guardian/     crash.py, incident.py (state machine), ai.py (Claude + fallbacks), dispatch.py, report.py
  controls.py   the copilot main loop and mode machine
  sim/          world model, renderers, scenarios, CLI
tests/          perception, control, monitoring, crash, guardian, AI, end-to-end scenarios
docs/           BUSINESS_MODEL.md, ARCHITECTURE.md, SAFETY.md
hardware/       Wayline One blueprint, build guide, manufacturing guide, BOM, drawings
website/        the marketing site (deployed to GitHub Pages)
```

## Hardware

[`hardware/`](hardware/) is the Wayline One package:

- **[Blueprint](hardware/BLUEPRINT.md):** a QCS6490-class SoM, a lockstep Safety Gate MCU, and an always-on
  Guardian MCU on a backup-power domain. Three road cameras, an IR driver camera, a ±200 g IMU, LTE + eSIM,
  L1/L5 GNSS, 3× CAN-FD and a fail-safe harness.
- **[Build guide](hardware/BUILD_GUIDE.md):** bench prototype from dev kits → EVT → DVT → PVT → mass production.
- **[Manufacturing](hardware/MANUFACTURING.md):** candidate partners by category and region, the RFQ process,
  one-time costs (≈ $0.55–1.15M) and a ~15-month timeline.
- **[BOM](hardware/bom/wayline-one-bom.csv):** ≈ $1,066 landed per unit at 1k/yr, ≈ $751 at 10k/yr.
- **[Drawings](hardware/drawings/).**

## The business model

[docs/BUSINESS_MODEL.md](docs/BUSINESS_MODEL.md) has a teardown of the incumbent open-source
aftermarket-ADAS model (device near cost, optional subscription, community-driven car ports,
data flywheel) and Wayline's version of it:

- **Wayline One:** $1,199 with harness, Guardian Reserve backup cell
- **Core:** $0, including real safety features (*we never paywall safety*)
- **Plus:** $19/mo, with a 24/7 response center and LTE
- **Fleet:** $39/vehicle/mo
- **Insurance partnerships**

All of these are planned prices.

## License

MIT, see [LICENSE](LICENSE). Wayline is an independent project. It is designed to sit on top of the
MIT-licensed open-source driving ecosystem, but this repository is original code written for this
prototype.

# Wayline One: Build Guide

How to take Wayline One from this repository to a manufactured product, phase by phase.
Read with [BLUEPRINT.md](BLUEPRINT.md) (what to build) and [MANUFACTURING.md](MANUFACTURING.md) (who builds it).

> ⚠️ **Safety rules for every phase**
> - Never test actuation (steering/braking commands) on public roads. Use a closed course or private
>   property, with a trained safety driver, until the product has completed validation and legal review.
> - Never point automated calls or texts at emergency numbers. Test Guardian with your own phones.
>   The code blocks 911/112/999 on purpose.
> - Treat the Guardian Reserve cells as stored energy. Discharge before rework; follow the cell maker's
>   handling and transport rules (UN 38.3).
> - IR illuminators can exceed eye-safe limits during bring-up. Keep LED current limits in firmware from day one.

```
Phase A  Bench prototype ......... months 0–2    off-the-shelf dev kits, software bring-up
Phase B  EVT ..................... months 2–6    first custom boards, 20–50 units
Phase C  DVT ..................... months 6–11   production-intent design + tooling, 150–300 units, certification
Phase D  PVT ..................... months 11–14  real production line, 500–1,000 units
Phase E  Mass production ......... month 15+     ramp, sustaining engineering
```

---

## Phase A: Bench prototype from dev kits (months 0–2)

**Goal:** run the Wayline stack on real sensors and prove Guardian's power-loss path before designing any board.

### A1. Shopping list

| Function | Off-the-shelf part (examples) |
|---|---|
| Compute | Thundercomm TurboX C6490 dev kit, or NVIDIA Jetson Orin Nano Developer Kit |
| Road cameras | 3× AR0233-based MIPI camera modules (e.g. Leopard Imaging) with M12 lenses ≈ 2 / 4.4 / 8 mm; Arducam modules are fine for first bench work |
| DMS camera | AR0144-based global-shutter module + 940 nm band-pass filter + 940 nm IR LED board |
| Vehicle bus | PEAK PCAN-USB FD (or another SocketCAN-compatible CAN-FD adapter), 120 Ω terminators |
| Safety Gate MCU | NXP S32K344 evaluation board |
| Guardian MCU | ST NUCLEO-U575ZI-Q / STM32U5 discovery board |
| IMUs | ADI EVAL-ADXL372Z; ST ASM330LHHX evaluation board |
| Cellular | Quectel EG25-G mini-PCIe + USB adapter, test SIM from an IoT MVNO |
| GNSS | u-blox NEO-F10N evaluation kit + L1/L5 antenna |
| Reserve | ADI LTC3350 demo board + 2 LIC cell samples (or EDLC supercapacitors for first tests) |
| Audio | 4-mic PDM array board + I²S amplifier board + 28 mm speaker |
| Lab | Programmable bench PSU (cold-crank profiles), electronic load, 4-channel oscilloscope, CAN analyzer, thermal camera |

### A2. Bring up the software

```bash
git clone https://github.com/NeoFrees/wayline && cd wayline
python -m pip install -e ".[dev]"
python -m pytest -q                 # reference behaviour, 100+ tests
python -m wayline.sim all --quiet   # the closed-loop scenarios you are about to reproduce on hardware
```

Write thin hardware adapters that feed the same interfaces the simulator uses:

| Adapter | Feeds | Into |
|---|---|---|
| Camera capture (V4L2/GStreamer) | frames | `perception.camera.CameraLanePipeline.process()` |
| CAN reader (python-can + SocketCAN) | speed, yaw rate, pedals, steering torque, airbag | `controls.CarState` |
| IMU reader (SPI at 3.2 kHz, FIFO) | `ImuSample` batches | `guardian.crash.CrashDetector.update()` |
| GNSS reader (UBX/NMEA) | fixes | `guardian.types.GpsFix` |
| Modem driver | SMS / calls | a `Notifier` implementation (mirror `TwilioNotifier`'s interface) |

### A3. Calibrate

- **Intrinsics:** ChArUco board, OpenCV `calibrateCameraCharuco`, 30+ poses per camera. Store fx, fy, cx, cy and distortion per serial number.
- **Extrinsics:** mount the rig at its installed pitch and measure `mount_height` and `pitch`. These are the `PinholeCamera` parameters used for inverse perspective mapping.
- **IMU:** 6-position static calibration (bias, scale), then camera ↔ IMU alignment.

### A4. Prove the Guardian power-loss path (the most important bench test)

1. Power the Guardian MCU, modem, GNSS and amp from the LTC3350 output (VRES); charge the cells.
2. Arm the incident: inject a crash pulse (a drop test of the IMU board onto foam, or a replayed recorded pulse).
3. **Cut the 12 V input.** Confirm the countdown prompt plays and, with no cancel, an SMS with location reaches
   *your* test phone, followed by a voice call that plays the prompt.
4. Measure the energy used and the remaining voltage, and extrapolate the runtime. Target ≥ 10 min at end-of-life capacity.

### A5. Vehicle data logging (read-only)

On private property, log CAN + cameras + IMU in **listen-only mode** across ≥ 20 h of mixed driving.
This produces the car-port DBC mapping, real IMU noise for crash-detector tuning, and the false-alarm baseline.

**Phase A exit:** the stack runs on dev kits at target rates; Guardian completes the power-loss test; logs are captured.

---

## Phase B: EVT, the first custom hardware (months 2–6)

### B1. Freeze the EVT design

Lock [BLUEPRINT.md](BLUEPRINT.md) Rev A requirements, the SoM choice (after the camera-concurrency benchmark), and the camera module supplier.

### B2. Schematics (KiCad)

| Sheet | Contents |
|---|---|
| 01 Power input | TVS, ideal diode, π-filter, ignition sense, 5 V and 3.3 V bucks |
| 02 Guardian Reserve | LTC3350, LIC cells, VRES rail, power-fail comparator |
| 03 SoM | Board-to-board connectors, boot straps, debug UART, USB, PMIC rails |
| 04 Cameras | 4× MIPI CSI-2 connectors, clocks, power sequencing, IR strobe sync |
| 05 Safety Gate | S32K344, 3× TJA1462, relay drivers, SPI to SoM, JTAG/SWD |
| 06 Guardian MCU | STM32U585, ADXL372, ASM330LHHX, FRAM, SOS input, status LEDs, SWD |
| 07 Cellular & GNSS | EG25-G, eUICC, antennas/matching, NEO-F10N, PCM switch |
| 08 Audio | PDM mic connectors, TAS2563 amp, speaker |
| 09 UI & fan | OLED connector, fan PWM + tach, temperature sensors |
| 10 Harness box | Relays (NC), ESD, PTC fuse, connectors (separate project) |

### B3. Reviews before layout

- Schematic peer review, plus a datasheet "application circuit" check for every IC.
- Power budget and sequencing review; worst-case cold-crank (6 V) and load-dump analysis.
- Fault-tree check: no single fault can command actuation without the Safety Gate's agreement.
- DFT: test points on every rail and bus; SWD/JTAG headers; a pogo-pin footprint for the factory fixture.

### B4. Layout rules

- 10-layer HDI stack-up from the fab's standard offering. Request their impedance table first.
- MIPI/USB 90 Ω differential, length-matched; CAN 120 Ω pairs to the connector, with ESD at the connector.
- IMUs on a rigid island near the board centroid, away from the fan and the speaker; no flex under them.
- RF: modem and GNSS at the top edge, with antenna keep-outs and a stitched ground fence; U.FL test ports.
- Thermal: SoM under the die-cast boss; thermal vias under PMICs; no electrolytics near hot spots.
- Run DFM with **the assembler you will use for EVT** (see [MANUFACTURING.md](MANUFACTURING.md)).

### B5. Order EVT parts

- PCBs and assembly: 10–25 main boards, plus cabin and harness-box boards, quick-turn.
- Camera modules: engineering samples from the module supplier, active-aligned with your lens choices.
- Mechanics: SLS/MJF PA12 shells and hood, CNC 6061 rear frame and camera bracket, laser-cut VHB.
- Long-lead parts: SoM, image sensors and the modem can take **16–26 weeks**. Place the orders now.

### B6. Board bring-up checklist (per unit)

1. Visual/AOI inspection; X-ray any BGA/LGA (SoM connectors, modem).
2. Current-limited 12 V power-up (≤ 0.5 A); verify every rail, ripple and sequencing.
3. Flash and boot the Guardian MCU; check the IMU WHO_AM_I registers, FRAM read/write and the SOS input.
4. Flash the Safety Gate; run a CAN loopback on all 3 buses; with the relays de-energized, confirm the stock path passes through.
5. Boot the SoM; enumerate the cameras, mics, OLED, Wi-Fi and modem (USB).
6. Modem: register on the network, SMS to the test phone, voice call with the PCM path; GNSS fix.
7. Reserve: charge, then a backup boost test with a pull-the-plug drill.
8. Thermal: 30 min at full load in a 45 °C chamber; log temperatures.

### B7. Firmware deliverables for EVT

- **Safety Gate (S32K344):** MISRA C port of `control/safety.py` (limits, rate limits, override); SoM heartbeat timeout
  → zero commands; relay control with fail-safe default; per-vehicle message checks; unit tests and HIL tests.
- **Guardian MCU (Zephyr):** C port of `guardian/crash.py` and the escalation timers from `guardian/incident.py`;
  modem AT driver (SMS, voice, retries); GNSS; FRAM black box; Reserve health via LTC3350; stored prompts.
- **SoM:** Yocto BSP, camera ISP tuning for the AR0233AT, NPU model deployment, Wayline OS services, OTA client.

### B8. EVT test plan

| Test | Method | Pass criteria |
|---|---|---|
| Functional | Scripted checklist B6 on all units | 100% pass, or failures root-caused |
| Power transients | ISO 7637-2 / ISO 16750-2 pre-test with a programmable supply | No reset during cold crank; survives load dump |
| EMC pre-scan | Near-field probes + LISN per CISPR 25 setup | Margins identified, fixes planned |
| Thermal | −30 °C start, +85 °C operation, solar-load soak | No unplanned shutdowns; throttling works |
| Guardian Reserve | Pull-the-plug at 25 °C / 85 °C / −20 °C | ≥ 10 min runtime with EOL derating |
| Crash detection | Drop tower / sled pulses + 100 h of driving logs | Detects all target pulses; zero false triggers on logs |
| Audio | Mic sensitivity sweep; speaker SPL at 50 cm; echo cancellation during a call | Check-in intelligible at highway noise |
| Vehicle (closed course) | Lane centering and ESA with a safety driver | Meets the simulator's behaviour envelope |

**Phase B exit:** design-intent functions all work; open issues list with owners; decision on fan vs. passive cooling.

---

## Phase C: DVT, production intent (months 6–11)

1. **Design changes** from EVT; final DFM with the chosen EMS, molder and die-caster.
2. **Tooling:** cut steel molds for the shells, hood and light pipe, plus the die-cast tool for the rear frame.
   Approve T0/T1 samples (dimensions, texture, colour, flash, sink marks) against the drawings in `hardware/drawings/`.
3. **Build 150–300 units at the production EMS**, using production processes where possible.
4. **Certification:** run the full list in [BLUEPRINT.md §13](BLUEPRINT.md#13-compliance-and-certification) at an accredited lab.
   Book the lab early, because slots fill months ahead.
5. **Reliability:** HALT on 5–10 units, temperature cycling, ISO 16750-3 vibration, mechanical shock, 1 m drop
   (packaged) per ISTA 3A, high-temperature operating life, Reserve cell aging.
6. **Validation fleet:** 50–100 units with trained drivers. Measure lane-centering interventions, driver-monitoring
   false alerts, **Guardian false-alarm rate** (target < 1 per 10,000 h) and time-to-alert.
7. **Car ports:** produce and validate harness SKUs for the launch car families.

**Phase C exit:** certifications granted or in final review; reliability passed; fleet metrics at target.

---

## Phase D: PVT, the production line (months 11–14)

### D1. Factory flow

```
SMT (main/cabin) ─► AOI ─► X-ray (BGA/LGA) ─► ICT / flying probe ─► FW flash + secure provisioning (HSM)
 ─► Box build (camera bracket, boards, Reserve, cabin board, frame) ─► Camera calibration station
 ─► Functional test station ─► Burn-in (4 h @ 55 °C) ─► Final QA + cosmetic ─► Pack ─► Out-of-box audit
```

| Station | What it checks | Target time |
|---|---|---|
| ICT / flying probe | Shorts, opens, component values | 60–90 s |
| Provisioning | Signed firmware on all 3 processors, device keys in ATECC608B, serial ↔ IMEI ↔ eUICC binding | 90 s |
| Camera calibration | Intrinsics per camera (ChArUco target wall), stereo/extrinsic check of the bracket, DMS focus at 60 cm | 120 s |
| Functional test | CAN loopback through the relays, RF conducted power (LTE), GNSS sim signal, IMU 6-face, mic/speaker sweep, OLED, SOS, fan tach, Reserve charge + capacitance/ESR | 180 s |
| Burn-in | Thermal soak with an active stress pattern | 4 h (batch) |

### D2. Pilot run

500–1,000 units. Targets: first-pass yield ≥ 95%; calibration Cpk ≥ 1.33; zero safety-critical escapes.

### D3. Production documents

Control plan, PFMEA, work instructions with photos, golden samples, packaging spec (ISTA 3A),
traceability (unit serial ↔ PCB serials ↔ component lots), and an RMA/failure-analysis process.

---

## Phase E: Mass production and sustaining (month 15+)

- Ramp in steps (e.g. 500 → 2,000 → 5,000 per month) gated on yield and field-return data.
- Ongoing reliability testing on a sample of each lot.
- Engineering change control: every hardware change re-runs the affected tests.
- Qualify **second sources** for the SoM, modem, LIC cells and camera modules.
- Field telemetry (opt-in): Guardian Reserve health, thermal throttling, false-alarm rate. These feed firmware tuning.

---

## Team needed (EVT → PVT)

| Role | Why |
|---|---|
| Hardware lead (EE) | Architecture, schematics, bring-up, supplier technical reviews |
| PCB / layout engineer (contract OK) | HDI layout, SI/PI, DFM |
| Mechanical engineer | Enclosure, thermal, tooling with the molder/die-caster |
| Camera / ISP engineer | Sensor tuning, calibration stations, optics with the module supplier |
| Firmware engineers ×2 | Safety Gate (MISRA C), Guardian MCU (Zephyr), modem/GNSS drivers |
| Embedded Linux engineer | Yocto BSP, OTA, secure boot |
| Test / manufacturing engineer (NPI) | Fixtures, stations, yields, factory relationship |
| Compliance consultant | Test plans, lab coordination, certifications |
| Supply-chain manager | Long-lead parts, second sources, contracts |

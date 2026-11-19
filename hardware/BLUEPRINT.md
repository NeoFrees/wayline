# Wayline One: Design Blueprint

**Document:** WL1-BLP · **Revision:** A (concept) · **Status:** pre-EVT design intent

> This blueprint describes the *intended* design of Wayline One, to be validated through EVT/DVT/PVT
> (see [BUILD_GUIDE.md](BUILD_GUIDE.md)). Part numbers are **candidates with alternates**, chosen
> because they exist and fit. Each must be confirmed against current datasheets, lifecycle status and
> quotes. Costs are budgetary estimates. Nothing here is certified for road use.

**Contents**
1. [Product requirements](#1-product-requirements)
2. [System architecture](#2-system-architecture)
3. [Compute](#3-compute)
4. [Sensors](#4-sensors)
5. [Connectivity and Guardian fallback path](#5-connectivity-and-guardian-fallback-path)
6. [Power architecture and Guardian Reserve](#6-power-architecture-and-guardian-reserve)
7. [Vehicle interface and harness](#7-vehicle-interface-and-harness)
8. [Mechanical design](#8-mechanical-design)
9. [Thermal design](#9-thermal-design)
10. [PCB set](#10-pcb-set)
11. [Firmware and software partitioning](#11-firmware-and-software-partitioning)
12. [Functional safety and security](#12-functional-safety-and-security)
13. [Compliance and certification](#13-compliance-and-certification)
14. [Bill of materials summary](#14-bill-of-materials-summary)
15. [Open design questions](#15-open-design-questions)

---

## 1. Product requirements

| ID | Requirement | Target |
|---|---|---|
| R1 | Lane centering, ACC, lane-departure warning on supported cars | Runs Wayline OS at ≥ 20 Hz perception, 100 Hz control |
| R2 | Three forward cameras | Wide ~120° / main ~60° / narrow ~30° HFOV, HDR ≥ 120 dB, LED-flicker mitigation |
| R3 | Driver monitoring, day and night, with sunglasses | 940 nm IR global-shutter camera, synchronized IR illumination, IEC 62471 exempt group |
| R4 | Crash detection | High-g accelerometer ±200 g at ≥ 3.2 kHz; 6-axis IMU; CAN airbag/wheel-speed where available |
| R5 | **Guardian survives loss of vehicle power** | ≥ 10 min of Guardian operation (location, SMS, one voice call, prompts) at end of life |
| R6 | Guardian independent of the main computer | Separate always-on MCU, power domain and modem control path |
| R7 | Voice check-in | 4-mic array + speaker; two-way audio for calls |
| R8 | Connectivity | LTE Cat 4 with eSIM + Wi-Fi/BT; dual-band GNSS (L1/L5) |
| R9 | Vehicle networks | 3× CAN-FD; fail-safe pass-through harness (stock behaviour when unpowered) |
| R10 | Physical SOS | Guarded, illuminated button wired to the Guardian MCU |
| R11 | Status display | 1.5" OLED + RGB status ring |
| R12 | Environment | Operating −30…+85 °C ambient; storage −40…+85 °C; ISO 16750 passenger-car body mount |
| R13 | Size / mass | ≤ 152 × 74 × 38 mm body (hood excluded); ≤ 320 g |
| R14 | Install | ≤ 15 min, no tools beyond a trim tool; reversible |
| R15 | Cost | Landed cost ≤ $880 at 3–5k units/yr (see §14) |

---

## 2. System architecture

```
                              VEHICLE (12 V, CAN)
                 ┌──────────────────┴──────────────────────────┐
   LKAS camera ──┤ HARNESS BOX: NC relays = stock pass-through │── car gateway / EPS
                 │ 2 A PTC fuse · ESD · ignition sense         │
                 └──────────────────┬──────────────────────────┘
                    1.5 m shielded cable · 12-pin locking connector
┌───────────────────────────────────┴───────────────────────────────────────────────────┐
│ WAYLINE ONE                                                                          │
│                                                                                      │
│  ┌──────────── MAIN DOMAIN (vehicle 12 V) ─────────────┐    ┌──── SAFETY GATE ─────┐ │
│  │ SoM: QCS6490-class SoC · 8 GB LPDDR5 · 128 GB UFS   │SPI │ NXP S32K344 lockstep │ │
│  │  ├ MIPI-CSI ×3  ← road cams (AR0233AT ×3)           │◄──►│  3× CAN-FD (TJA1462) │─┼─► CAN A/B/C
│  │  ├ MIPI-CSI ×1  ← DMS cam (AR0144AT, 940 nm)        │    │  relay drive, limits │ │
│  │  ├ PDM ×4       ← MEMS mics                          │    │  heartbeat watchdog  │ │
│  │  ├ SPI          → 1.5" OLED                           │    └──────────────────────┘ │
│  │  ├ Wi-Fi 6/BT (on SoM)                               │                              │
│  │  └ USB 2.0 ────────────────────────────┐             │                              │
│  └────────────────────────────────────────┼─────────────┘                              │
│                                           │                                            │
│  ┌──────────── GUARDIAN DOMAIN (VRES, always on, backed by Guardian Reserve) ───────┐ │
│  │ STM32U585 Guardian MCU ── UART/PCM ──► Quectel EG25-G LTE (USB to SoC) ── eSIM   │ │
│  │   ├ SPI  ← ADXL372 ±200 g      ├ I²C ← ASM330LHHX 6-axis    ├ UART ← NEO-F10N GNSS│ │
│  │   ├ SPI  → 256 kbit FRAM black box  ├ GPIO ← SOS button   ├ I²S → speaker amp     │ │
│  │   └ I²C  ↔ LTC3350 backup controller ↔ 2× lithium-ion-capacitor cells (Reserve)   │ │
│  └───────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Partitioning principle.** Three independent "brains", each owning what it must guarantee:

| Domain | Owns | Fails safe by |
|---|---|---|
| **SoM** (Linux) | Perception, planning, UI, voice, AI language layer, OTA | Watchdogs in both MCUs; losing it means no assistance, never unsafe actuation |
| **Safety Gate MCU** | Every byte that reaches the car's actuators | Default relay state = stock car; zero torque/accel if the SoM heartbeat is missing > 100 ms |
| **Guardian MCU** | Crash detection, escalation timers, modem fallback, black box | Runs on the Reserve; needs nothing else to call for help |

---

## 3. Compute

| Item | Choice | Alternates | Notes |
|---|---|---|---|
| Main SoM | **Qualcomm QCS6490-class SoM** (e.g. Thundercomm TurboX C6490): 8× Kryo 670, Adreno 643, Hexagon NPU (~12 TOPS), 8 GB LPDDR5, 128 GB UFS, Wi-Fi 6E/BT 5.2 | NVIDIA Jetson Orin Nano 8 GB (more TOPS, more W); NXP i.MX 8M Plus (lower cost, 2.3 TOPS) | Industrial temp grade; must support ≥ 4 concurrent MIPI cameras. **Confirm concurrency with the SoM vendor** |
| Safety Gate MCU | **NXP S32K344** (Cortex-M7 lockstep, ASIL D-capable, FlexCAN with CAN-FD) | Infineon AURIX TC3xx; ST SPC58 | Runs the actuation rules from `wayline/control/safety.py`, ported to MISRA C |
| Guardian MCU | **ST STM32U585** (Cortex-M33, TrustZone, ultra-low-power) | Nordic nRF5340; NXP LPC55S69 | Zephyr RTOS; C port of `wayline/guardian/crash.py` + escalation timers |
| Secure element | **Microchip ATECC608B** | NXP SE050 | Device identity, OTA signature keys, cloud TLS |
| Black-box memory | **256 kbit SPI FRAM** (Infineon CY15B256J / Fujitsu MB85RS256) | — | 2 s pre/post-crash IMU + CAN snapshot; no wear-out |

Power budget, main domain: 5–9 W typical (perception on NPU), 12 W peak.

---

## 4. Sensors

### 4.1 Road cameras (×3, one sensor family)

| Camera | Sensor | Lens (M12, automotive) | Use |
|---|---|---|---|
| Wide | onsemi **AR0233AT** 2.6 MP, 120 dB HDR, LFM | ~2.0 mm, HFOV ≈ 120° | Cut-ins, intersections, near lane lines |
| Main | AR0233AT | ~4.4 mm, HFOV ≈ 60° | Primary lane and lead-vehicle perception |
| Narrow | AR0233AT (option: AR0820AT 8.3 MP) | ~8 mm, HFOV ≈ 30° | Long-range lanes and vehicles |

- One sensor family means one ISP tuning and one supply chain. LED-flicker mitigation (LFM) is needed for LED traffic lights and signs.
- The modules are **active-aligned and focus-locked by the camera-module supplier**, then bonded to one **aluminium camera bracket** so their relative pose (extrinsics) is stable. Baseline ≈ 30 mm between optical centres. Optical axes are parallel within ±0.5°.
- Lenses: automotive M12 glass lenses with IR-cut filters (suppliers in [MANUFACTURING.md](MANUFACTURING.md#camera-modules-and-optics)).
- Interface: MIPI CSI-2, 4-lane, on short rigid-flex. No serializers are needed inside one enclosure.

### 4.2 Driver-monitoring camera

- **onsemi AR0144AT** 1 MP global shutter, mono, with a 940 nm band-pass filter (alternate: OmniVision OX05B1S RGB-IR).
- 2× 940 nm IR LEDs (OSRAM OSLON Black class), strobed in sync with exposure through a constant-current driver; average power kept within the **IEC 62471 exempt group** at 30 cm.
- 940 nm passes through most sunglasses and is invisible to the driver.

### 4.3 Motion

| Part | Role | Placement |
|---|---|---|
| ADI **ADXL372** ±200 g, up to 3.2 kHz ODR | Crash pulse capture (Δv), FIFO with 2 s pre-trigger | Main board, at the body's centre of mass, rigid (not on flex) |
| ST **ASM330LHHX** 6-axis, AEC-Q100 | Motion, gravity vector (rollover), camera/IMU alignment, dead reckoning | Same rigid region |

### 4.4 Audio

- 4× **Infineon IM69D130** PDM MEMS microphones: 2 on the cabin face (beamformed toward the driver and passenger), 2 on the top edge for echo reference and noise estimation.
- Amplifier **TI TAS2563** (or MAX98357A) driving a 28 mm, 2 W full-range speaker. The amp sits on the Guardian domain so prompts and calls work on the Reserve.

### 4.5 GNSS

- **u-blox NEO-F10N** (L1/L5 dual band), with **Quectel LC29H** as alternate. It is fused on the SoM with the IMU and CAN wheel speed for dead reckoning in tunnels and urban canyons.

---

## 5. Connectivity and Guardian fallback path

| Item | Choice | Notes |
|---|---|---|
| Cellular | **Quectel EG25-G** (LTE Cat 4, global bands, voice + SMS) | Carrier-certified module; USB to the SoM for data, UART + PCM to the Guardian MCU for fallback |
| SIM | MFF2 **eUICC** (eSIM) soldered (e.g. Thales, G+D, Kigen) | Multi-profile; no SIM tray to fail in a crash |
| Antennas | Flex LTE main + diversity, L1/L5 GNSS patch (e.g. Taoglas, Molex) | Placed at the top edge behind the mirror. Some coated (IR-reflective) windshields attenuate RF, so design a U.FL test port and qualify on coated glass |
| Wi-Fi / BT | On the SoM | Phone pairing, home Wi-Fi uploads |

**Fallback path (SoM dead or car power lost):**
`Guardian MCU → AT commands → EG25-G → SMS with location → voice call playing pre-recorded prompts (stored in MCU flash) → retry loop`.
The audio switch (TI TS5A23157-class) hands the PCM path from the SoM to the Guardian MCU.

> Automated calls to emergency short codes (911/112/999) are **blocked in firmware**, as in
> `wayline/guardian/dispatch.py`. Emergency services are reached through a certified response
> partner or by the occupant.

---

## 6. Power architecture and Guardian Reserve

```
 12 V harness ─► TVS (SM8S33A class, ISO 16750-2 load dump) ─► ideal-diode (TI LM74700-Q1 + FET, reverse polarity)
             ─► π-filter (CISPR 25) ─┬─► 5.0 V / 4 A sync buck (TI LM61460-Q1) ─► SoM PMIC ─► SoM, cameras, OLED, fan
                                     ├─► 3.3 V / 1 A buck ─► Safety Gate MCU, CAN transceivers
                                     └─► ADI LTC3350 backup controller ─► VRES 3.8 V (always-on Guardian domain)
                                                     ▲      │
                                     2× LIC cells ───┘      └─► Guardian MCU, EG25-G, GNSS, ADXL372, ASM330, FRAM, amp
```

| Parameter | Target |
|---|---|
| Input operating range | 6–36 V (cold crank to jump start), survives −14 V reverse and ISO 16750-2 pulse 5b |
| Quiescent (ignition off, Guardian armed) | < 3 mA @ 12 V |
| Main domain power | 5–9 W typical, 12 W peak |
| Guardian fallback load | ≈ 2.5 W average (modem in call ≈ 1.8 W, GNSS 0.1 W, MCU + sensors 0.1 W, amp 0.5 W) |

**Guardian Reserve sizing**

- Cells: 2× **lithium-ion capacitor (LIC / hybrid supercapacitor)**, 3.8 V, ≥ 250 F class, rated −25…+85 °C
  (vendor families: Musashi/JSR *ULTIMO*, Eaton *HS/HSL*). Chosen over Li-ion because of windshield heat
  and over plain EDLC supercapacitors because of energy density.
- Usable energy per cell ≈ ½ · C · (3.8² − 2.2²) = ½ · 250 · 9.6 ≈ 1.2 kJ, so **≈ 2.4 kJ for the pair**.
- Runtime ≈ 2.4 kJ ÷ 2.5 W ≈ **16 min new, ≈ 11 min at end of life** (30% capacitance fade): meets R5.
- LTC3350 monitors capacitance and ESR in the field. If health drops below the 10-minute threshold,
  the app tells the owner.
- **Hot soak:** above the cell rating, charging stops and the device reports reduced Reserve availability.
  Validate with a 100 °C dashboard soak test (§13).

---

## 7. Vehicle interface and harness

```
  car-side connector ◄──── Y-harness ────► camera-side connector        (vehicle-specific, OEM-compatible)
                         │
                   ┌─────┴─────────────────────────────┐
                   │ HARNESS BOX (2-layer PCB)          │
                   │  RL1/RL2: DPDT signal relays, NC   │  unpowered/fault  → camera ⇄ car direct (stock)
                   │  ESD: NXP PESD2CANFD ×3            │  engaged & healthy → camera ⇄ Wayline ⇄ car
                   │  PTC fuse 2 A on 12 V tap          │
                   └─────┬─────────────────────────────┘
                         │ 1.5 m cable: 3× CAN-FD twisted pairs (120 Ω), 12 V, GND, IGN sense, relay drive, shield
                         ▼
                 Wayline One harness port: 12-pin locking (Molex Mini50 or TE NanoMQS class)
```

| Bus | Purpose |
|---|---|
| CAN-A | Lane-keep camera ⇄ car. Intercepted for steering commands when engaged |
| CAN-B | Powertrain/chassis: wheel speeds, yaw rate, pedals, steering torque, airbag status (where exposed) |
| CAN-C | ACC/radar bus where applicable |

- **Fail-safe by construction:** the relays are normally closed in the stock path. Unplug the device, lose power,
  or trip the Safety Gate watchdog, and the car behaves exactly as it does from the factory.
- One harness SKU per *car family* (connector + pinout). Pinouts and message definitions come from the
  per-vehicle car port (open-source DBC databases).
- The device-side connector is deliberately **not USB-C**, so it can't be mistaken for a charging port.

---

## 8. Mechanical design

```
          FRONT (road side)                        SIDE                          REAR (cabin side)
 ┌──────────────────────────────────┐      ┌──────────────┐          ┌──────────────────────────────────┐
 │   ◯ wide    ◯ main    ◯ narrow   │      │▓ mount rail ▓│          │ ▣ OLED 1.5"     ◉ DMS  ✷ ✷ IR    │
 │  └──────── glare hood ────────┘  │      │  ╲ hood      │          │                                  │
 │                                  │ 74   │   ╲  ┌──────┐│ 74       │ ∴ mics        ░░ speaker ░░      │
 │                                  │      │    ╲ │ body ││          │                         (SOS) ◎  │
 └──────────────────────────────────┘      └──────┴──────┘┘          └──────────────────────────────────┘
                 152                            38 (+40 hood)                        152
                                                                    bottom edge: harness port ⊟ · fan intake ≡
```

| Part | Material / process | Notes |
|---|---|---|
| Front shell | PC/ABS, heat-resistant grade (Covestro Bayblend T85 / SABIC Cycoloy class), UV-stabilized, UL94 V-0, matte texture MT-11010 | 1.8–2.2 mm walls, 0.5° draft min |
| Rear frame / heatsink | Die-cast aluminium **ADC12 / A380**, powder-coated black, fins on top | Structural spine + SoM heat path |
| Glare hood | PC/ABS, internal baffles, textured matte black (VDI 3400 Ref 33+), foam gasket to glass | Blocks dashboard reflections into the road cameras |
| Camera bracket | CNC 6061-T6 aluminium (die-cast at volume) | Holds all three road modules co-planar |
| Windshield mount | Stamped steel plate + **3M VHB 5952** (or 3M 4229P automotive acrylic foam), dovetail quick-release with spring latch + safety screw | Factory pitch nominal; online calibration absorbs ±5° |
| Buttons / light pipes | SOS: 12 mm IP67 tactile under a raised guard ring; light pipe PC for the RGB ring | Guard prevents accidental presses |
| Fasteners | 4× M2 Torx thread-forming screws (plastics) + 4× M2 machine screws into die-cast | No adhesives in the service path |
| Ingress | IP4X (cabin dust); dust mesh on the fan intake | No liquid exposure expected |

**Tolerance stack priorities:** camera bracket to glass angle (±1°), DMS camera aim at the driver's head box,
and mic port alignment to the gaskets (acoustic leaks degrade beamforming).

---

## 9. Thermal design

- Heat path: SoM → 0.5 mm gap pad (≥ 6 W/m·K) → die-cast rear frame (fins) → cabin air.
- Active assist: 30 × 30 × 7 mm blower (5 V PWM, ball bearing), with intake at the bottom (filtered) and exhaust at the top-rear, away from the glass.
- Policies:
  - SoC junction > 95 °C: lower the perception rate.
  - Internal ambient > 85 °C: disengage with a warning.
  - The Guardian domain always runs (parts rated ≥ 105 °C, except the LIC cells: see §6).
- Validate in a climatic chamber with solar load: −30 °C cold start, +85 °C operating, +100 °C hot soak (unpowered).

---

## 10. PCB set

| Board | Stack-up | Highlights |
|---|---|---|
| **Main board** (~120 × 60 mm) | 10-layer HDI (1+8+1), high-Tg FR-4 (Tg ≥ 170 °C), ENIG | SoM board-to-board connectors; 90 Ω MIPI/USB differential, 120 Ω CAN; IMUs on a rigid island; RF keep-outs |
| **Camera boards** ×3 + **DMS board** | 4-layer rigid-flex | Supplied as finished modules by the camera-module vendor |
| **Cabin board** | 4-layer | OLED, mics, IR LEDs + driver, SOS button, RGB ring; flex to the main board |
| **Harness box** | 2-layer, 2 oz Cu | Relays, ESD, fuse; conformal coated |

Fab class: **IPC-6012 Class 3** with the automotive addendum (IPC-6012DA); assembly to **IPC-A-610 Class 3**.
Design tool: **KiCad** (open source, matching the open-hardware positioning). Release package format: ODB++ or Gerber X2 + IPC-2581.

---

## 11. Firmware and software partitioning

| Layer | Runs on | Contents | Source in this repo |
|---|---|---|---|
| Wayline OS | SoM, Yocto Linux, A/B rootfs, dm-verity | camera pipeline, perception (NPU), `controls.py` loop, UI, voice, Guardian language layer | `wayline/` |
| OTA | SoM | RAUC / SWUpdate / Mender with signed bundles, staged rollout, automatic rollback | — |
| Safety Gate | S32K344, bare-metal / AUTOSAR-lite, MISRA C:2012 | Torque/accel limits, rate limits, driver override, heartbeat, per-vehicle message checks (counters/CRC) | `wayline/control/safety.py` (reference) |
| Guardian | STM32U585, Zephyr RTOS | Crash detection, escalation timers, SOS, modem/GNSS drivers, FRAM black box, Reserve health | `wayline/guardian/crash.py`, `incident.py` (reference) |

Interfaces: SoM ⇄ Safety Gate over SPI at 100 Hz, with a 10 ms heartbeat. SoM ⇄ Guardian over UART with a protobuf framing.
The **SoM can enrich Guardian (voice, AI wording) but can never suppress an escalation.**

---

## 12. Functional safety and security

- **Process:** ISO 26262-inspired (target ASIL B practices for the Safety Gate), ISO 21448 (SOTIF) for perception limits,
  hazard analysis (HARA) per supported feature, FMEA on hardware, fault injection on HIL rigs.
- **Safety mechanisms:** lockstep core, dual heartbeat, relay fail-safe, actuation limits independent of the SoM,
  brown-out detection, independent watchdogs, CAN message plausibility checks.
- **Security:** secure boot on all three processors, signed firmware, per-device keys in the ATECC608B, encrypted storage,
  no inbound network services, ISO/SAE 21434 threat analysis (TARA), coordinated vulnerability disclosure.

---

## 13. Compliance and certification

| Area | Standards / programs |
|---|---|
| RF / EMC (product) | FCC Part 15 B (+ modular grants for the modem and Wi-Fi), ISED, CE-RED, UKCA |
| Automotive EMC | CISPR 25 (emissions), ISO 11452-2/-4 (immunity), ISO 7637-2 (transients); **UN ECE R10 E-mark** for EU aftermarket |
| Environmental | ISO 16750-2 (electrical), -3 (mechanical: vibration and shock), -4 (climatic), plus a solar-load hot-soak test |
| Cellular | PTCRB + carrier certification (AT&T, Verizon, T-Mobile) via the module's pre-certifications |
| Energy storage | UN 38.3 (transport), IEC 62133 where applicable to the reserve cells |
| Photobiological | IEC 62471 for the IR illuminators |
| Product safety | IEC/UL 62368-1 |
| Materials | RoHS, REACH, California Prop 65 |
| Process | ISO 26262 / ISO 21448 practices; ISO/SAE 21434 cybersecurity; quality per ISO 9001 (IATF 16949 at the EMS) |

---

## 14. Bill of materials summary

Full line-item BOM: [`bom/wayline-one-bom.csv`](bom/wayline-one-bom.csv). Budgetary, per unit:

| Group | @1k units | @10k units |
|---|---|---|
| Compute (SoM, Safety Gate MCU, Guardian MCU, CAN-FD transceivers, secure element, FRAM) | $305 | $232 |
| Cameras (3 road modules, DMS module, IR LEDs + driver) | $205 | $140 |
| Connectivity (LTE module, eSIM, antennas, GNSS) | $105 | $80 |
| Sensors and audio (IMUs, mics, amp, speaker) | $30 | $22 |
| Power and Guardian Reserve (front end, regulators, LTC3350, LIC cells) | $65 | $45 |
| PCBs and assembly (main, cabin, flex) | $70 | $40 |
| Mechanical (shells, die-cast frame, hood, bracket, mount, fan, gaskets, fasteners) | $85 | $46 |
| UI (OLED, SOS button, light pipe) | $16 | $11 |
| Harness (vehicle-specific Y-harness, harness box, cable) | $60 | $45 |
| Factory (final assembly, calibration, test, burn-in) | $45 | $25 |
| Packaging, freight, duties, yield allowance | $80 | $65 |
| **Landed cost (est.)** | **≈ $1,066** | **≈ $751** |

At the planned **$1,199** price this gives roughly 11% gross margin at 1k units/yr and 37% at 10k.
The ≈25% target in the business plan is reached at roughly 3–5k units/yr. One-time engineering
and tooling costs are in [MANUFACTURING.md](MANUFACTURING.md#cost-nre-and-timeline).

---

## 15. Open design questions

1. **SoM camera concurrency and NPU throughput** for 3 road cameras + DMS at the target frame rates. Get vendor benchmarks before freezing.
2. **LIC cell selection** (size vs. capacitance vs. temperature) and the hot-soak strategy. Alternative: a small LTO cell with stricter thermal management.
3. **RF through coated windshields.** Decide whether an optional external antenna lead is needed.
4. **Harness architecture per car family.** Some cars put lane-keep on the CAN-FD gateway rather than the camera bus, which changes the intercept point.
5. **Fan vs. passive cooling** after thermal EVT data. Fans are a reliability and noise item.
6. **Voice on-device vs. cloud** split for the AI language layer, given latency, privacy and per-incident cost.

# Wayline Business Model

> **Status:** concept-stage plan with a working software prototype in this repo. Prices are *planned*;
> unit economics are *illustrative assumptions* to be validated, not results.

**Contents**
1. [Executive summary](#1-executive-summary)
2. [Teardown: the comma.ai model](#2-teardown-the-commaai-model)
3. [Where the incumbent model leaves room](#3-where-the-incumbent-model-leaves-room)
4. [The Wayline model](#4-the-wayline-model)
5. [Products and pricing](#5-products-and-pricing)
6. [Unit economics (illustrative)](#6-unit-economics-illustrative)
7. [The flywheel](#7-the-flywheel)
8. [Go-to-market and roadmap](#8-go-to-market-and-roadmap)
9. [Competitive landscape](#9-competitive-landscape)
10. [Metrics that matter](#10-metrics-that-matter)
11. [Risks and mitigations](#11-risks-and-mitigations)

---

## 1. Executive summary

The aftermarket driver-assistance market has a proven template: an **open-source driving stack**,
a **device sold near cost**, an **optional subscription**, and a **community that ports new cars
and fixes bugs for free**. It turns ordinary cars into hands-off, eyes-on cars for about the price of a phone.

That template is built for enthusiasts. Its value stops when the drive goes wrong: when the
driver nods off, has a medical event, or crashes. **Wayline** keeps the proven template and adds what
mainstream, safety-motivated buyers need:

| | Incumbent template | **Wayline** |
|---|---|---|
| Lane centering + adaptive cruise | ✅ | ✅ (builds on the same open ecosystem) |
| Driver monitoring | Alerts, then **disengages** | Alerts, then **Emergency Stop Assist**: keeps the lane and slows to a controlled stop with hazards on |
| After a crash | — | **Guardian**: crash detection → voice check-in → alerts contacts / 24/7 response center with location and crash data |
| Survives power loss | Device needs car power | **Guardian Reserve** backup cell keeps Guardian alive ~10 min |
| AI | Driving models | Driving models **plus** a language layer that talks to occupants and writes dispatcher-grade alerts. It never decides *whether* help is called. |
| Who it's for | Enthusiasts, developers | Families, long-distance commuters, older drivers, fleets, and enthusiasts |
| Revenue | Device + convenience subscription | Device + **safety subscription** + **fleet SaaS** + **insurance partnerships** |

The bet: **safety sells to a much larger market than convenience does**, and Guardian is
the trust layer that turns hands-free driving from a hobbyist upgrade into something a
parent buys for their teenager's car.

---

## 2. Teardown: the comma.ai model

*Source: comma.ai (home, shop, prime, vehicles, openpilot, jobs, setup pages) and github.com/commaai,
read November 2026. Figures are as published by the company.*

### 2.1 Products

| Item | Price | Notes |
|---|---|---|
| **comma four** (current device) | **$999** ($699 with trade-in of any comma device) | 3 cameras ("360° vision"), Snapdragon 845-class SoC, LTE + Wi-Fi, OLED display, CAN FD, high-precision GPS. Box: device, OBD-C cable, 2 mounts |
| Car harness | $99 | Vehicle-specific; plugs in at the factory lane-keep camera |
| Accessories | $20–$199 | Harness box/connector $50, OBD-C cable $20, power $20, mounts $20, prime SIM $20, red panda $99, panda jungle v2 $199, screen $100 |
| chestnut | from $249 | USB-to-PCIe adapter for a desktop GPU (adjacent ML/robotics product) |
| Custom car port service | $500,000 total ($50,000 down), 12 weeks | For pre-production or non-production vehicles; car supplied by customer |
| Merch | $35–$89 | Hoodie, beanie, t-shirt |

**Terms:** 30-day money-back trial ("love it or return it"), 1-year warranty, plus *commacare*
(up to one more year) when prime is started within 30 days and kept active.

### 2.2 Subscription: "comma prime"

| Tier | Price | Includes |
|---|---|---|
| Free | $0 | Core driving; 3 days of drive storage |
| **prime** | **$24/mo** (US & Puerto Rico, data included) | 1-year drive-video storage, 24/7 LTE, live GPS tracking, camera livestream, SSH, commacare |
| prime lite | $14/mo | Same without data; bring your own SIM; works internationally |

A subscription is explicitly *not required* for core driving. The 1-month trial is bundled
with a device. Prime is not transferable between devices.

### 2.3 The open-source core

| Repo | Stars | License | Role in the business |
|---|---|---|---|
| openpilot | ~64,000 | MIT | The product: "an operating system for robotics", driver assistance on 300+ cars |
| opendbc | ~3,600 | MIT | "A Python API for your car": the car-port database, i.e. the compatibility moat |
| panda | ~1,700 | MIT | CAN-interface firmware, including the safety model that bounds actuation |
| research, comma2k19, comma10k, commavq, comma-steering-control | 400–4,100 each | MIT/BSD | Public datasets that recruit researchers and build reputation |
| msgq, rednose, laika, minikeyvalue, miniray | 140–730 | MIT | Infrastructure (IPC, Kalman filters, GNSS, storage, distributed compute) |
| calib / speed / controls / compression challenges | 400–970 | — | Recruiting funnels |

### 2.4 How the machine works

- **Value proposition:** "hands-free driving for the car you already have"; "make driving chill".
  Lane centering, adaptive cruise, lane-change assist, camera-based driver monitoring ("no wheel nags").
- **Coverage:** "350+" models across 27 brands, installed in ~15 minutes, updated over the air.
- **Scale claims:** 300M+ miles, 20,000+ active users (openpilot page), 30,000+ cars (homepage),
  "#2 after Tesla in hands-free miles". These are the company's claims, and the numbers on different pages don't match.
- **Data flywheel:** every engaged mile is training data for the driving models. Public datasets
  (e.g. 100,000 minutes of compressed video; ~12,500 hours of steering data) build credibility.
- **Community as R&D:** 1,000+ contributors, bounties, hackathons (COMMA_HACK), and challenges.
  Volunteers port cars, which grows the addressable market at near-zero cost.
- **Talent engine:** challenge → two calls → paid micro-internship; on-site only in San Diego.
- **Positioning:** "If Tesla is the iOS of self driving, we are the Android."
- **Safety and regulatory posture:** the driver must stay alert and ready to take over at all times.
  Driver monitoring disengages the system when the driver is distracted. No regulatory approvals
  are claimed, and compliance (mounting laws, insurance) is left to the user.

### 2.5 Business model canvas (incumbent)

| Block | Content |
|---|---|
| Customer segments | Owners of compatible cars who like tech; developers and researchers |
| Value proposition | Best-in-class open-source L2 for existing cars at a one-time price |
| Channels | Direct-to-consumer web store, GitHub, Discord, word of mouth |
| Relationships | Community-led support, open development, trial with returns |
| Revenue | Device (~$999) + harness ($99) + optional prime ($14–24/mo) + accessories + rare custom ports |
| Key resources | Driving models and data, opendbc car database, hardware design, brand among builders |
| Key activities | ML training, hardware, car ports, safety firmware |
| Key partners | Open-source community; contract manufacturing; LTE carriers |
| Cost structure | Small, high-talent team; GPU compute; hardware inventory |

---

## 3. Where the incumbent model leaves room

1. **Nothing happens after the worst moment.** Based on the published feature list, prime is about
   convenience and connectivity (storage, livestream, SSH, GPS tracking). There is no crash
   detection, emergency notification or response service.
2. **Unresponsive driver = disengage.** Handing control back to someone who has stopped responding
   (asleep, having a seizure or a cardiac event) is the most dangerous moment in L2 driving.
3. **The device dies with the car's power,** which is exactly what often happens in a crash.
4. **Enthusiast positioning caps the market.** "Chill" driving appeals to builders. Peace of mind
   appeals to families, older drivers, fleet managers and insurers, a much larger group.
5. **No B2B.** Fleets pay for safety outcomes (fewer incidents, faster response, coaching), and
   insurers pay for verified safe driving. Neither is served.
6. **The subscription is an add-on, not essential.** Convenience features have weak retention.
   Safety coverage has strong retention: people don't cancel their safety net.

---

## 4. The Wayline model

**Mission:** *Make every car on the road a safer one — the car you already have.*

**Positioning:** *The AI copilot that keeps you in your lane — and calls for help when you can't.*

### 4.1 Strategy in one paragraph

Don't re-fight the open-source driving war; **join it**. The car-interface and driving
ecosystem is MIT-licensed, so Wayline builds on it for car coverage (hundreds of models on day
one) and contributes improvements upstream. Wayline competes where nobody else is: the
**safety layer** (Emergency Stop Assist + Guardian + a power-independent device) and the **service
business** around it (a 24/7 response center, fleets, insurers). The free tier includes real
safety features, because *we never paywall safety*. The paid tier sells connectivity and humans
on call.

### 4.2 Customer segments

| Segment | Job to be done | Buys |
|---|---|---|
| **Safety-first households** (parents of teen drivers, caregivers of older drivers, long commutes) | "If something happens, someone knows immediately, with location." | Wayline One + Plus |
| **Enthusiasts and developers** | "Best hands-free driving in my current car; let me hack on it." | Wayline One + Core (free) |
| **Small/medium fleets** (field service, delivery, rideshare drivers) | Fewer incidents, faster response, coaching, insurance leverage | Fleet plan |
| **Insurers** (partner channel) | Lower claims severity, verified-safe-driving discounts | Referral/revenue share; aggregated opt-in data |
| *Later:* **OEMs / Tier-1s** | An emergency layer for their own L2 systems | Guardian licensing |

### 4.3 Revenue streams

1. **Hardware**: Wayline One at a thin margin (adoption first).
2. **Wayline Plus**: recurring safety and connectivity subscription.
3. **Fleet SaaS**: per-vehicle per-month, with optional hardware leasing.
4. **Insurance partnerships**: referral fees and revenue share on discounted policies. Any data
   used is strictly opt-in, aggregated, and never sold per person.
5. **Accessories and services**: extra harnesses, mounts, professional installation network.
6. *Later:* **Guardian licensing** to OEMs / Tier-1s, and certified emergency-response APIs.

---

## 5. Products and pricing

| Product | Planned price | What it is |
|---|---|---|
| **Wayline One** | **$1,199**, car harness included | 3 forward cameras, IR driver-monitoring camera, 4-mic array + speaker, ±200 g IMU, dual-band GNSS, eSIM LTE, 3× CAN-FD, physical SOS button, OLED status display, **Guardian Reserve** backup cell. 30-day trial, 1-year warranty (+1 year on Plus) |
| **Core** | **$0 forever** | All Wayline OS driving features; Guardian Core (crash detection, unresponsive-driver stop, emergency-contact alerts via phone/Wi-Fi); 7-day drive storage |
| **Plus** | **$19/mo or $190/yr** | Built-in LTE; 24/7 human response center with emergency-services relay; roadside assistance dispatch; 1-year drive vault; live view and remote location; AI voice copilot; extended warranty |
| **Fleet** | **$39/vehicle/mo** (5+ vehicles) | Fleet dashboard, incident reports, driver coaching insights, API and webhooks, priority support. Hardware purchase or 36-month lease |

**Why $1,199 vs. the incumbent's $999:** the IR camera, microphone array, high-g IMU and backup
cell add real cost, and they are the hardware Guardian needs. The harness is included because a
surprise $99 add-on at checkout erodes trust.

**Why Plus is $19, not $24:** retention matters more than price per month. A safety subscription
priced below the incumbent's convenience subscription is easy to keep paying for.

---

## 6. Unit economics (illustrative)

*All numbers below are planning assumptions to be validated in Phase 1–2. They are not results.*

**Hardware (per unit)**

| Line | Assumption |
|---|---|
| Price (incl. harness) | $1,199 |
| Landed cost (BOM, assembly, test, harness, packaging, freight) | ~$880 |
| Returns / warranty reserve | ~5% of revenue |
| **Gross margin target** | **~25%** |

**Plus (per subscriber per month)**

| Line | Assumption |
|---|---|
| Revenue | $19.00 (or $15.83 on annual) |
| LTE data | $3.00 |
| Cloud storage and compute | $1.50 |
| Response-center capacity (amortized) | $2.50 |
| AI inference (incidents + voice copilot) | $1.00 |
| Payments, support, warranty extension | $1.50 |
| **Contribution** | **~$9.50 (~50%)** |

**Customer lifetime (blended, consumer)**

| Driver | Assumption |
|---|---|
| Plus attach rate | 40% of active devices |
| Plus lifetime | 36 months |
| Hardware gross profit | ~$300 |
| Plus contribution | 0.4 × $9.50 × 36 ≈ $137 |
| **LTV (gross profit)** | **≈ $437** |
| **CAC target** | **< $150** (community, referral, insurer channel) |

**Fleet:** $39/vehicle/month at ~70% contribution, hardware at cost or leased. A 50-vehicle
customer is ≈ $23k ARR.

Sensitivities to watch: Plus attach (each +10 pts ≈ +$34 LTV), response-center cost per incident,
false-alarm rate (it drives response-center load), hardware return rate.

---

## 7. The flywheel

```
     open-source core ──► community ports more cars ──► more compatible buyers
            ▲                                                   │
            │                                                   ▼
   better models ◄── more (opt-in) driving data ◄── more Wayline devices on the road
            │                                                   ▲
            ▼                                                   │
   Guardian proves value  ──►  insurers & fleets adopt  ──►  lower CAC, higher attach
   (time-to-alert, saved          (discounts, mandates)
    response minutes)
```

The incumbent flywheel is technology-led: data makes the models better. Wayline adds a
**trust-led loop**. Every verified Guardian response is evidence that insurers and fleet
managers can act on, and that brings in customers who would never have found us on GitHub.

---

## 8. Go-to-market and roadmap

| Phase | Goal | Milestones |
|---|---|---|
| **0: Reference implementation** (this repo) | Prove the architecture | Closed-loop simulator; lane assist; driver monitoring → Emergency Stop Assist; Guardian with AI language layer and deterministic fallbacks; 100+ tests |
| **1: Developer kit** | Real-car data, community | 100–300 units built on the open car-interface ecosystem; Guardian running on hardware with the backup cell; false-alarm and time-to-alert measured on real drives; upstream contributions |
| **2: Consumer launch (US)** | Product–market fit with households | Certified emergency-response partner; one insurer partner; professional install network; Plus at $19 |
| **3: Fleets and insurance** | B2B revenue | Fleet dashboard, incident API, coaching; insurer discount programs |
| **4: Scale** | New markets, licensing | EU (eCall-aware), Guardian licensing to OEMs / Tier-1s |

**Channels:** direct web store; GitHub/community (developers); insurers and fleet-management
platforms (B2B2C); driving schools and senior-mobility programs (high-trust referrals).

---

## 9. Competitive landscape

| Alternative | Strength | Gap Wayline fills |
|---|---|---|
| OEM hands-free systems | Deep integration | New cars only; usually a subscription per brand; nothing for the ~280M vehicles already on US roads |
| Open-source aftermarket ADAS | Great driving, big community | No emergency layer; disengages on an unresponsive driver; enthusiast positioning |
| Phone / watch crash detection | Already in pockets | No vehicle data (airbag, wheel speed), no driver monitoring, no stop-in-lane; depends on the phone surviving |
| Embedded telematics response services | Proven response centers | Tied to specific car brands; no driver assistance |
| Fleet dashcams | Fleet workflows | No driver assistance and no automatic emergency stop |

---

## 10. Metrics that matter

- **Safety:** Guardian false-alarm rate (target < 1 per 10,000 driving hours); time-to-alert
  (p95 < 15 s after a non-severe crash, < 8 s after a severe one); Emergency Stop Assist activations
  and outcomes; lane-centering interventions per 100 km.
- **Product:** engaged-distance share; supported-model coverage; OTA adoption.
- **Business:** Plus attach and 12-month retention; fleet logo and vehicle growth; CAC by channel;
  hardware return rate; response-center cost per incident.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Regulatory status of aftermarket L2** | Position strictly as supervised driver assistance; strong driver monitoring; work with counsel on crash-reporting obligations for driver-assistance systems and state mounting laws |
| **Emergency-call regulation** (automated or pre-recorded calls to emergency numbers are restricted in many places) | Never auto-dial emergency numbers from the device; the code refuses it. Use certified response-center and emergency-data partners; in the EU, align with eCall standards |
| **Liability** | Product liability insurance; conservative safety gate on a separate MCU; transparent logging; clear "hands-off, eyes-on" UX; no "self-driving" language |
| **Carmakers lock down their networks** (CAN authentication) | Diversify across brands; partner programs; Guardian works without any car integration (IMU + GPS + cabin audio) |
| **False alarms** annoy users and load the response center | Multi-signal crash detection with wheel-speed corroboration; voice check-in with cancellation; measure and publish the false-alarm rate |
| **AI errors in an emergency** | AI never decides whether help is called; deterministic escalation; keyword veto on cancellations; validated AI output with a template fallback; the model never sees raw coordinates |
| **Privacy** | On-device processing; no cloud speech outside active incidents; opt-in data sharing; users own and can delete their drives |
| **Dependence on an upstream open-source project** | Maintain a fork; contribute upstream; keep Guardian independent of the driving stack |

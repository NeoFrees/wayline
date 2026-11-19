# Wayline One hardware

The hardware package for **Wayline One**, the windshield-mounted device that runs Wayline OS and Guardian.

> Concept stage (Rev A, pre-EVT). Part numbers are candidates with alternates; costs are budgetary.
> Not certified for road use.

| Document | What's in it |
|---|---|
| [BLUEPRINT.md](BLUEPRINT.md) | Requirements, system architecture ("three brains"), compute, sensors, connectivity, power and the **Guardian Reserve** sizing, harness, mechanical, thermal, PCBs, firmware partitioning, safety and security, certifications, cost summary |
| [BUILD_GUIDE.md](BUILD_GUIDE.md) | How to make it: dev-kit bench prototype → EVT → DVT → PVT → mass production, with checklists, bring-up steps, test plans, factory stations and the team you need |
| [MANUFACTURING.md](MANUFACTURING.md) | Where to make it: candidate partners by category and region, how to run the RFQ, contract essentials, one-time costs, timeline, quality system |
| [bom/wayline-one-bom.csv](bom/wayline-one-bom.csv) | Line-item bill of materials with candidate parts, alternates, and 1k / 10k unit costs |
| [drawings/](drawings/) | Engineering drawings (orthographic views, exploded view, system block diagram, power tree, harness) |

**At a glance:** 152 × 74 × 38 mm · ≤ 320 g · QCS6490-class SoM + lockstep Safety Gate MCU + always-on Guardian MCU ·
3× AR0233AT road cameras + 940 nm IR driver camera · ±200 g IMU · LTE Cat 4 eSIM + L1/L5 GNSS · 3× CAN-FD ·
Guardian Reserve ≈ 2.4 kJ (≈ 11–16 min after power loss) · landed cost ≈ $1,066 @1k → ≈ $751 @10k ·
one-time costs ≈ $0.55–1.15M · ~15 months from bench to mass production.

The software that runs on it is in [`../wayline`](../wayline). The reference behaviour the firmware must match
is covered by the tests in [`../tests`](../tests).

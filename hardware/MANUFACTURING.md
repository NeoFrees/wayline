# Wayline One: Where and How It Gets Manufactured

> **Partner names below are candidates to request quotes from.** They are well-known companies in each
> category. Wayline has no affiliation with any of them, and listing them is not an endorsement. Before
> committing, verify current capabilities, certifications (ISO 9001 / **IATF 16949** for automotive),
> capacity and references, and get competing quotes.

**Contents**
1. [Strategy at a glance](#1-strategy-at-a-glance)
2. [Partner directory by category](#2-partner-directory-by-category)
3. [Choosing a region](#3-choosing-a-region)
4. [Running the RFQ](#4-running-the-rfq)
5. [Contract essentials](#5-contract-essentials)
6. [Cost, NRE and timeline](#cost-nre-and-timeline)
7. [Quality system](#7-quality-system)

---

## 1. Strategy at a glance

| Phase | Volume | Who builds it | Why |
|---|---|---|---|
| A: Bench | 1–5 rigs | You, from dev kits | Speed; no NRE |
| B: EVT | 20–50 | **Quick-turn PCBA** + rapid-prototype mechanics | Days-to-weeks turns, low minimums |
| C: DVT | 150–300 | **The production EMS** you selected, on soft/production tooling | Find manufacturing problems early, on the real line |
| D: PVT | 500–1,000 | Production EMS, full line + fixtures | Prove yield, test coverage, throughput |
| E: MP | 1k–10k+/month | Production EMS (+ second source later) | Cost, quality, capacity |

**Recommendation:** use a mid-size, **IATF 16949-certified EMS** that does box build, has a site in **Mexico or
Southeast Asia** for the US market, and will take a sub-10k/yr program seriously. Keep camera modules with a
specialist camera-module supplier, who ships active-aligned, tested modules to the EMS.

---

## 2. Partner directory by category

### Prototype PCBs and assembly (EVT)

| Company | Region | Good for |
|---|---|---|
| JLCPCB | China | Very low cost, fast; harness-box and cabin boards; check HDI limits for the main board |
| PCBWay | China | PCB + assembly + cable/harness assembly; HDI options |
| Seeed Studio Fusion | China | PCBA and small-batch "agile manufacturing" |
| MacroFab | USA | US-based PCBA, a platform that scales from prototype to low-volume production |
| Sierra Circuits / ProtoExpress | USA | HDI / high-layer-count quick-turn, strong DFM support |
| Advanced Circuits | USA | Quick-turn bare boards |
| Eurocircuits, Aisler | EU | European prototype PCBs/PCBA |

### Volume EMS with automotive capability (DVT → MP)

| Company | Footprint (examples) | Notes |
|---|---|---|
| Kimball Electronics | USA, Mexico, China, Poland, Thailand | Long automotive heritage; mid-volume friendly |
| SigmaTron International | USA, Mexico, China, Vietnam | Mid-size; Mexico for US-bound product |
| Benchmark Electronics | USA, Mexico, Asia, Europe | Complex box build, engineering services |
| Plexus | USA, Mexico, Malaysia, Europe | Product realization, regulated markets |
| Creation Technologies | North America | Low-to-mid volume, high mix |
| Nortech Systems | USA, Mexico, China | Includes wire/cable assemblies |
| Zollner Elektronik | Germany, Europe, Asia | Strong automotive; for EU-market production |
| Kitron, Scanfil | Nordics, Baltics, Poland, Asia | European mid-size EMS |
| Venture Corporation | Singapore, Malaysia | Box build, design services |
| Jabil, Flex, Celestica, Sanmina | Global | Tier-1 scale. Consider once volumes are in the hundreds of thousands |

### Camera modules and optics

| Company | Role |
|---|---|
| Leopard Imaging | Automotive camera modules (onsemi/Sony sensors), customization, calibration |
| e-con Systems | Custom MIPI camera modules, ISP tuning support |
| Sunny Optical | High-volume camera modules and lenses |
| Arducam | Low-cost modules for EVT/bench work |
| Sunex, Evetar, Lensation | M12 / automotive lenses and lens selection |

### Enclosures: prototypes, molds, die-casting

| Company | Good for |
|---|---|
| Protolabs | SLS/MJF prints, CNC, rapid injection-mold tooling (US/EU/JP) |
| Xometry | Marketplace for CNC, molding and die-casting quotes |
| Fictiv | Managed sourcing for CNC/molding with DFM support |
| RapidDirect, HLH Prototypes, Star Rapid | China-based CNC, vacuum casting, injection-mold tooling, die-casting |
| JLC3DP / PCBWay 3D printing | Low-cost prints for fit checks |

At DVT, move to a dedicated molder and die-caster near the EMS. Ship steel tools to the region where the box build happens.

### Harnesses, connectors and cables

- **Connectors:** Molex, TE Connectivity, Amphenol, JAE, Hirose (board-to-board), plus OEM-compatible camera
  connectors per car family (often from the same makers; confirm part numbers from vehicle service data).
- **Prototype harnesses:** build in-house with the connector maker's crimp tools, or use quick-turn cable shops
  (e.g. PCBWay cable assembly).
- **Volume harnesses:** harness assemblers certified to **IPC/WHMA-A-620 Class 3**, typically in Mexico or China.
  Your EMS may build them or subcontract. Tier-1 harness makers (Yazaki, Sumitomo Electric, Aptiv, Lear) only
  make sense at OEM-scale volumes.

### Key components (buy through authorized channels only)

| Category | Source |
|---|---|
| Semiconductors and passives | Digi-Key, Mouser, Arrow, Avnet, Future Electronics, WPG/WT (Asia); use Octopart to compare stock |
| SoM | Direct from the SoM vendor (e.g. Thundercomm) or an authorized distributor; negotiate a longevity commitment |
| LTE module | Quectel via authorized distributors; carrier certification support from Quectel |
| eSIM / connectivity | eUICC from Thales, G+D or Kigen; IoT connectivity plans from KORE, Hologram, emnify or 1NCE |
| Guardian Reserve cells | Musashi Energy Solutions (hybrid supercapacitors), Eaton (HS/HSL), Vinatech |
| Fans / thermal | Sunon, Delta, Nidec; Henkel Bergquist, Laird, Fujipoly gap pads |
| Adhesive mount | 3M (VHB 5952 / 4229P) via 3M converters who die-cut to shape |

> Avoid broker or grey-market parts for anything in the safety or Guardian path. Counterfeits are a real
> risk during shortages.

### Compliance and certification labs

| Lab | Typical scope |
|---|---|
| UL Solutions | Product safety (62368-1), EMC, wireless |
| TÜV SÜD, TÜV Rheinland | Automotive EMC (CISPR 25, ISO 11452), ISO 16750, E-mark (UN ECE R10), functional-safety assessments |
| Intertek, SGS, Bureau Veritas (incl. 7layers) | EMC, RF (FCC/ISED/RED), environmental, cellular (PTCRB) |
| Element Materials Technology | RF/cellular certification, environmental and mechanical testing |

### Services Guardian needs to operate

| Need | Candidate partners |
|---|---|
| 24/7 human response center with emergency-services relay | Specialized safety-monitoring providers (e.g. Noonlight) |
| Emergency data delivery to 911 centers | RapidSOS, Intrado |
| Roadside assistance dispatch | Agero, Urgently |

---

## 3. Choosing a region

| Region | Pros | Watch out for |
|---|---|---|
| **China** (Shenzhen, Dongguan) | Fastest iteration, deepest component and tooling ecosystem, lowest prototype cost | US tariffs on China-origin electronics are high and change often; IP protection |
| **Mexico** (Guadalajara, Monterrey, Juárez, Tijuana) | Near-shore for the US, USMCA treatment when origin rules are met, large automotive EMS clusters | Component supply still largely from Asia; plan logistics |
| **Southeast Asia** (Vietnam, Malaysia, Thailand) | Tariff diversification, mature EMS base | Longer ramp for new suppliers; rules-of-origin depth |
| **USA** | Prototypes, final assembly / test / calibration, "assembled in USA" options | Highest labour cost |
| **Central / Northern Europe** | Automotive-grade EMS for the EU market, E-mark expertise | Cost; energy prices |

**Practical plan:** EVT in China or the US (speed). DVT → MP at an IATF 16949 EMS in **Mexico** for the US
market, with a **Malaysia/Vietnam** site as the second source. Get a licensed customs broker to confirm
classification and duties before you commit, because the tariff line in the BOM is an allowance, not advice.

---

## 4. Running the RFQ

**Send to 3–5 candidates under NDA:**

- [ ] Gerber X2 / ODB++ / IPC-2581, drill files, stack-up and impedance table
- [ ] BOM with an approved vendor list (AVL) and alternates: [`bom/wayline-one-bom.csv`](bom/wayline-one-bom.csv)
- [ ] Pick-and-place (centroid) files, assembly drawings, conformal-coating map (harness box)
- [ ] 3D STEP of the assembly + 2D drawings (`drawings/`), cosmetic spec (texture, colour, A/B surfaces)
- [ ] Test specification (stations and limits from BUILD_GUIDE §D1) and who supplies the fixtures
- [ ] Forecast: EAU (estimated annual usage) per year for 3 years, plus pilot quantities
- [ ] Quality requirements: IATF 16949, IPC classes, traceability, PPAP-lite deliverables
- [ ] Packaging and labelling spec; ship-to regions

**Score the responses (weights are a starting point):**

| Criterion | Weight |
|---|---|
| Unit cost at 1k / 5k / 10k (turnkey) | 25% |
| Engineering support (DFM, test development, NPI team) | 20% |
| Automotive quality system and audit result | 20% |
| Supply-chain strength (component buying power, shortage handling) | 15% |
| Location, tariffs and logistics to the target market | 10% |
| Appetite for a startup program (you will be small) | 10% |

Visit the shortlisted factories in person before awarding. Run an audit with a checklist based on IATF 16949.

---

## 5. Contract essentials

- **NDA** before sharing design files. **MSA** (manufacturing services agreement) and a **quality agreement**.
- **You own the tooling** (molds, die-cast tools, fixtures) and the design IP. Tools are tagged, and you control their transfer.
- **Turnkey vs. consigned:** turnkey (the EMS buys parts) at volume; consign the SoM and image sensors early if you hold allocation.
- **Pricing:** volume breaks, a component cost-pass-through formula, and quarterly price reviews.
- **Inventory risk:** NCNR (non-cancellable, non-returnable) parts and excess and obsolescence (E&O) liability caps. These matter for long-lead parts.
- **Lead times and buffers:** 16–26 weeks for the SoM, modem and image sensors. Agree buffer stock levels.
- **Warranty, RMA and failure analysis** turnaround; epidemic-failure clause.
- **Audit rights**, change notification (no part or process change without your approval), and second-source rights.

---

## Cost, NRE and timeline

### Unit cost (from the BOM)

| Volume | Landed cost / unit | Gross margin at $1,199 |
|---|---|---|
| 1k units/yr | ≈ $1,066 | ≈ 11% |
| 3–5k units/yr | ≈ $880–900 | ≈ 25% (business-plan target) |
| 10k units/yr | ≈ $751 | ≈ 37% |

### One-time costs (budgetary)

| Item | Low | High |
|---|---|---|
| Industrial + mechanical design (incl. contract) | $60k | $120k |
| PCB layout and electrical design services | $40k | $80k |
| Injection-mold tooling (shell, hood, light pipe, button cap) | $45k | $90k |
| Die-cast tool + trim die (rear frame) | $25k | $45k |
| Camera-module NRE (lens selection, active-alignment setup, calibration) | $30k | $80k |
| Test fixtures and calibration stations | $40k | $80k |
| Certification and compliance testing (all of BLUEPRINT §13) | $180k | $350k |
| Harness tooling, ~$5–15k per car family × 10 families | $50k | $150k |
| EVT/DVT builds (units, expedites, samples) | $80k | $150k |
| **Total** | **≈ $550k** | **≈ $1.15M** |

Plus working capital: long-lead components for the first 3–6 months of production are usually paid up front or on short terms.

### Timeline

```
Month:      0    2    4    6    8   10   12   14   16
Phase A   ████
EVT            ████████
DVT                     ██████████
 tooling             ██████
 certify                    ███████
PVT                                   ██████
MP                                            ███████▶
Long-lead orders  ▲(EVT)        ▲(DVT)    ▲(PVT/MP)
```

---

## 7. Quality system

| Stage | Control |
|---|---|
| Incoming (IQC) | Sampling inspection; certificates of conformance; counterfeit screening for safety-path parts |
| SMT | SPI (solder-paste inspection), AOI, X-ray on BGA/LGA, reflow profiling records |
| Electrical test | ICT / flying probe, then full functional test (BUILD_GUIDE §D1) |
| Calibration | Per-unit camera and IMU calibration stored with the serial; Cpk tracked |
| Burn-in | 4 h thermal soak with stress pattern; failures go to failure analysis |
| Outgoing | Out-of-box audit (OBA) sampling; cosmetic inspection to the A/B surface spec |
| Traceability | Unit serial ↔ PCB serials ↔ component lot codes ↔ test results ↔ firmware version |
| Field | RMA intake, failure analysis with 8D reports, field-return Pareto feeding engineering changes |

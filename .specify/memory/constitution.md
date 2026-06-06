# Project Constitution

## What This Is

An integrated CO₂ Huff-and-Puff (HnP) CCUS screening and planning framework for
Jatibarang-class Indonesian fractured carbonate reservoirs. The framework lets an
engineering team plan a CO₂ HnP-CCUS development as a single coupled exercise —
subsurface response, CO₂ supply logistics, surface facility sizing, and economics —
instead of four disconnected silos.

The core technical enabler is a pre-trained spatiotemporal surrogate (ED-ConvLSTM)
that predicts CO₂ plume evolution and production in seconds, making it feasible to
screen hundreds of scenarios and run the economics across multiple carbon-price
scenarios where full compositional simulation could only afford a handful.

## Deliverables

This project produces two coupled artifacts:

1. **A technical paper** for **APECX 2026**, hosted by **SPE UGM SC** (Society of
   Petroleum Engineers, Universitas Gadjah Mada Student Chapter). Case study:
   Jatibarang field, West Java, Indonesia.
2. **A live demo application** — a screening tool used during the presentation to
   show the framework running end-to-end (geology input → screened scenarios →
   pipeline route → facility sizing → economics) in minutes, interactively.

The software is both the paper's methodology in executable form and the
presentation's centerpiece. Build decisions should serve both.

## The Four Modules

| Module | Name | Role | Runtime engine |
|---|---|---|---|
| 1 | Pipeline & Logistics Optimizer | CO₂ supply routing, diameter, boosters | CoolProp + graph search |
| 2 | Subsurface Surrogate | Plume + production prediction (inference only) | PyTorch (pre-trained) |
| 3 | Surface Facility Cost Model | Compression, separation, injection sizing | CoolProp + cost correlations |
| 4 | Economic Engine | NPV under Indonesian carbon regulation | NumPy |

Runtime data flow (NOT build order): **Module 2 → Module 1 → Module 3 → Module 4.**
Module 2 screening produces the CO₂ demand profile that Module 1 needs and the
injection rate that Module 3 needs. Module 4 is terminal — all paths lead there.

## Architecture Rules

- Backend: Python 3.11+, FastAPI.
- Frontend: Next.js 14+ with TypeScript.
- Surrogate: PyTorch, CPU inference only, checkpoint loaded once at startup.
- CO₂ thermodynamics: **CoolProp only at runtime.** No DWSIM, no MATLAB, no .NET,
  no external process calls during screening.
- Economics: NumPy, vectorized. No Excel/spreadsheet dependencies.
- All inter-module communication uses typed Pydantic models. Interface contracts
  are fixed before implementation (define the schemas, then build).
- Every module must be independently runnable and independently testable.
- The whole stack must install from `pip install` + `npm install`. No runtime
  dependency that can crash on a presentation laptop.

## Data Constraints (from the surrogate's training distribution)

The surrogate was trained on a literature-informed, Jatibarang-anchored fractured-HnP
proxy dataset. Predictions are only trustworthy inside these ranges:

| Quantity | Trained range |
|---|---|
| Grid | 64 × 64 × 1 |
| Porosity (mean sample) | 0.17–0.22 |
| Porosity (facies, clipped) | 0.14–0.25 |
| Matrix permeability (pre-multiplier) | 10–114 mD |
| Effective permeability (post-fracture clip) | 10–4000 mD |
| Injection rate | 8,000–10,000 m³/day eq. |
| Soak duration | 25–35 days |
| Production duration | 170–210 days |
| Production BHP | 650–700 psi |
| Cycles | 3–4 |
| Pressure cap | 2,000 psi |

**Any input outside these ranges is EXTRAPOLATION and must be flagged in the API
response and surfaced in the UI.** The framework never silently extrapolates.

The matrix rock/PVT anchors (carbonate/shale, porosity ~16–23%, permeability
~15–114 mD, reservoir pressure ~750 psi, temperature ~91 °C, 2,000 psi pressure cap)
trace to Jatibarang literature. Fracture-stimulated effective permeability may exceed
the matrix range by design — the dataset is a training-oriented literature-aligned
fractured-HnP proxy, **not** a proprietary Jatibarang geomodel or a pilot-faithful
reproduction of the 2022 pilot. Documentation and the paper must state this honestly.

## Physics Non-Negotiables

- CO₂ operating conditions sit near the critical point (31 °C, 73.8 bar). Always use
  CoolProp real-gas properties. Ideal-gas assumptions are forbidden anywhere CO₂
  thermodynamics matter (compression work, pipeline density, injection volume).
- Dense-phase CO₂ pipeline transport requires pressure above ~80 bar everywhere along
  the route. Dropping below risks two-phase flow — unacceptable. Boosters exist to
  prevent this.
- Net CO₂ stored = CO₂ injected − CO₂ produced back. This drives carbon-credit
  revenue and must be derived consistently from the surrogate's outputs (see Module 4
  spec for the mass-balance handling and its known limitation).

## Honesty Rules (apply to code, docs, and paper)

- The surrogate is the engine, not the product. The product is the integrated
  framework. Do not oversell the surrogate's standalone novelty.
- Report the surrogate's limitations explicitly: rollout error accumulation, the
  soak→produce transition behavior, and CO₂ mass error. Propagate these as
  uncertainty bands into the economic results rather than reporting point estimates
  as certainties.
- Modules 1 and 3 are intentionally lean (parametric / correlation-based). The
  novelty is the *coupling* across domains and the Indonesian carbon-regulation
  economics, not state-of-the-art depth in any single module.
- The comparison story is: naive strategy vs. limited-simulation optimization vs.
  surrogate-enabled integrated screening. The headline result is how NPV — and the
  *ranking* of scenarios — shifts across carbon-price scenarios.

## Out of Scope (for this project)

- Retraining or modifying the surrogate. It is consumed as a frozen checkpoint.
- Full MILP pipeline-network optimization (single-source-to-sink routing is enough).
- Dynamic DWSIM-in-the-loop. DWSIM is used offline to validate the facility
  correlations only.
- Real-time MRST coupling. MRST is the offline ground truth for the paper.

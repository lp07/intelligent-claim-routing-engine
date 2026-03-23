# Intelligent Claim Routing Engine

A production-grade, multi-factor denial risk scoring and queue assignment engine for healthcare revenue cycle operations. Takes validated EDI 837 claims (from the [Healthcare Claims DQ Platform](https://github.com/lp07/Healthcare-Claims-Data-Quality-Intelligent-Platform)) and routes each claim to the correct operational queue based on a transparent, auditable 0–100 risk score.

Built on real RCM operational patterns — specifically the claim prioritization and skills-based routing logic used by production billing operations systems.

---

## The Problem This Solves

A validated claims report tells you which claims have errors. It does not tell you:

- Which claims need to be worked **today** vs. next week
- Which claims need a **senior coder** vs. a standard billing rep
- Which claims need **manager escalation** before any action is taken
- Which claims are about to **expire** their timely filing window

This engine answers all four questions — for every claim, every run.

---

## How It Connects to Project 1

This is **Project 2** in a three-part RCM data pipeline:

```
Project 1 → Validate claims before submission
      ↓ (output CSV feeds directly into Project 2)
Project 2 → Score denial risk, assign queues, generate action worklist (this repo)
      ↓
Project 3 → Reconcile 835 remittance payments, feed denial patterns back to Project 1
```

The `--input` flag accepts the exact CSV output from Project 1 with zero transformation required.

---

## Architecture

```
┌──────────────────────────────┐
│  Input: Validated Claims CSV  │  ← Project 1 output (status, error codes, revenue at risk)
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│     DenialRiskScorer          │  ← 7-factor weighted model → score 0–100
│                               │
│  • Validation status   40 pts │
│  • Critical errors     20 pts │
│  • Payer risk weight   10 pts │
│  • Timely filing       15 pts │
│  • Dollar value         5 pts │
│  • CPT procedure risk   5 pts │
│  • Warning errors       5 pts │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       ClaimRouter             │  ← Score → Queue + Action Recommendation
│                               │
│  Score 0–20  → AUTO_PROCESS   │
│  Score 21–45 → REVIEW         │
│  Score 46–70 → HOLD           │
│  Score 71+   → REJECT         │
│  Score 46+ AND $2K+ → ESCALATE│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      RoutingReporter          │  ← 3 output files
│                               │
│  • routed_claims.csv          │  ← Full claim-level detail
│  • action_worklist.csv        │  ← Priority-sorted billing team worklist
│  • queue_summary.json         │  ← Operations dashboard KPIs
└──────────────────────────────┘
```

---

## The Five Queues

| Queue | Score | Escalation | Avg Score | Action | Turnaround |
|-------|-------|-----------|-----------|--------|-----------|
| AUTO_PROCESS | 0–20 | — | 13.0 | Submit immediately | 2 hours |
| REVIEW | 21–45 | — | 29.8 | Billing team review | 24 hours |
| HOLD | 46–70 | — | 61.0 | Senior coder correction | 48 hours |
| ESCALATE | ≥46 + $2K+ | Dollar override | 68.0 | RCM manager decision | 4 hours |
| REJECT | 71–100 | — | 76.8 | Appeal or write-off | 72 hours |

---

## Risk Scoring — 7 Factors

| Factor | Max Points | Logic |
|--------|-----------|-------|
| Validation status | 40 | REJECTED=40, FLAGGED=20, VALID=0 |
| Critical error count | 20 | ×7 per error, capped at 20 |
| Payer risk weight | 10 | Cigna=10, Aetna=8, BCBS/Humana=5, Medicare=4 |
| Timely filing urgency | 15 | ≤10 days=15, ≤30 days=8, ≤60 days=3 |
| Dollar value | 5 | ≥$2,000=5, ≥$1,000=3 |
| CPT procedure risk | 5 | Prior-auth, bundling, frequency-limit codes |
| Warning error count | 5 | ×2 per warning, capped at 5 |

All score weights and thresholds are defined in `routing_configs/` JSON files — updatable without code changes.

---

## Sample Run Results

1,200 validated claims routed in 0.17 seconds:

```
=================================================================
  INTELLIGENT CLAIM ROUTING — QUEUE SUMMARY
=================================================================
  Total Claims:     1,200
  Total Billed:     $3,419,569.88
  Avg Risk Score:   38.3

  QUEUE DISTRIBUTION:
    AUTO_PROCESS      429 claims ( 35.8%)  $1,221,908.07  avg score: 13.0
    REVIEW            304 claims ( 25.3%)  $  874,959.77  avg score: 29.8
    HOLD              119 claims (  9.9%)  $  128,914.68  avg score: 61.0
    ESCALATE          299 claims ( 24.9%)  $1,134,808.53  avg score: 68.0
    REJECT             49 claims (  4.1%)  $   58,978.83  avg score: 76.8

  RISK LEVEL DISTRIBUTION:
    LOW           429 claims ( 35.8%)
    MEDIUM        304 claims ( 25.3%)
    HIGH          324 claims ( 27.0%)
    CRITICAL      143 claims ( 11.9%)
=================================================================
```

**234 timely filing urgency alerts** fired — claims within 10–30 days of payer deadline.

---

## Project Structure

```
intelligent-claim-routing-engine/
│
├── routing_engine/
│   ├── __init__.py        # Package exports
│   ├── models.py          # RoutingResult, RiskScoreBreakdown, QueueType, ActionRecommendation
│   ├── scorer.py          # 7-factor denial risk scorer (0–100)
│   ├── router.py          # Queue assignment + action recommendation engine
│   └── reporter.py        # 3-format output generation
│
├── routing_configs/
│   ├── payer_risk.json    # Payer risk weights + timely filing windows
│   ├── thresholds.json    # Queue score thresholds + escalation rules
│   └── cpt_risk.json      # High-risk CPT codes by denial category
│
├── data/
│   ├── generate_sample_data.py    # Synthetic Project 1 output generator
│   └── sample_output/             # Routing reports + analysis
│
├── tests/
│   └── test_scoring.py    # 22 unit tests across all scoring factors
│
├── main.py                # CLI entry point
└── requirements.txt
```

---

## Tech Stack and Why

| Technology | Why Used |
|------------|----------|
| **Python** | Industry standard for RCM data pipelines |
| **Pandas** | Batch processing of 1,200+ claims in under 0.2 seconds |
| **Dataclasses** | Typed, auditable data models — RiskScoreBreakdown shows every factor |
| **Enums** | Type-safe queue and action types — no string typos in production |
| **JSON configs** | All weights and thresholds updatable without code changes |
| **pytest** | 22 unit tests covering every scoring factor and queue assignment |

---

## How to Run

```bash
# Clone and set up
git clone https://github.com/lp07/intelligent-claim-routing-engine.git
cd intelligent-claim-routing-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Generate sample data and route
python main.py --generate

# Route Project 1 output directly
python main.py --input ../healthcare-claims-dq-platform/data/sample_output/sample_validation_report.csv

# Run tests
python -m pytest tests/test_scoring.py -v
```

---

## Design Decisions

**Why a numeric score instead of rule-based routing:**
Binary rules (pass/fail) cannot differentiate between a $4,500 Cigna claim expiring in 8 days vs. a $150 Medicare claim with the same errors. A score gives the billing team a spectrum — they can prioritize within queues, not just between them. This mirrors how production RCM systems like PracticeSuite's Rank KPI Workqueue and AnnexMed's intelligent workflows operate.

**Why escalation is a separate queue from HOLD/REJECT:**
Dollar value changes *who* needs to act, not just *what* needs to happen. A senior coder can fix a $150 rejected claim. A $3,500 rejected claim needs a manager to decide: appeal investment vs. write-off vs. emergency correction. Conflating these into one queue creates operational bottlenecks.

**Why CPT risk is a scoring factor:**
Prior authorization requirements, bundling rules, and frequency limits are CPT-code-specific. A claim for CPT 27447 (total knee arthroplasty) without a prior auth number is heading toward denial regardless of how clean every other field is. Capturing this at the routing stage prevents billing teams from wasting time submitting claims that will return denied for clinical reasons.

**Why config-driven thresholds:**
Business needs change. An organization may want to lower the AUTO_PROCESS ceiling from score 20 to score 15 after a period of high denial rates. Or raise the escalation dollar threshold from $2,000 to $3,000. These are JSON edits — not code releases.

---

## Extending the Engine

**Adjust queue thresholds:**
Edit `routing_configs/thresholds.json` — change `max_score` values per queue.

**Update payer risk weights:**
Edit `routing_configs/payer_risk.json` — change `weights` for any payer.

**Add a new CPT risk category:**
Edit `routing_configs/cpt_risk.json` — add codes to existing category or create a new one.

**Add a new scoring factor:**
1. Add a `_score_[factor]` method to `DenialRiskScorer` in `scorer.py`
2. Add a field to `RiskScoreBreakdown` in `models.py`
3. Call it in the `score()` method
4. Write a test in `tests/test_scoring.py`

---

## Part of a Three-Project RCM Pipeline

| Project | Repo | What It Does |
|---------|------|-------------|
| 1 — Claims DQ Platform | [Healthcare-Claims-Data-Quality-Intelligent-Platform](https://github.com/lp07/Healthcare-Claims-Data-Quality-Intelligent-Platform) | Pre-submission EDI 837 validation |
| 2 — Routing Engine | This repo | Denial risk scoring and queue assignment |
| 3 — Remittance Reconciliation | Coming | 835/837 matching + denial feedback loop |

---

*All data is synthetically generated. No real patient, provider, or payer data is used.*

MIT License — Copyright (c) 2026 Lisa Patel

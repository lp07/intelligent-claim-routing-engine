# Intelligent Claim Routing Engine — Analysis

**Run Date:** 2026-03-23
**Engine:** Intelligent Claim Routing Engine
**Input:** 1,200 validated claims (Project 1 output format)
**Processing Time:** 0.17 seconds

---

## Executive Summary

1,200 validated claims were scored and routed across five operational queues using a multi-factor denial risk scoring model. **429 claims (35.8%) were cleared for immediate submission** with no human intervention required. **771 claims (64.2%) required some form of human action** — ranging from billing team review to manager escalation.

**$1,134,808.53 in high-risk claims were escalated** to RCM manager queue — representing the highest-value, highest-risk subset requiring senior decision-making before any action is taken.

**234 claims received timely filing urgency alerts** — meaning they are within critical or warning range of their payer's filing deadline and require same-day or same-week action regardless of other priorities.

---

## Queue Distribution

| Queue | Claims | % of Total | Total Billed | Avg Risk Score | Action Required |
|-------|--------|-----------|-------------|----------------|----------------|
| AUTO_PROCESS | 429 | 35.8% | $1,221,908.07 | 13.0 | Submit immediately |
| REVIEW | 304 | 25.3% | $874,959.77 | 29.8 | Billing team review |
| HOLD | 119 | 9.9% | $128,914.68 | 61.0 | Senior coder correction |
| ESCALATE | 299 | 24.9% | $1,134,808.53 | 68.0 | RCM manager decision |
| REJECT | 49 | 4.1% | $58,978.83 | 76.8 | Appeal or write-off |
| **TOTAL** | **1,200** | **100%** | **$3,419,569.88** | **38.3** | |

---

## Risk Score Distribution

| Risk Level | Score Range | Claims | % of Total |
|-----------|-------------|--------|-----------|
| LOW | 0–20 | 429 | 35.8% |
| MEDIUM | 21–45 | 304 | 25.3% |
| HIGH | 46–70 | 324 | 27.0% |
| CRITICAL | 71–100 | 143 | 11.9% |

**35.8% of claims are low risk** — these are the first-pass yield. AUTO_PROCESS claims require zero human intervention and can be submitted in bulk immediately after routing.

**11.9% of claims are CRITICAL risk** — these are the claims most likely to be denied if submitted as-is. They carry the highest combination of validation errors, payer risk, and/or timely filing urgency.

---

## Action Worklist Distribution

The action worklist is the primary operational output — sorted by priority and due date for billing team use.

| Action | Count | Description |
|--------|-------|-------------|
| SUBMIT_IMMEDIATELY | 429 | No correction needed — submit now |
| CORRECT_AND_RESUBMIT | 304 | Fix flagged fields, resubmit within 5 days |
| MANAGER_ESCALATION | 299 | High-value + high-risk — manager decision required |
| SENIOR_CODER_REVIEW | 119 | Critical errors — senior coder correction before submission |
| APPEAL | 37 | Denial likely unrecoverable — evaluate appeal options |
| WRITE_OFF | 12 | Timely filing exceeded — initiate write-off process |

---

## Timely Filing Urgency Analysis

**234 claims (19.5%) received timely filing urgency alerts.**

These claims are within the critical (≤10 days) or warning (≤30 days) range of their payer's timely filing deadline. Timely filing denials are the most financially damaging category — once the window closes, the revenue is permanently lost regardless of clinical validity.

| Alert Level | Days Remaining | Points Added | Operational Priority |
|------------|----------------|-------------|---------------------|
| CRITICAL | ≤10 days | +15 pts | Act today — same-day submission or escalation |
| WARNING | ≤30 days | +8 pts | Act this week |
| APPROACHING | ≤60 days | +3 pts | Schedule review |

**Why Cigna drives most timely filing urgency:**
Cigna's 90-day filing window is the strictest among the 5 payers in this dataset. A claim submitted 85 days after DOS has only 5 days remaining — the same claim against BCBS or Medicare would have 280+ days remaining. This disparity is reflected in the scoring: Cigna claims score 10 points for payer risk weight plus up to 15 points for timely filing urgency — a combined 25-point floor before any validation errors are factored in.

---

## ESCALATE Queue Deep Dive

299 claims were escalated to the RCM manager queue — the most operationally significant segment.

**Escalation criteria:** Risk score ≥46 AND billed amount ≥$2,000

**Escalation by payer:**

| Payer | Escalated Claims | % of Payer's Total |
|-------|-----------------|-------------------|
| AETNA | 66 | 29.6% |
| CIGNA | 65 | 28.1% |
| HUMANA | 60 | 22.8% |
| BCBS | 58 | 23.5% |
| MEDICARE | 50 | 21.2% |

**Why Aetna and Cigna lead escalations:**
Aetna's 180-day timely filing window creates more claims in the approaching-deadline range than BCBS/Medicare. Cigna's strict 90-day window pushes more claims into the critical urgency tier. Both payers also have stricter subscriber ID and prior auth requirements — adding payer-specific risk points on top of validation errors.

---

## Risk Score Breakdown — How Scores Are Built

The risk score is transparent and auditable. Every claim's score is explained by its component factors:

| Factor | Max Points | When Triggered |
|--------|-----------|----------------|
| Validation status = REJECTED | 40 | Critical errors from Project 1 |
| Validation status = FLAGGED | 20 | Warning errors from Project 1 |
| Critical error count (×7, cap 20) | 20 | Each critical error adds 7 pts |
| Payer risk weight | 10 | Cigna=10, Aetna=8, BCBS/Humana=5, Medicare=4 |
| Timely filing urgency | 15 | ≤10 days=15, ≤30 days=8, ≤60 days=3 |
| Dollar value | 5 | ≥$2,000=5pts, ≥$1,000=3pts |
| CPT procedure risk | 5 | Prior-auth required, bundling risk, frequency limits |

**Example score calculation — ESCALATE queue claim:**
```
REJECTED status:         +40 pts
2 critical errors:       +14 pts
CIGNA payer weight:      +10 pts
Timely filing (8 days):  +15 pts
Billed $3,200:           +5 pts
CPT 27447 (prior auth):  +5 pts
────────────────────────────────
Total score:              89 pts → ESCALATE (score ≥46 + billed ≥$2,000)
```

---

## Connection to Project 1

This engine directly consumes the output of the **Healthcare Claims DQ Platform (Project 1)**. No transformation required — the Project 1 validation report CSV is the input to this engine.

**Full pipeline:**
```
EDI 837 Claims
      ↓
Project 1: Healthcare Claims DQ Platform
      → Validates fields, enforces EDI 837 rules and payer configs
      → Output: claims_validation_report.csv (status, error codes, revenue at risk)
      ↓
Project 2: Intelligent Claim Routing Engine (this project)
      → Scores denial risk, assigns queues, generates action recommendations
      → Output: routed_claims.csv, action_worklist.csv, queue_summary.json
      ↓
Project 3: 835/837 Remittance Reconciliation Pipeline (coming)
      → Matches 835 remittance payments against 837 submissions
      → Feeds denial patterns back to Project 1 to improve validation rules
```

---

## Key Findings for Operations

**1. 35.8% first-pass yield**
429 of 1,200 claims cleared all checks and can be submitted immediately. In a real environment, these would be batched and submitted in one automated run — no billing team time required.

**2. ESCALATE queue carries most revenue risk**
$1,134,808.53 sits in the ESCALATE queue — more than AUTO_PROCESS, REVIEW, or HOLD individually. These high-dollar, high-risk claims need manager attention before any submission or write-off decision.

**3. 234 timely filing alerts demand immediate attention**
19.5% of claims have time-based urgency. In a real RCM operation, these would be surfaced to billing leads first thing each morning. Every day of delay on a timely filing alert is a day closer to permanent revenue loss.

**4. REJECT queue is small but permanent**
49 claims (4.1%) in the REJECT queue represent $58,978.83 in revenue that is either unrecoverable or requires formal appeal. The 12 WRITE_OFF recommendations are specifically timely-filing-exceeded cases where the window has closed.

---

## Technical Notes

**Scoring engine:** Python-based, 7-factor weighted model
**Processing speed:** 1,200 claims in 0.17 seconds
**Config-driven:** All thresholds, payer weights, and escalation rules in JSON — updatable without code changes
**Test coverage:** 22 unit tests across scoring factors and queue assignment
**Input format:** Direct consumption of Project 1 (Healthcare Claims DQ Platform) output CSV

---

*Generated by Intelligent Claim Routing Engine*
*github.com/lp07/intelligent-claim-routing-engine*

# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
models.py — Data Models for the Intelligent Claim Routing Engine

WHY THIS FILE EXISTS:
Every claim that enters the routing engine produces a result.
That result carries: which claim, what risk score, which queue,
what actions are recommended, and why.

We define those structures here — once — so every module uses
the same shape. Same pattern as Project 1.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class QueueType(Enum):
    """
    The 5 routing queues — each maps to a specific operational workflow.

    WHY ENUMS:
    Queue names cannot be arbitrary strings. An enum ensures
    'AUTO_PROCESS' is always 'AUTO_PROCESS' — not 'auto_process'
    or 'AutoProcess' depending on who wrote the code.
    """
    AUTO_PROCESS = "AUTO_PROCESS"   # Low risk — submit immediately
    REVIEW       = "REVIEW"         # Medium risk — billing team review
    HOLD         = "HOLD"           # High risk — senior coder needed
    ESCALATE     = "ESCALATE"       # High risk + high dollar — RCM manager
    REJECT       = "REJECT"         # Critical errors — write-off or appeal


class RiskLevel(Enum):
    """
    Human-readable risk tier mapped from numeric score.
    Used in reports and action recommendations.
    """
    LOW      = "LOW"       # Score 0–20
    MEDIUM   = "MEDIUM"    # Score 21–45
    HIGH     = "HIGH"      # Score 46–70
    CRITICAL = "CRITICAL"  # Score 71–100


class ActionType(Enum):
    """
    What should happen to this claim after routing.
    Each queue maps to a primary action — but complex claims
    may have multiple actions (e.g. CORRECT_AND_RESUBMIT + ESCALATE).
    """
    SUBMIT_IMMEDIATELY    = "SUBMIT_IMMEDIATELY"
    CORRECT_AND_RESUBMIT  = "CORRECT_AND_RESUBMIT"
    SENIOR_CODER_REVIEW   = "SENIOR_CODER_REVIEW"
    MANAGER_ESCALATION    = "MANAGER_ESCALATION"
    APPEAL                = "APPEAL"
    WRITE_OFF             = "WRITE_OFF"
    TIMELY_FILING_URGENT  = "TIMELY_FILING_URGENT"


@dataclass
class RiskScoreBreakdown:
    """
    Detailed breakdown of how the risk score was calculated.

    WHY TRANSPARENCY MATTERS:
    A black-box score of '73' is useless to a billing team.
    They need to know: "This scored 73 because REJECTED (+40),
    Cigna high-risk payer (+10), timely filing in 8 days (+15)."
    This breakdown is what makes the engine actionable, not just predictive.
    """
    # Base validation status contribution
    validation_status_points: int = 0

    # Error-based contributions
    critical_error_points: int = 0
    warning_error_points: int = 0

    # Payer risk contribution
    payer_risk_points: int = 0

    # Timely filing urgency contribution
    timely_filing_points: int = 0

    # Dollar value contribution
    dollar_value_points: int = 0

    # CPT procedure risk contribution
    cpt_risk_points: int = 0

    @property
    def total(self) -> int:
        return min(100, (
            self.validation_status_points +
            self.critical_error_points +
            self.warning_error_points +
            self.payer_risk_points +
            self.timely_filing_points +
            self.dollar_value_points +
            self.cpt_risk_points
        ))

    def to_dict(self) -> dict:
        return {
            "validation_status_pts": self.validation_status_points,
            "critical_error_pts":    self.critical_error_points,
            "warning_error_pts":     self.warning_error_points,
            "payer_risk_pts":        self.payer_risk_points,
            "timely_filing_pts":     self.timely_filing_points,
            "dollar_value_pts":      self.dollar_value_points,
            "cpt_risk_pts":          self.cpt_risk_points,
            "total_score":           self.total,
        }


@dataclass
class ActionRecommendation:
    """
    What the routing engine recommends doing with this claim.

    WHY RECOMMENDATIONS NOT JUST QUEUES:
    A queue tells you WHERE the claim goes.
    A recommendation tells you WHAT TO DO and BY WHEN.
    Real RCM teams need actionable instructions, not just labels.
    """
    action_type: ActionType
    priority: int                    # 1 = highest priority, 5 = lowest
    due_by_days: Optional[int]       # How many days to act before risk increases
    instructions: str                # Human-readable instruction for billing team
    error_codes_to_fix: List[str] = field(default_factory=list)


@dataclass
class RoutingResult:
    """
    The complete routing result for one claim.

    This is the primary output object of the routing engine.
    Every field tells part of the story:
    - claim_id, payer, billed_amount: claim identity
    - validation_status: what Project 1 found
    - risk_score: our calculated denial probability (0-100)
    - risk_level: human-readable tier
    - queue: where this claim goes
    - actions: what to do with it
    - score_breakdown: why it scored this way
    """
    # Claim identity (from Project 1 output)
    claim_id: str
    patient_id: str
    payer: str
    billed_amount: float
    validation_status: str           # VALID / FLAGGED / REJECTED from Project 1
    error_codes: str                 # Pipe-delimited error codes from Project 1
    critical_error_count: int
    warning_error_count: int
    date_of_service: str

    # Routing outputs
    risk_score: int = 0
    risk_level: RiskLevel = RiskLevel.LOW
    queue: QueueType = QueueType.AUTO_PROCESS
    actions: List[ActionRecommendation] = field(default_factory=list)
    score_breakdown: Optional[RiskScoreBreakdown] = None

    # Metadata
    routing_reason: str = ""         # One-line explanation of queue assignment

    def to_dict(self) -> dict:
        """Serialize to flat dict for CSV output."""
        primary_action = self.actions[0] if self.actions else None
        return {
            "claim_id":                self.claim_id,
            "patient_id":              self.patient_id,
            "payer":                   self.payer,
            "billed_amount":           self.billed_amount,
            "date_of_service":         self.date_of_service,
            "validation_status":       self.validation_status,
            "error_codes":             self.error_codes,
            "critical_error_count":    self.critical_error_count,
            "warning_error_count":     self.warning_error_count,
            "risk_score":              self.risk_score,
            "risk_level":              self.risk_level.value,
            "queue":                   self.queue.value,
            "routing_reason":          self.routing_reason,
            "primary_action":          primary_action.action_type.value if primary_action else "",
            "action_priority":         primary_action.priority if primary_action else "",
            "due_by_days":             primary_action.due_by_days if primary_action else "",
            "instructions":            primary_action.instructions if primary_action else "",
            "error_codes_to_fix":      "|".join(primary_action.error_codes_to_fix) if primary_action else "",
            # Score breakdown
            "score_validation_pts":    self.score_breakdown.validation_status_points if self.score_breakdown else 0,
            "score_critical_error_pts":self.score_breakdown.critical_error_points if self.score_breakdown else 0,
            "score_payer_risk_pts":    self.score_breakdown.payer_risk_points if self.score_breakdown else 0,
            "score_timely_filing_pts": self.score_breakdown.timely_filing_points if self.score_breakdown else 0,
            "score_dollar_pts":        self.score_breakdown.dollar_value_points if self.score_breakdown else 0,
            "score_cpt_risk_pts":      self.score_breakdown.cpt_risk_points if self.score_breakdown else 0,
        }

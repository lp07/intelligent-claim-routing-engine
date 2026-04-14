# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
scorer.py — Multi-Factor Denial Risk Scorer

WHY THIS FILE EXISTS:
A claim's validation status alone doesn't tell you how likely it is
to be denied or how urgently it needs attention.

A REJECTED Cigna claim with $3,500 billed and 8 days left on timely
filing needs immediate escalation. A REJECTED Medicare claim with
$180 billed and 300 days left can wait in a normal queue.

This scorer combines 7 factors into a single 0-100 risk score that
drives queue assignment and action recommendations.

RESEARCH BASIS:
Real RCM systems (PracticeSuite, AnnexMed, Inovalon) use composite
scoring combining: validation errors, payer strictness, timely filing
urgency, dollar value, and procedure risk. This implementation
mirrors that architecture in a transparent, auditable way.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

from routing_engine.models import RiskScoreBreakdown

logger = logging.getLogger(__name__)


class DenialRiskScorer:
    """
    Calculates a 0-100 denial risk score for each claim.

    Score composition (max 100 points):
    ┌─────────────────────────────┬──────────┬────────────────────────────────┐
    │ Factor                      │ Max Pts  │ Why It Matters                 │
    ├─────────────────────────────┼──────────┼────────────────────────────────┤
    │ Validation status           │ 40       │ Primary denial predictor        │
    │ Critical error count        │ 20       │ Each error = likely denial      │
    │ Payer risk weight           │ 10       │ Cigna denies more than Medicare │
    │ Timely filing urgency       │ 15       │ Deadline pressure = act now     │
    │ Dollar value                │ 5        │ High $ = higher scrutiny        │
    │ CPT procedure risk          │ 5        │ Prior auth/bundling risk        │
    │ Warning error count         │ 5        │ Warnings compound risk          │
    └─────────────────────────────┴──────────┴────────────────────────────────┘
    """

    def __init__(self, config_dir: str = "routing_configs"):
        self.config_dir = config_dir
        self._payer_config = self._load_config("payer_risk.json")
        self._threshold_config = self._load_config("thresholds.json")
        self._cpt_config = self._load_config("cpt_risk.json")
        self._cpt_risk_map = self._build_cpt_risk_map()
        logger.info("DenialRiskScorer initialized.")

    def _load_config(self, filename: str) -> dict:
        path = os.path.join(self.config_dir, filename)
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config not found: {path}. Using defaults.")
            return {}

    def _build_cpt_risk_map(self) -> Dict[str, int]:
        """
        Flatten CPT risk categories into a dict: {cpt_code: risk_points}.
        This makes O(1) lookup per claim instead of iterating all categories.
        """
        risk_map = {}
        categories = self._cpt_config.get("risk_categories", {})
        for category, data in categories.items():
            points = data.get("risk_points", 0)
            for code in data.get("codes", []):
                # Take highest risk points if code appears in multiple categories
                risk_map[code] = max(risk_map.get(code, 0), points)
        return risk_map

    def score(self, claim: Dict[str, Any]) -> RiskScoreBreakdown:
        """
        Calculate full risk score breakdown for a single claim.

        Args:
            claim: dict with keys from Project 1 validation report CSV

        Returns:
            RiskScoreBreakdown with individual factor scores and total
        """
        breakdown = RiskScoreBreakdown()

        breakdown.validation_status_points = self._score_validation_status(claim)
        breakdown.critical_error_points    = self._score_critical_errors(claim)
        breakdown.warning_error_points     = self._score_warning_errors(claim)
        breakdown.payer_risk_points        = self._score_payer_risk(claim)
        breakdown.timely_filing_points     = self._score_timely_filing(claim)
        breakdown.dollar_value_points      = self._score_dollar_value(claim)
        breakdown.cpt_risk_points          = self._score_cpt_risk(claim)

        return breakdown

    # ─── Individual Factor Scorers ────────────────────────────────────────────

    def _score_validation_status(self, claim: dict) -> int:
        """
        Validation status from Project 1 — the single strongest predictor.

        REJECTED = 40 pts: Critical errors present, will be denied as-is
        FLAGGED  = 20 pts: Warnings present, may pass but risky
        VALID    = 0 pts:  Clean claim, no baseline risk from validation
        """
        status = str(claim.get("status", "")).upper().strip()
        if status == "REJECTED":
            return 40
        elif status == "FLAGGED":
            return 20
        return 0

    def _score_critical_errors(self, claim: dict) -> int:
        """
        Each critical error multiplies denial risk.
        Cap at 20 points (after 3 critical errors the claim is essentially
        unsubmittable — additional errors don't add more urgency).

        Research basis: Most payers stop processing at first critical error.
        But from a prioritization standpoint, more errors = more rework needed.
        """
        try:
            count = int(float(str(claim.get("critical_error_count", 0))))
        except (ValueError, TypeError):
            count = 0
        return min(20, count * 7)

    def _score_warning_errors(self, claim: dict) -> int:
        """
        Warning errors add moderate risk — they may not cause denial
        but increase scrutiny and reprocessing likelihood.
        Cap at 5 points.
        """
        try:
            count = int(float(str(claim.get("error_count", 0)))) - \
                    int(float(str(claim.get("critical_error_count", 0))))
            count = max(0, count)
        except (ValueError, TypeError):
            count = 0
        return min(5, count * 2)

    def _score_payer_risk(self, claim: dict) -> int:
        """
        Payer-specific denial risk weight.

        CIGNA scores highest (10 pts) because:
        - 90-day timely filing window (strictest in industry)
        - Requires prior auth on most specialist procedures
        - Highest denial rate in our portfolio data

        MEDICARE scores lowest (4 pts) because:
        - 365-day timely filing
        - More predictable adjudication rules
        - Lower commercial denial rate
        """
        payer = str(claim.get("payer", "DEFAULT")).upper().strip()
        weights = self._payer_config.get("weights", {})
        return weights.get(payer, weights.get("DEFAULT", 3))

    def _score_timely_filing(self, claim: dict) -> int:
        """
        Timely filing urgency — how close is this claim to the payer's deadline?

        This is the most operationally critical factor.
        A claim expiring in 8 days needs same-day action.
        A claim expiring in 300 days can wait.

        Scoring tiers (from thresholds.json):
        ≤10 days remaining  → 15 pts (CRITICAL — act today)
        ≤30 days remaining  → 8 pts  (WARNING — act this week)
        ≤60 days remaining  → 3 pts  (APPROACHING — schedule review)
        >60 days remaining  → 0 pts  (No urgency)
        """
        payer = str(claim.get("payer", "DEFAULT")).upper().strip()
        dos_str = str(claim.get("date_of_service", "")).strip()

        if not dos_str:
            return 0

        try:
            dos = datetime.strptime(dos_str, "%Y-%m-%d")
        except ValueError:
            return 0

        # Get payer-specific filing window
        filing_days = self._payer_config.get("timely_filing_days", {})
        window = filing_days.get(payer, filing_days.get("DEFAULT", 365))

        days_elapsed = (datetime.today() - dos).days
        days_remaining = window - days_elapsed

        urgency_config = self._threshold_config.get("timely_filing_urgency", {})

        if days_remaining <= urgency_config.get("critical_days_remaining", 10):
            return urgency_config.get("critical_points", 15)
        elif days_remaining <= urgency_config.get("warning_days_remaining", 30):
            return urgency_config.get("warning_points", 8)
        elif days_remaining <= urgency_config.get("approaching_days_remaining", 60):
            return urgency_config.get("approaching_points", 3)
        return 0

    def _score_dollar_value(self, claim: dict) -> int:
        """
        High-dollar claims receive extra scrutiny from payers
        and have higher revenue impact if denied.

        Research basis: AnnexMed and similar RCM firms prioritize
        high-value accounts first. Claims >$2,000 get escalation
        treatment when combined with high risk scores.
        """
        try:
            amount = float(str(claim.get("billed_amount", 0)))
        except (ValueError, TypeError):
            amount = 0

        dollar_config = self._threshold_config.get("dollar_value_tiers", {})

        if amount >= dollar_config.get("high_value_threshold", 2000):
            return dollar_config.get("high_value_points", 5)
        elif amount >= dollar_config.get("medium_value_threshold", 1000):
            return dollar_config.get("medium_value_points", 3)
        return 0

    def _score_cpt_risk(self, claim: dict) -> int:
        """
        CPT-based procedure risk.

        Certain CPT codes have elevated denial risk regardless of other factors:
        - Prior auth required codes (prior auth missing = auto-denial)
        - Bundling risk codes (may be denied as included in another service)
        - Medical necessity scrutiny codes (requires strong diagnosis support)
        - Frequency limit codes (too many in a period = denial)

        Research basis: CPT/ICD-10 mismatch and prior auth gaps
        account for 25-30% of denied claims in 2026 (SteadyMedical research).
        """
        procedure_code = str(claim.get("procedure_code", "")).strip().upper()
        if not procedure_code:
            return 0
        return self._cpt_risk_map.get(procedure_code, 0)

    def days_until_timely_filing_deadline(self, claim: dict) -> Optional[int]:
        """
        Calculate exact days remaining before timely filing deadline.
        Used in action recommendations to give billing team specific dates.
        """
        payer = str(claim.get("payer", "DEFAULT")).upper().strip()
        dos_str = str(claim.get("date_of_service", "")).strip()

        if not dos_str:
            return None

        try:
            dos = datetime.strptime(dos_str, "%Y-%m-%d")
        except ValueError:
            return None

        filing_days = self._payer_config.get("timely_filing_days", {})
        window = filing_days.get(payer, 365)
        days_elapsed = (datetime.today() - dos).days
        return max(0, window - days_elapsed)


# Fix missing Optional import
from typing import Optional

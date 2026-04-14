# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
router.py — Queue Assignment and Action Recommendation Engine

WHY THIS FILE EXISTS:
The scorer calculates HOW risky a claim is (0-100).
The router decides WHERE it goes and WHAT to do with it.

These are separate responsibilities:
- Scorer: pure math, no business rules
- Router: business logic, operational decisions

This separation means you can change routing rules (e.g. lower the
escalation threshold from $2,000 to $1,500) without touching the
scoring logic. And vice versa.

ROUTING LOGIC:
1. Calculate risk score via DenialRiskScorer
2. Determine base queue from score thresholds
3. Apply escalation override (high score + high dollar → ESCALATE)
4. Generate action recommendations based on queue + error codes
5. Return populated RoutingResult
"""

import json
import logging
import os
from typing import Dict, Any, List

from routing_engine.models import (
    RoutingResult, RiskScoreBreakdown, QueueType, RiskLevel,
    ActionRecommendation, ActionType
)
from routing_engine.scorer import DenialRiskScorer

logger = logging.getLogger(__name__)


class ClaimRouter:
    """
    Routes claims to queues and generates action recommendations.

    Usage:
        router = ClaimRouter(config_dir="routing_configs")
        result = router.route(claim_dict)
    """

    def __init__(self, config_dir: str = "routing_configs"):
        self.scorer = DenialRiskScorer(config_dir=config_dir)
        self._threshold_config = self._load_config(
            os.path.join(config_dir, "thresholds.json")
        )
        logger.info("ClaimRouter initialized.")

    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config not found: {path}")
            return {}

    def route(self, claim: Dict[str, Any]) -> RoutingResult:
        """
        Route a single claim to a queue with action recommendations.

        Args:
            claim: dict from Project 1 validation report row

        Returns:
            RoutingResult with queue, risk score, and actions
        """
        # Step 1: Calculate risk score
        breakdown = self.scorer.score(claim)
        score = breakdown.total

        # Step 2: Determine risk level
        risk_level = self._get_risk_level(score)

        # Step 3: Determine base queue from score
        queue = self._get_base_queue(score)

        # Step 4: Apply escalation override
        queue, escalation_applied = self._apply_escalation(claim, queue, score)

        # Step 5: Build routing reason
        routing_reason = self._build_routing_reason(
            claim, score, queue, breakdown, escalation_applied
        )

        # Step 6: Generate action recommendations
        actions = self._generate_actions(claim, queue, breakdown, score)

        # Step 7: Build result
        result = RoutingResult(
            claim_id=str(claim.get("claim_id", "UNKNOWN")),
            patient_id=str(claim.get("patient_id", "UNKNOWN")),
            payer=str(claim.get("payer", "UNKNOWN")),
            billed_amount=float(claim.get("billed_amount", 0)),
            validation_status=str(claim.get("status", "UNKNOWN")),
            error_codes=str(claim.get("error_codes", "")),
            critical_error_count=int(float(str(claim.get("critical_error_count", 0)))),
            warning_error_count=max(0,
                int(float(str(claim.get("error_count", 0)))) -
                int(float(str(claim.get("critical_error_count", 0))))
            ),
            date_of_service=str(claim.get("date_of_service", "")),
            risk_score=score,
            risk_level=risk_level,
            queue=queue,
            actions=actions,
            score_breakdown=breakdown,
            routing_reason=routing_reason,
        )

        return result

    def route_batch(self, claims_df) -> List[RoutingResult]:
        """
        Route a full batch of claims from a pandas DataFrame.

        WHY ACCEPTS DATAFRAME:
        Project 1 output is a CSV → pandas DataFrame.
        This method takes that directly, making the Project 1 → Project 2
        connection explicit and zero-transformation.
        """
        import time
        results = []
        total = len(claims_df)
        start = time.time()

        logger.info(f"Starting routing batch: {total} claims")

        for idx, row in claims_df.iterrows():
            result = self.route(row.to_dict())
            results.append(result)

            if (idx + 1) % 100 == 0:
                logger.info(f"Routed {idx + 1}/{total} claims...")

        elapsed = round(time.time() - start, 2)

        # Queue distribution summary
        queue_counts = {}
        for r in results:
            queue_counts[r.queue.value] = queue_counts.get(r.queue.value, 0) + 1

        logger.info(
            f"Routing complete in {elapsed}s | "
            f"AUTO: {queue_counts.get('AUTO_PROCESS', 0)} | "
            f"REVIEW: {queue_counts.get('REVIEW', 0)} | "
            f"HOLD: {queue_counts.get('HOLD', 0)} | "
            f"ESCALATE: {queue_counts.get('ESCALATE', 0)} | "
            f"REJECT: {queue_counts.get('REJECT', 0)}"
        )

        return results

    # ─── Private Methods ──────────────────────────────────────────────────────

    def _get_risk_level(self, score: int) -> RiskLevel:
        if score <= 20:   return RiskLevel.LOW
        elif score <= 45: return RiskLevel.MEDIUM
        elif score <= 70: return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def _get_base_queue(self, score: int) -> QueueType:
        """
        Map score to base queue using thresholds from config.

        WHY CONFIG-DRIVEN THRESHOLDS:
        Business needs change. If the organization wants to be more
        conservative and lower the AUTO_PROCESS ceiling from 20 to 15,
        that's a JSON edit — not a code change.
        """
        thresholds = self._threshold_config.get("queue_thresholds", {})

        if score <= thresholds.get("AUTO_PROCESS", {}).get("max_score", 20):
            return QueueType.AUTO_PROCESS
        elif score <= thresholds.get("REVIEW", {}).get("max_score", 45):
            return QueueType.REVIEW
        elif score <= thresholds.get("HOLD", {}).get("max_score", 70):
            return QueueType.HOLD
        return QueueType.REJECT

    def _apply_escalation(
        self, claim: dict, base_queue: QueueType, score: int
    ) -> tuple:
        """
        Escalation override: HOLD or REJECT + high dollar → ESCALATE

        WHY ESCALATION EXISTS AS A SEPARATE QUEUE:
        A $4,500 claim with a 73 risk score needs immediate manager attention.
        A $90 claim with the same score can go through normal REJECT workflow.
        Dollar value changes who needs to act, not just the urgency.

        Research basis: AnnexMed and similar RCM firms explicitly prioritize
        high-value denials for manager escalation before write-off decisions.
        """
        escalation_config = self._threshold_config.get("escalation_rules", {})
        dollar_threshold = escalation_config.get("dollar_threshold", 2000)
        score_threshold = escalation_config.get("score_threshold", 46)

        try:
            billed = float(str(claim.get("billed_amount", 0)))
        except (ValueError, TypeError):
            billed = 0

        if (score >= score_threshold and
            billed >= dollar_threshold and
            base_queue in [QueueType.HOLD, QueueType.REJECT]):
            return QueueType.ESCALATE, True

        return base_queue, False

    def _build_routing_reason(
        self,
        claim: dict,
        score: int,
        queue: QueueType,
        breakdown: RiskScoreBreakdown,
        escalation_applied: bool
    ) -> str:
        """
        One-line human-readable explanation of why claim was routed here.
        This is what a billing team member sees in the worklist.
        """
        payer = str(claim.get("payer", "")).upper()
        status = str(claim.get("status", "")).upper()

        reasons = []

        if status == "REJECTED":
            reasons.append("critical validation errors")
        elif status == "FLAGGED":
            reasons.append("validation warnings")

        if breakdown.timely_filing_points >= 15:
            reasons.append("timely filing <10 days")
        elif breakdown.timely_filing_points >= 8:
            reasons.append("timely filing <30 days")

        if escalation_applied:
            reasons.append(f"high-value claim (${float(claim.get('billed_amount', 0)):,.0f})")

        if breakdown.payer_risk_points >= 8:
            reasons.append(f"{payer} high-risk payer")

        if breakdown.cpt_risk_points > 0:
            reasons.append("prior-auth/bundling risk CPT")

        reason_str = "; ".join(reasons) if reasons else "standard validation"
        return f"Score {score} → {queue.value} | {reason_str}"

    def _generate_actions(
        self,
        claim: dict,
        queue: QueueType,
        breakdown: RiskScoreBreakdown,
        score: int
    ) -> List[ActionRecommendation]:
        """
        Generate specific action recommendations based on queue and errors.

        WHY ACTIONS NOT JUST QUEUES:
        A queue tells billing WHERE to put the claim.
        An action tells them WHAT TO DO and WHEN.

        Research basis: Skills-based routing (CareCloud, 2012) shows
        that combining queue routing with specific instructions reduces
        claim rework time by enabling staff to act immediately without
        additional investigation.
        """
        actions = []
        error_codes = str(claim.get("error_codes", ""))
        error_list = [e for e in error_codes.split("|") if e]
        days_left = self.scorer.days_until_timely_filing_deadline(claim)
        billed = float(str(claim.get("billed_amount", 0)) or 0)

        if queue == QueueType.AUTO_PROCESS:
            actions.append(ActionRecommendation(
                action_type=ActionType.SUBMIT_IMMEDIATELY,
                priority=5,
                due_by_days=1,
                instructions="Claim passed all validation checks. Submit to payer immediately.",
                error_codes_to_fix=[]
            ))

        elif queue == QueueType.REVIEW:
            npi_errors = [e for e in error_list if "NPI" in e]
            dx_errors  = [e for e in error_list if "DX" in e]
            instructions = "Review flagged fields before submission. "
            if npi_errors:
                instructions += "Verify provider NPI format and Luhn validity. "
            if dx_errors:
                instructions += "Confirm diagnosis pointer maps to correct HI segment code. "
            instructions += "Resubmit once corrections are confirmed."

            actions.append(ActionRecommendation(
                action_type=ActionType.CORRECT_AND_RESUBMIT,
                priority=3,
                due_by_days=min(days_left or 30, 5),
                instructions=instructions.strip(),
                error_codes_to_fix=error_list[:5]
            ))

        elif queue == QueueType.HOLD:
            npi_errors  = [e for e in error_list if "NPI" in e]
            date_errors = [e for e in error_list if "DATE" in e or "TF" in e]
            instructions = "Senior coder review required. "
            if npi_errors:
                instructions += f"Correct {len(npi_errors)} NPI error(s): verify 10-digit format and Luhn checksum. "
            if date_errors and days_left is not None:
                instructions += f"TIMELY FILING: {days_left} days remaining. Prioritize submission. "
            instructions += "Do not submit until all critical errors are resolved."

            priority = 1 if (days_left is not None and days_left <= 10) else 2

            actions.append(ActionRecommendation(
                action_type=ActionType.SENIOR_CODER_REVIEW,
                priority=priority,
                due_by_days=min(days_left or 48, 2),
                instructions=instructions.strip(),
                error_codes_to_fix=error_list
            ))

        elif queue == QueueType.ESCALATE:
            instructions = (
                f"ESCALATE TO RCM MANAGER — High-value claim (${billed:,.0f}) with "
                f"risk score {score}. "
            )
            if days_left is not None and days_left <= 30:
                instructions += f"URGENT: {days_left} days before timely filing deadline. "
            instructions += (
                "Manager to decide: appeal, senior coder correction, or write-off analysis. "
                "Do not route to standard queue without manager sign-off."
            )

            actions.append(ActionRecommendation(
                action_type=ActionType.MANAGER_ESCALATION,
                priority=1,
                due_by_days=1,
                instructions=instructions.strip(),
                error_codes_to_fix=error_list
            ))

        elif queue == QueueType.REJECT:
            tf_errors = [e for e in error_list if "TF_001" in e]
            if tf_errors:
                instructions = (
                    "Timely filing window exceeded — claim cannot be resubmitted. "
                    "Evaluate appeal options with payer or write off. "
                    "Document denial reason for root cause analysis."
                )
                actions.append(ActionRecommendation(
                    action_type=ActionType.WRITE_OFF,
                    priority=4,
                    due_by_days=30,
                    instructions=instructions,
                    error_codes_to_fix=tf_errors
                ))
            else:
                instructions = (
                    "Critical errors cannot be corrected post-submission. "
                    "Evaluate appeal eligibility. If appeal viable, assign to appeal "
                    "specialist. Otherwise initiate write-off process."
                )
                actions.append(ActionRecommendation(
                    action_type=ActionType.APPEAL,
                    priority=3,
                    due_by_days=min(days_left or 30, 30),
                    instructions=instructions,
                    error_codes_to_fix=error_list
                ))

        # Add timely filing urgency as secondary action if days are critical
        if (days_left is not None and days_left <= 10 and
            queue not in [QueueType.AUTO_PROCESS, QueueType.REJECT]):
            actions.append(ActionRecommendation(
                action_type=ActionType.TIMELY_FILING_URGENT,
                priority=1,
                due_by_days=days_left,
                instructions=(
                    f"CRITICAL: Only {days_left} day(s) remaining before "
                    f"{claim.get('payer', 'payer')} timely filing deadline. "
                    "This claim must be submitted or escalated today."
                ),
                error_codes_to_fix=[]
            ))

        return actions

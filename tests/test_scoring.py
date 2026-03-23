"""
tests/test_scoring.py — Unit Tests for Routing Engine

Tests cover:
- Risk score calculation for each factor
- Queue assignment from scores
- Escalation override logic
- Edge cases (missing fields, zero amounts, future dates)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta

from routing_engine.scorer import DenialRiskScorer
from routing_engine.router import ClaimRouter
from routing_engine.models import QueueType, RiskLevel


CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "routing_configs")


@pytest.fixture
def scorer():
    return DenialRiskScorer(config_dir=CONFIG_DIR)

@pytest.fixture
def router():
    return ClaimRouter(config_dir=CONFIG_DIR)

def make_claim(**overrides):
    """Base valid claim dict. Override specific fields per test."""
    defaults = {
        "claim_id":             "CLM000001",
        "patient_id":           "PAT12345",
        "payer":                "BCBS",
        "billed_amount":        500.0,
        "date_of_service":      (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "status":               "VALID",
        "error_count":          0,
        "critical_error_count": 0,
        "error_codes":          "",
        "revenue_at_risk":      0.0,
        "procedure_code":       "99213",
    }
    defaults.update(overrides)
    return defaults


# ─── Validation Status Scoring ────────────────────────────────────────────────

class TestValidationStatusScoring:

    def test_valid_claim_scores_zero(self, scorer):
        claim = make_claim(status="VALID")
        breakdown = scorer.score(claim)
        assert breakdown.validation_status_points == 0

    def test_flagged_claim_scores_20(self, scorer):
        claim = make_claim(status="FLAGGED")
        breakdown = scorer.score(claim)
        assert breakdown.validation_status_points == 20

    def test_rejected_claim_scores_40(self, scorer):
        claim = make_claim(status="REJECTED")
        breakdown = scorer.score(claim)
        assert breakdown.validation_status_points == 40

    def test_unknown_status_scores_zero(self, scorer):
        claim = make_claim(status="UNKNOWN")
        breakdown = scorer.score(claim)
        assert breakdown.validation_status_points == 0


# ─── Critical Error Scoring ───────────────────────────────────────────────────

class TestCriticalErrorScoring:

    def test_no_errors_scores_zero(self, scorer):
        claim = make_claim(critical_error_count=0)
        breakdown = scorer.score(claim)
        assert breakdown.critical_error_points == 0

    def test_one_critical_error_scores_7(self, scorer):
        claim = make_claim(critical_error_count=1, status="REJECTED")
        breakdown = scorer.score(claim)
        assert breakdown.critical_error_points == 7

    def test_three_critical_errors_scores_21_capped_at_20(self, scorer):
        claim = make_claim(critical_error_count=3, status="REJECTED")
        breakdown = scorer.score(claim)
        assert breakdown.critical_error_points == 20

    def test_max_critical_errors_caps_at_20(self, scorer):
        claim = make_claim(critical_error_count=10, status="REJECTED")
        breakdown = scorer.score(claim)
        assert breakdown.critical_error_points == 20


# ─── Payer Risk Scoring ───────────────────────────────────────────────────────

class TestPayerRiskScoring:

    def test_cigna_scores_highest(self, scorer):
        claim = make_claim(payer="CIGNA")
        breakdown = scorer.score(claim)
        assert breakdown.payer_risk_points == 10

    def test_aetna_scores_8(self, scorer):
        claim = make_claim(payer="AETNA")
        breakdown = scorer.score(claim)
        assert breakdown.payer_risk_points == 8

    def test_medicare_scores_lowest(self, scorer):
        claim = make_claim(payer="MEDICARE")
        breakdown = scorer.score(claim)
        assert breakdown.payer_risk_points == 4

    def test_unknown_payer_uses_default(self, scorer):
        claim = make_claim(payer="UNKNOWN_PAYER")
        breakdown = scorer.score(claim)
        assert breakdown.payer_risk_points == 3


# ─── Timely Filing Scoring ────────────────────────────────────────────────────

class TestTimelyFilingScoring:

    def test_claim_with_plenty_of_time_scores_zero(self, scorer):
        dos = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        claim = make_claim(payer="BCBS", date_of_service=dos)
        breakdown = scorer.score(claim)
        assert breakdown.timely_filing_points == 0

    def test_cigna_claim_near_deadline_scores_critical(self, scorer):
        # Cigna has 90-day window. 85 days ago = 5 days left
        dos = (datetime.today() - timedelta(days=85)).strftime("%Y-%m-%d")
        claim = make_claim(payer="CIGNA", date_of_service=dos)
        breakdown = scorer.score(claim)
        assert breakdown.timely_filing_points == 15

    def test_claim_approaching_deadline_scores_warning(self, scorer):
        # BCBS 365-day window. 340 days ago = 25 days left
        dos = (datetime.today() - timedelta(days=340)).strftime("%Y-%m-%d")
        claim = make_claim(payer="BCBS", date_of_service=dos)
        breakdown = scorer.score(claim)
        assert breakdown.timely_filing_points == 8

    def test_missing_dos_scores_zero(self, scorer):
        claim = make_claim(date_of_service="")
        breakdown = scorer.score(claim)
        assert breakdown.timely_filing_points == 0


# ─── Dollar Value Scoring ─────────────────────────────────────────────────────

class TestDollarValueScoring:

    def test_low_value_claim_scores_zero(self, scorer):
        claim = make_claim(billed_amount=500.0)
        breakdown = scorer.score(claim)
        assert breakdown.dollar_value_points == 0

    def test_medium_value_claim_scores_3(self, scorer):
        claim = make_claim(billed_amount=1500.0)
        breakdown = scorer.score(claim)
        assert breakdown.dollar_value_points == 3

    def test_high_value_claim_scores_5(self, scorer):
        claim = make_claim(billed_amount=3500.0)
        breakdown = scorer.score(claim)
        assert breakdown.dollar_value_points == 5


# ─── Queue Assignment ─────────────────────────────────────────────────────────

class TestQueueAssignment:

    def test_clean_claim_routes_to_auto_process(self, router):
        claim = make_claim(status="VALID", billed_amount=300.0)
        result = router.route(claim)
        assert result.queue == QueueType.AUTO_PROCESS

    def test_flagged_low_dollar_routes_to_review(self, router):
        claim = make_claim(
            status="FLAGGED",
            payer="BCBS",
            billed_amount=400.0,
            error_count=2,
            critical_error_count=0,
        )
        result = router.route(claim)
        assert result.queue in [QueueType.REVIEW, QueueType.HOLD]

    def test_rejected_high_dollar_escalates(self, router):
        claim = make_claim(
            status="REJECTED",
            payer="CIGNA",
            billed_amount=4500.0,
            error_count=2,
            critical_error_count=2,
        )
        result = router.route(claim)
        assert result.queue == QueueType.ESCALATE

    def test_rejected_low_dollar_goes_to_reject(self, router):
        claim = make_claim(
            status="REJECTED",
            payer="MEDICARE",
            billed_amount=150.0,
            error_count=3,
            critical_error_count=3,
            error_codes="NPI_001|DX_002|PROC_002",
        )
        result = router.route(claim)
        assert result.queue in [QueueType.HOLD, QueueType.REJECT]

    def test_risk_score_not_exceeds_100(self, router):
        claim = make_claim(
            status="REJECTED",
            payer="CIGNA",
            billed_amount=5000.0,
            error_count=5,
            critical_error_count=5,
            date_of_service=(datetime.today() - timedelta(days=88)).strftime("%Y-%m-%d"),
        )
        result = router.route(claim)
        assert result.risk_score <= 100
        assert result.risk_score >= 0

    def test_routing_result_has_actions(self, router):
        claim = make_claim(status="FLAGGED")
        result = router.route(claim)
        assert len(result.actions) >= 1

    def test_auto_process_has_submit_action(self, router):
        claim = make_claim(status="VALID")
        result = router.route(claim)
        assert result.actions[0].action_type.value == "SUBMIT_IMMEDIATELY"


# ─── Risk Level ───────────────────────────────────────────────────────────────

class TestRiskLevel:

    def test_score_0_is_low_risk(self, router):
        claim = make_claim(status="VALID")
        result = router.route(claim)
        assert result.risk_level == RiskLevel.LOW

    def test_rejected_cigna_is_high_or_critical(self, router):
        claim = make_claim(
            status="REJECTED",
            payer="CIGNA",
            critical_error_count=2,
            error_count=2,
        )
        result = router.route(claim)
        assert result.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

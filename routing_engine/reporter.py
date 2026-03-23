"""
reporter.py — Routing Report Generator

WHY THIS FILE EXISTS:
The router produces RoutingResult objects.
This module turns those into three actionable outputs:

1. routed_claims.csv      — every claim with queue, score, and action
2. queue_summary.csv      — aggregate stats per queue
3. action_worklist.csv    — priority-sorted action list for billing team

WHY THREE OUTPUTS:
Different teams need different views.
- Operations manager → queue_summary (how many in each bucket, revenue impact)
- Billing team lead  → action_worklist (what to work first today)
- Data team          → routed_claims (full detail for analysis)
"""

import os
import json
import logging
from typing import List, Dict
from datetime import datetime

import pandas as pd

from routing_engine.models import RoutingResult, QueueType, RiskLevel

logger = logging.getLogger(__name__)


class RoutingReporter:

    def __init__(self, output_dir: str = "data/sample_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_routed_claims_report(self, results: List[RoutingResult]) -> str:
        """Full claim-level report with all routing details."""
        rows = [r.to_dict() for r in results]
        df = pd.DataFrame(rows)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"routed_claims_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False)
        logger.info(f"Routed claims report saved: {filepath}")
        return filepath

    def generate_queue_summary(self, results: List[RoutingResult]) -> dict:
        """
        Queue-level summary for operations managers.
        Shows claim counts, revenue distribution, and average risk scores per queue.
        """
        summary = {
            "run_timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_claims":    len(results),
            "total_billed":    round(sum(r.billed_amount for r in results), 2),
            "queues":          {},
            "risk_distribution": {},
            "avg_risk_score":  round(sum(r.risk_score for r in results) / len(results), 1) if results else 0,
        }

        # Per-queue stats
        for queue in QueueType:
            queue_results = [r for r in results if r.queue == queue]
            if not queue_results:
                continue
            total_billed = sum(r.billed_amount for r in queue_results)
            summary["queues"][queue.value] = {
                "count":        len(queue_results),
                "pct_of_total": round(len(queue_results) / len(results) * 100, 1),
                "total_billed": round(total_billed, 2),
                "avg_risk_score": round(
                    sum(r.risk_score for r in queue_results) / len(queue_results), 1
                ),
                "payers": dict(
                    pd.Series([r.payer for r in queue_results]).value_counts()
                ),
            }

        # Risk level distribution
        for level in RiskLevel:
            level_results = [r for r in results if r.risk_level == level]
            summary["risk_distribution"][level.value] = {
                "count": len(level_results),
                "pct":   round(len(level_results) / len(results) * 100, 1) if results else 0,
            }

        # Save
        self._print_summary(summary)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"queue_summary_{timestamp}.json")
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Queue summary saved: {filepath}")
        return summary

    def generate_action_worklist(self, results: List[RoutingResult]) -> str:
        """
        Priority-sorted action list for the billing team.

        WHY THIS IS THE MOST IMPORTANT OUTPUT:
        A billing team member starts their day with this list.
        It tells them exactly what to work, in what order, and what to do.
        No interpretation needed.

        Sorted by: priority (1 first) → due_by_days (soonest first) → billed_amount (highest first)
        """
        rows = []
        for result in results:
            if not result.actions:
                continue
            primary_action = result.actions[0]

            # Check for timely filing urgent secondary action
            tf_urgent = next(
                (a for a in result.actions[1:] if "TIMELY_FILING" in a.action_type.value),
                None
            )

            rows.append({
                "priority":            primary_action.priority,
                "queue":               result.queue.value,
                "claim_id":            result.claim_id,
                "payer":               result.payer,
                "billed_amount":       result.billed_amount,
                "date_of_service":     result.date_of_service,
                "risk_score":          result.risk_score,
                "due_by_days":         primary_action.due_by_days,
                "action":              primary_action.action_type.value,
                "timely_filing_alert": "YES" if tf_urgent else "",
                "error_codes":         result.error_codes,
                "instructions":        primary_action.instructions,
            })

        if not rows:
            return ""

        df = pd.DataFrame(rows)
        df = df.sort_values(
            by=["priority", "due_by_days", "billed_amount"],
            ascending=[True, True, False]
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"action_worklist_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False)
        logger.info(f"Action worklist saved: {filepath}")
        return filepath

    def _print_summary(self, summary: dict):
        """Console output for operations visibility."""
        print("\n" + "="*65)
        print("  INTELLIGENT CLAIM ROUTING — QUEUE SUMMARY")
        print("="*65)
        print(f"  Run Time:         {summary['run_timestamp']}")
        print(f"  Total Claims:     {summary['total_claims']}")
        print(f"  Total Billed:     ${summary['total_billed']:,.2f}")
        print(f"  Avg Risk Score:   {summary['avg_risk_score']}")
        print(f"\n  QUEUE DISTRIBUTION:")
        for queue_name, stats in summary["queues"].items():
            print(
                f"    {queue_name:<15} "
                f"{stats['count']:>4} claims ({stats['pct_of_total']:>5.1f}%)  "
                f"${stats['total_billed']:>12,.2f}  "
                f"avg score: {stats['avg_risk_score']}"
            )
        print(f"\n  RISK LEVEL DISTRIBUTION:")
        for level, stats in summary["risk_distribution"].items():
            print(f"    {level:<12} {stats['count']:>4} claims ({stats['pct']:>5.1f}%)")
        print("="*65 + "\n")

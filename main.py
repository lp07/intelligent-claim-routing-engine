# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
main.py — Intelligent Claim Routing Engine Entry Point

HOW TO RUN:
    python main.py --generate                        # Generate sample data + route
    python main.py                                   # Route existing sample data
    python main.py --input path/to/claims.csv        # Route your own file (Project 1 output)

CONNECTS TO PROJECT 1:
    The --input flag accepts the exact CSV output from the
    Healthcare Claims DQ Platform (Project 1).

    Example full pipeline:
    1. Run Project 1:  python main.py --generate
                       → produces claims_validation_report.csv
    2. Run Project 2:  python main.py --input ../healthcare-claims-dq-platform/data/sample_output/sample_validation_report.csv
                       → produces routed_claims.csv, queue_summary.json, action_worklist.csv
"""

import argparse
import logging
import os
import sys

import pandas as pd

from routing_engine.router import ClaimRouter
from routing_engine.reporter import RoutingReporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Intelligent Claim Routing Engine — Multi-factor denial risk scoring and queue assignment"
    )
    parser.add_argument("--input",        default="data/sample_project1_output.csv",
                        help="Path to validated claims CSV (Project 1 output format)")
    parser.add_argument("--output-dir",   default="data/sample_output",
                        help="Directory for output reports")
    parser.add_argument("--config-dir",   default="routing_configs",
                        help="Directory containing routing config JSON files")
    parser.add_argument("--generate",     action="store_true",
                        help="Generate fresh synthetic data before routing")
    return parser.parse_args()


def main():
    args = parse_args()

    # Generate sample data if needed
    if args.generate or not os.path.exists(args.input):
        logger.info("Generating synthetic claims data (Project 1 output format)...")
        from data.generate_sample_data import generate_project1_output
        df = generate_project1_output(1200)
        os.makedirs("data", exist_ok=True)
        df.to_csv(args.input, index=False)
        logger.info(f"Sample data saved to {args.input}")

    # Load claims
    try:
        claims_df = pd.read_csv(args.input)
        logger.info(f"Loaded {len(claims_df)} claims from {args.input}")
    except FileNotFoundError:
        logger.error(f"Input file not found: {args.input}")
        logger.error("Run with --generate flag to create sample data first.")
        sys.exit(1)

    # Route claims
    router   = ClaimRouter(config_dir=args.config_dir)
    reporter = RoutingReporter(output_dir=args.output_dir)

    results = router.route_batch(claims_df)

    # Generate reports
    routed_path   = reporter.generate_routed_claims_report(results)
    summary       = reporter.generate_queue_summary(results)
    worklist_path = reporter.generate_action_worklist(results)

    print(f"
Reports saved to: {args.output_dir}/")
    print(f"  Routed claims:    {os.path.basename(routed_path)}")
    if worklist_path:
        print(f"  Action worklist:  {os.path.basename(worklist_path)}")


if __name__ == "__main__":
    main()

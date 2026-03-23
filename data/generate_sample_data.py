"""
generate_sample_data.py

Generates synthetic data that mirrors the exact output format
of Project 1 (Healthcare Claims DQ Platform).

In production: this script is replaced by the actual Project 1 output CSV.
For portfolio demonstration: generates realistic data with the same schema.
"""

import pandas as pd
import random
from datetime import datetime, timedelta

VALID_NPIS = [
    "1234567893", "1679576722", "1982645297",
    "1003000126", "1144224569", "1932102084",
    "1528060639", "1891794814", "1269671339",
    "1734770807"
]

def generate_project1_output(n=1200):
    random.seed(42)

    payers = ["BCBS", "AETNA", "CIGNA", "HUMANA", "MEDICARE"]
    procedure_codes = [
        "99213", "99214", "99215", "99232", "93000",
        "71046", "80053", "85025", "36415", "99283",
        "G0438", "27447", "93306", "90837", "22612"
    ]
    error_code_sets = {
        "REJECTED_NPI":      ("NPI_001|NPI_006",    2, 0, "REJECTED"),
        "REJECTED_DATE":     ("PAYER_TF_001",        1, 0, "REJECTED"),
        "REJECTED_DX":       ("DX_002|DX_003",       1, 1, "REJECTED"),
        "REJECTED_MULTI":    ("NPI_003|DX_004|PAYER_TF_001", 2, 1, "REJECTED"),
        "REJECTED_PROC":     ("PROC_002|AMT_002",    1, 1, "REJECTED"),
        "FLAGGED_WARNING":   ("DX_004|PAYER_SUB_001",0, 2, "FLAGGED"),
        "FLAGGED_TF":        ("DATE_004",            0, 1, "FLAGGED"),
        "VALID":             ("",                    0, 0, "VALID"),
    }

    records = []
    for i in range(n):
        payer = random.choice(payers)
        billed = round(random.uniform(120, 5500), 2)
        dos_days_ago = random.randint(1, 350)
        dos = datetime.today() - timedelta(days=dos_days_ago)

        # Adjust DOS for Cigna to create more timely filing urgency
        if payer == "CIGNA":
            dos_days_ago = random.randint(60, 95)
            dos = datetime.today() - timedelta(days=dos_days_ago)

        # Weighted status distribution
        roll = random.random()
        if roll < 0.558:
            error_set = "VALID"
        elif roll < 0.604:
            error_set = "FLAGGED_WARNING"
        elif roll < 0.624:
            error_set = "FLAGGED_TF"
        elif roll < 0.674:
            error_set = "REJECTED_NPI"
        elif roll < 0.730:
            error_set = "REJECTED_DATE"
        elif roll < 0.780:
            error_set = "REJECTED_DX"
        elif roll < 0.840:
            error_set = "REJECTED_MULTI"
        else:
            error_set = "REJECTED_PROC"

        error_codes, critical_count, warning_count, status = error_code_sets[error_set]
        error_count = critical_count + warning_count

        revenue_at_risk = billed if status != "VALID" else 0.0

        records.append({
            "claim_id":             f"CLM{str(i+1).zfill(6)}",
            "patient_id":           f"PAT{random.randint(10000,99999)}",
            "payer":                payer,
            "billed_amount":        billed,
            "date_of_service":      dos.strftime("%Y-%m-%d"),
            "status":               status,
            "error_count":          error_count,
            "critical_error_count": critical_count,
            "error_codes":          error_codes,
            "error_messages":       "",
            "revenue_at_risk":      revenue_at_risk,
            "procedure_code":       random.choice(procedure_codes),
        })

    return pd.DataFrame(records)


if __name__ == "__main__":
    df = generate_project1_output(1200)
    df.to_csv("data/sample_project1_output.csv", index=False)
    print(f"Generated {len(df)} claims → data/sample_project1_output.csv")
    print(f"\nStatus distribution:\n{df['status'].value_counts()}")
    print(f"\nPayer distribution:\n{df['payer'].value_counts()}")

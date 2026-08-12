"""
Example: generate a synthetic feeder dataset with a mix of recent
street-view capture dates, stale ones, and some missing entirely — then
run the line-miles calculation and produce both the Excel output and a
visual summary. Fully synthetic - no real network data required.
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
import matplotlib.pyplot as plt

from line_miles_calculator import calculate_line_miles_by_feeder, export_to_excel, UNKNOWN_LABEL

TODAY = date(2026, 8, 13)


def make_synthetic_dataset(seed=11):
    rng = np.random.default_rng(seed)
    feeders = ["FDR-101", "FDR-102", "FDR-103"]
    customers = {"FDR-101": "Utility Co. A", "FDR-102": "Utility Co. A", "FDR-103": "Utility Co. B"}

    rows = []
    for feeder in feeders:
        n_features = rng.integers(15, 25)
        for _ in range(n_features):
            length = rng.uniform(0.05, 0.4)  # miles per span

            r = rng.random()
            if r < 0.45:
                # Recent street view -> Cross-Validated
                days_ago = rng.integers(0, 365 * 1.5)
                capture_date = TODAY - timedelta(days=int(days_ago))
            elif r < 0.85:
                # Old street view -> Imagery-Only
                days_ago = rng.integers(365 * 3, 365 * 6)
                capture_date = TODAY - timedelta(days=int(days_ago))
            else:
                # Missing entirely -> Unknown
                capture_date = None

            rows.append({
                "feeder": feeder,
                "customer": customers[feeder],
                "length_lms": round(length, 4),
                "streetview_capture_date": capture_date.isoformat() if capture_date else None,
            })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = make_synthetic_dataset()
    df.to_csv("sample_data/feeder_attributes.csv", index=False)
    print(f"Created synthetic dataset: {len(df)} features across {df['feeder'].nunique()} feeders")

    results = calculate_line_miles_by_feeder(
        df,
        length_field="length_lms",
        feeder_field="feeder",
        customer_field="customer",
        date_field="streetview_capture_date",
        recency_threshold_years=2,
        reference_date=TODAY,
    )

    export_to_excel(results, "sample_output/feeder_line_miles.xlsx")

    # Visual summary: stacked bar of line miles per feeder, by category
    categories = sorted({c for d in results.values() for c in d["lengths"]})
    feeders = sorted(results.keys())

    fig, ax = plt.subplots(figsize=(8, 5))
    bottom = np.zeros(len(feeders))
    colors = {"Cross-Validated": "#2E7D32", "Imagery-Only": "#F9A825", UNKNOWN_LABEL: "#B0BEC5"}

    for cat in categories:
        values = [results[f]["lengths"].get(cat, 0.0) for f in feeders]
        ax.bar(feeders, values, bottom=bottom, label=cat, color=colors.get(cat, "gray"))
        bottom += np.array(values)

    ax.set_ylabel("Line miles")
    ax.set_title("Line miles by feeder and validation category")
    ax.legend()
    plt.tight_layout()
    plt.savefig("line_miles_demo.png", dpi=150)
    print("\nSaved demo image: line_miles_demo.png")

    # Print a quick summary to prove the Unknown-handling logic works
    for f in feeders:
        d = results[f]
        print(f"\n{f} ({d['customer']}):")
        for cat, length in d["lengths"].items():
            hrs = d["estimated_minutes"].get(cat, None)
            hrs_str = f"{hrs/60:.2f} hrs" if hrs is not None else "excluded from estimate"
            print(f"  {cat}: {length:.3f} mi | {hrs_str}")

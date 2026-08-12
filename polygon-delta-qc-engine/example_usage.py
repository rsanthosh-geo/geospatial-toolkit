"""
Example: build genuine synthetic shapefiles (not just DataFrames) for a
"reference" (model) and "comparison" (QC-corrected) dataset across two
feeders, with deliberate, known differences — then run the comparison
and verify the output against the ground truth we control. This also
exercises the dependency-free raw-DBF reader against real shapefiles
written by a different library (geopandas/fiona), which is the
strongest possible test of that reader.
"""
import os
import shutil
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt

from polygon_delta_qc_engine import compare_polygon_datasets, ShapefileReader


def make_feeder_shapefile(path, features):
    """features: list of dicts with treeid, treearea (None for a NULL-attribute polygon)."""
    geoms, treeids, treeareas = [], [], []
    for i, feat in enumerate(features):
        # Simple square polygon, offset per feature so geometries are distinct
        x = i * 10
        geoms.append(Polygon([(x, 0), (x + 5, 0), (x + 5, 5), (x, 5)]))
        treeids.append(feat.get("treeid"))
        treeareas.append(feat.get("treearea"))

    gdf = gpd.GeoDataFrame({"treeid": treeids, "treearea": treeareas}, geometry=geoms, crs="EPSG:3857")
    gdf.to_file(path)


if __name__ == "__main__":
    base = "sample_data"
    if os.path.exists(base):
        shutil.rmtree(base)

    # --- Feeder FDR-201: reference has 5 features, QC removed 2 (deletions) ---
    os.makedirs(f"{base}/model/FDR-201", exist_ok=True)
    os.makedirs(f"{base}/qc/FDR-201", exist_ok=True)

    ref_features_201 = [
        {"treeid": "T1", "treearea": 12.5}, {"treeid": "T2", "treearea": 8.0},
        {"treeid": "T3", "treearea": 15.2}, {"treeid": "T4", "treearea": 6.7},
        {"treeid": "T5", "treearea": 9.9},
    ]
    # QC kept only T1, T3, T5 -> 2 deletions
    qc_features_201 = [
        {"treeid": "T1", "treearea": 12.5}, {"treeid": "T3", "treearea": 15.2},
        {"treeid": "T5", "treearea": 9.9},
    ]

    make_feeder_shapefile(f"{base}/model/FDR-201/FDR-201_model.shp", ref_features_201)
    make_feeder_shapefile(f"{base}/qc/FDR-201/FDR-201_qc.shp", qc_features_201)

    # --- Feeder FDR-202: reference has 3 features incl. 1 NULL polygon, QC has all 3 + kept the NULL one ---
    os.makedirs(f"{base}/model/FDR-202", exist_ok=True)
    os.makedirs(f"{base}/qc/FDR-202", exist_ok=True)

    ref_features_202 = [
        {"treeid": "T10", "treearea": 20.0}, {"treeid": "T11", "treearea": 5.5},
        {"treeid": None, "treearea": None},  # NULL polygon
    ]
    qc_features_202 = [
        {"treeid": "T10", "treearea": 20.0}, {"treeid": "T11", "treearea": 5.5},
        {"treeid": None, "treearea": None},
    ]

    make_feeder_shapefile(f"{base}/model/FDR-202/FDR-202_model.shp", ref_features_202)
    make_feeder_shapefile(f"{base}/qc/FDR-202/FDR-202_qc.shp", qc_features_202)

    print("Created synthetic shapefiles:")
    print("  FDR-201: 5 reference features, QC kept 3 -> expect 2 deletions")
    print("  FDR-202: 3 reference features (incl. 1 NULL), QC kept all 3 -> expect 0 deletions")

    # --- Sanity check: prove the dependency-free raw DBF reader works on ---
    # --- shapefiles written by a completely different library (fiona)   ---
    print("\nVerifying dependency-free DBF reader against geopandas-written files...")
    df_check = ShapefileReader.read_dbf_raw(f"{base}/model/FDR-201/FDR-201_model.dbf")
    print(f"  Raw DBF reader parsed {len(df_check)} records, columns: {list(df_check.columns)}")
    assert len(df_check) == 5, "Raw DBF reader record count mismatch!"
    print("  PASSED")

    # --- Run the actual comparison ---
    os.makedirs("sample_output", exist_ok=True)
    output_path = "sample_output/Polygon_Delta_QC_Report.xlsx"

    compare_polygon_datasets(
        f"{base}/model", f"{base}/qc", output_path,
        reference_label="Model", comparison_label="QC",
    )

    # --- Verify against known ground truth ---
    import pandas as pd
    summary = pd.read_excel(output_path, sheet_name="Summary")
    print("\n--- Summary sheet ---")
    print(summary.to_string(index=False))

    row_201 = summary[summary["Feeder"] == "FDR-201"].iloc[0]
    row_202 = summary[summary["Feeder"] == "FDR-202"].iloc[0]
    assert row_201["Deletion"] == 2, f"Expected 2 deletions for FDR-201, got {row_201['Deletion']}"
    assert row_202["Deletion"] == 0, f"Expected 0 deletions for FDR-202, got {row_202['Deletion']}"
    print("\nGround-truth verification PASSED: deletions match expected values exactly.")

    # --- Visual summary ---
    fig, ax = plt.subplots(figsize=(7, 4.5))
    feeders = summary["Feeder"]
    x = range(len(feeders))
    ax.bar([i - 0.2 for i in x], summary["Model Count"], width=0.4, label="Model (reference)", color="#1F4E78")
    ax.bar([i + 0.2 for i in x], summary["QC Count"], width=0.4, label="QC (comparison)", color="#2E7D32")
    ax.set_xticks(list(x))
    ax.set_xticklabels(feeders)
    ax.set_ylabel("Unique feature count")
    ax.set_title("Model vs QC feature counts, by feeder")
    ax.legend()
    plt.tight_layout()
    plt.savefig("delta_qc_demo.png", dpi=150)
    print("\nSaved demo image: delta_qc_demo.png")

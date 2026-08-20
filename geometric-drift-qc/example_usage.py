"""
Example: build synthetic raw/corrected pairs (lines and polygons) with
known, deliberate positional and angular shifts — some above threshold
(should flag), some below (should not) — run the comparison, and verify
every outcome against known ground truth.
"""
import os
import shutil
import math
import geopandas as gpd
from shapely.geometry import LineString, Polygon
from shapely.affinity import translate, rotate
import matplotlib.pyplot as plt

from geometric_drift_qc import flag_geometric_drift

if __name__ == "__main__":
    base = "sample_data"
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(base, exist_ok=True)

    # --- Lines: L1 unchanged, L2 small shift+rotation (below threshold),
    #             L3 large shift+rotation (above threshold, should flag) ---
    raw_lines = {
        "L1": LineString([(0, 0), (10, 0)]),
        "L2": LineString([(20, 0), (30, 0)]),
        "L3": LineString([(40, 0), (50, 0)]),
    }
    corrected_lines = {
        "L1": LineString([(0, 0), (10, 0)]),                                   # no change
        "L2": translate(rotate(raw_lines["L2"], 3, origin="centroid"), 1, 1),   # small shift + 3deg rotation
        "L3": translate(rotate(raw_lines["L3"], 25, origin="centroid"), 8, 8),  # large shift + 25deg rotation
    }

    # --- Polygons: P1 unchanged, P2 large shift (should flag) ---
    raw_polys = {
        "P1": Polygon([(0, 20), (10, 20), (10, 30), (0, 30)]),
        "P2": Polygon([(20, 20), (30, 20), (30, 30), (20, 30)]),
    }
    corrected_polys = {
        "P1": Polygon([(0, 20), (10, 20), (10, 30), (0, 30)]),                      # no change
        "P2": translate(raw_polys["P2"], 12, 12),                                    # large centroid shift
    }

    def make_gdf(lines_dict, polys_dict):
        ids = list(lines_dict.keys()) + list(polys_dict.keys())
        geoms = list(lines_dict.values()) + list(polys_dict.values())
        return gpd.GeoDataFrame({"feature_id": ids}, geometry=geoms, crs="EPSG:3857")

    raw_gdf = make_gdf(raw_lines, raw_polys)
    corr_gdf = make_gdf(corrected_lines, corrected_polys)

    raw_gdf.to_file(f"{base}/raw.geojson", driver="GeoJSON")
    corr_gdf.to_file(f"{base}/corrected.geojson", driver="GeoJSON")
    print("Created synthetic raw/corrected pairs: L1 (unchanged), L2 (small drift), L3 (large drift), "
          "P1 (unchanged), P2 (large drift)")

    os.makedirs("sample_output", exist_ok=True)
    result = flag_geometric_drift(
        f"{base}/raw.geojson", f"{base}/corrected.geojson", "feature_id",
        output_path="sample_output/drift_flags.geojson",
        distance_threshold=5.0, angle_threshold_deg=10.0,
    )

    # --- Verify against known ground truth ---
    by_id = result.set_index("feature_id")
    assert not by_id.loc["L1", "flagged"], "L1 (unchanged) should NOT be flagged"
    assert not by_id.loc["L2", "flagged"], "L2 (small drift) should NOT be flagged"
    assert by_id.loc["L3", "flagged"], "L3 (large drift) SHOULD be flagged"
    assert not by_id.loc["P1", "flagged"], "P1 (unchanged) should NOT be flagged"
    assert by_id.loc["P2", "flagged"], "P2 (large drift) SHOULD be flagged"

    print("\nGround-truth verification PASSED:")
    for fid in ["L1", "L2", "L3", "P1", "P2"]:
        row = by_id.loc[fid]
        print(f"  {fid} ({row['geom_type']}): distance={row['distance_shift']:.2f}, "
              f"angle={row['angle_change_deg']}, flagged={row['flagged']}")

    # --- Visual proof ---
    fig, ax = plt.subplots(figsize=(9, 5))
    raw_gdf.plot(ax=ax, color="gray", linewidth=1.5, linestyle="--", label="Raw")
    for fid in by_id.index:
        color = "red" if by_id.loc[fid, "flagged"] else "green"
        geom = corr_gdf[corr_gdf["feature_id"] == fid].geometry.iloc[0]
        gpd.GeoSeries([geom]).plot(ax=ax, color=color, linewidth=2)
        c = geom.centroid
        ax.annotate(fid, (c.x, c.y), fontsize=9, weight="bold",
                    xytext=(0, 8), textcoords="offset points", ha="center")

    handles = [
        plt.Line2D([0], [0], color="gray", linestyle="--", label="Raw"),
        plt.Line2D([0], [0], color="green", label="Corrected — within threshold"),
        plt.Line2D([0], [0], color="red", label="Corrected — flagged for QC"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8)
    ax.set_title("Geometric drift QC: raw (dashed gray) vs. corrected (green=ok, red=flagged)")
    ax.set_aspect("equal")
    plt.tight_layout()
    plt.savefig("drift_qc_demo.png", dpi=150)
    print("\nSaved demo image: drift_qc_demo.png")

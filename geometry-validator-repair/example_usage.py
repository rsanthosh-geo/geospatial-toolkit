"""
Example: build a synthetic dataset with known geometry defects — a
classic self-intersecting "bowtie" polygon, a polygon with duplicate
vertices, a valid polygon, and a sliver too thin to be a real feature —
run the repair pipeline, and verify each one resolves exactly as
expected. Not just a visual demo: every outcome is asserted against
known ground truth.
"""
import os
import shutil
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt

from geometry_validator_repair import repair_geometries

if __name__ == "__main__":
    base = "sample_data"
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(base, exist_ok=True)

    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])
    assert not bowtie.is_valid, "Test setup error: bowtie should be invalid"

    dup_verts = Polygon([
        (20, 0), (20.0000001, 0), (30, 0), (30, 10), (20, 10), (20, 0)
    ])

    clean_poly = Polygon([(40, 0), (50, 0), (50, 10), (40, 10), (40, 0)])

    sliver = Polygon([(60, 0), (60.001, 0), (60.001, 10), (60, 10), (60, 0)])

    gdf = gpd.GeoDataFrame(
        {"name": ["bowtie", "dup_vertices", "clean", "sliver"]},
        geometry=[bowtie, dup_verts, clean_poly, sliver],
        crs="EPSG:3857",
    )
    input_path = f"{base}/test_geometries.geojson"
    gdf.to_file(input_path, driver="GeoJSON")
    print("Created 4 synthetic polygons: 1 self-intersecting, 1 with duplicate vertices, 1 clean, 1 sliver")

    os.makedirs("sample_output", exist_ok=True)
    n_kept, n_unfixable = repair_geometries(
        input_path,
        "sample_output/repaired.geojson",
        unfixable_path="sample_output/unfixable.geojson",
        preset="coarse",
    )

    repaired = gpd.read_file("sample_output/repaired.geojson")
    repaired_names = set(repaired["name"])

    assert "bowtie" in repaired_names, "Bowtie should have been repaired to a valid geometry"
    assert repaired[repaired["name"] == "bowtie"].geometry.iloc[0].is_valid, "Repaired bowtie must be valid"
    assert "dup_vertices" in repaired_names, "Duplicate-vertex polygon should survive repair"
    assert "clean" in repaired_names, "Already-valid polygon should pass through"
    assert "sliver" not in repaired_names, "Sliver should have been filtered out by the size filter"

    print("\nGround-truth verification PASSED:")
    print("  - Self-intersecting bowtie -> repaired to valid geometry")
    print("  - Duplicate-vertex polygon -> cleaned and kept")
    print("  - Already-valid polygon -> passed through")
    print("  - Sliver polygon -> correctly filtered out")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    gdf.plot(ax=axes[0], facecolor="none", edgecolor="red", linewidth=1.5)
    for _, row in gdf.iterrows():
        c = row.geometry.centroid
        axes[0].annotate(row["name"], (c.x, c.y), ha="center", fontsize=8)
    axes[0].set_title("Before: bowtie (invalid), dup-vertices, clean, sliver")
    axes[0].set_axis_off()

    repaired.plot(ax=axes[1], facecolor="lightgreen", edgecolor="darkgreen", linewidth=1.5)
    for _, row in repaired.iterrows():
        c = row.geometry.centroid
        axes[1].annotate(row["name"], (c.x, c.y), ha="center", fontsize=8)
    axes[1].set_title("After: repaired + sliver filtered out")
    axes[1].set_axis_off()

    plt.tight_layout()
    plt.savefig("repair_demo.png", dpi=150)
    print("\nSaved demo image: repair_demo.png")

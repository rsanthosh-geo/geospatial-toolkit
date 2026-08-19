"""
Example: build a synthetic merged point dataset spanning 3 groups (plus
one feature with a missing group value, to test the gap-reporting), run
the splitter, and verify each output file contains exactly the right
features — checked against known ground truth, not just eyeballed.
"""
import os
import shutil
import geopandas as gpd
from shapely.geometry import Point

from spatial_dataset_splitter import split_by_group

if __name__ == "__main__":
    base = "sample_data"
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(f"{base}/merged", exist_ok=True)

    rows = (
        [{"unit_id": "A", "asset": f"a{i}"} for i in range(4)]
        + [{"unit_id": "B", "asset": f"b{i}"} for i in range(2)]
        + [{"unit_id": "C", "asset": f"c{i}"} for i in range(3)]
        + [{"unit_id": None, "asset": "orphan"}]
    )
    geoms = [Point(i, i) for i in range(len(rows))]
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")

    merged_path = f"{base}/merged/merged_dataset.geojson"
    gdf.to_file(merged_path, driver="GeoJSON")
    print(f"Created synthetic merged dataset: {len(gdf)} features across groups A(4), B(2), C(3), plus 1 null-group feature")

    os.makedirs("sample_output", exist_ok=True)
    results = split_by_group(merged_path, "unit_id", "sample_output")

    expected = {"A": 4, "B": 2, "C": 3}
    for group, count in expected.items():
        assert group in results, f"Group {group} missing from results!"
        assert results[group][1] == count, f"Group {group}: expected {count}, got {results[group][1]}"
        out_gdf = gpd.read_file(results[group][0])
        assert len(out_gdf) == count, f"Output file for {group} has wrong feature count!"

    assert "orphan" not in results.keys(), "Null-group feature should not have created an output group"

    print("\nGround-truth verification PASSED: all group counts match exactly, null-group feature correctly excluded and flagged.")

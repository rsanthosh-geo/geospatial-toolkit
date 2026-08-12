"""
Example: generate a synthetic line network and a set of nearby points
(some within snap threshold, some deliberately too far), run the
snapping tool, and visualize before/after. Fully synthetic - no real
network data required to try this out.
"""
import geopandas as gpd
import numpy as np
from shapely.geometry import Point, LineString
import matplotlib.pyplot as plt

from spatial_feature_snapping import snap_points_to_lines


def make_synthetic_data(seed=3):
    rng = np.random.default_rng(seed)

    # A simple zig-zag line network (stand-in for a road/conductor/pipeline network)
    line = LineString([(0, 0), (10, 5), (20, 2), (30, 8), (40, 4)])
    lines = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")

    # Vertices of that line — points will be scattered near some of them
    vertex_coords = list(line.coords)

    points = []
    labels = []
    # Points close to vertices (within threshold) — should snap
    for i, (vx, vy) in enumerate(vertex_coords):
        offset = rng.uniform(-3, 3, size=2)
        points.append(Point(vx + offset[0], vy + offset[1]))
        labels.append(f"near_vertex_{i}")
    # Points deliberately far away — should NOT snap
    for i in range(3):
        points.append(Point(rng.uniform(0, 40), rng.uniform(20, 30)))
        labels.append(f"far_{i}")

    points_gdf = gpd.GeoDataFrame({"label": labels}, geometry=points, crs="EPSG:3857")
    return points_gdf, lines


if __name__ == "__main__":
    points, lines = make_synthetic_data()
    points.to_file("sample_data/points.geojson", driver="GeoJSON")
    lines.to_file("sample_data/lines.geojson", driver="GeoJSON")
    print(f"Created synthetic data: {len(points)} points, 1 line ({len(lines.geometry[0].coords)} vertices)")

    result = snap_points_to_lines(
        points, lines, snap_threshold=6.0,
        output_path="sample_output/points_snapped.geojson",
    )

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    for ax, gdf, title in [
        (axes[0], points, "Before: original point positions"),
        (axes[1], result, "After: snapped to nearest vertex (threshold=6.0)"),
    ]:
        lines.plot(ax=ax, color="steelblue", linewidth=2, zorder=1)
        line_verts = gpd.GeoDataFrame(
            geometry=[Point(c) for c in lines.geometry[0].coords], crs=lines.crs
        )
        line_verts.plot(ax=ax, color="steelblue", markersize=40, zorder=2)

        if "snapped" in gdf.columns:
            snapped = gdf[gdf["snapped"] == "Yes"]
            unchanged = gdf[gdf["snapped"] == "No"]
            snapped.plot(ax=ax, color="green", markersize=50, zorder=3, label="Snapped")
            unchanged.plot(ax=ax, color="red", markersize=50, zorder=3, label="Unchanged (beyond threshold)")
            ax.legend(loc="upper left", fontsize=8)
        else:
            gdf.plot(ax=ax, color="orange", markersize=50, zorder=3)

        ax.set_title(title)
        ax.set_axis_off()

    plt.tight_layout()
    plt.savefig("snapping_demo.png", dpi=150)
    print("\nSaved demo image: snapping_demo.png")

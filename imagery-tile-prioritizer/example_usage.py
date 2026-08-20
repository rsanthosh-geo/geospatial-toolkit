"""
Example: create 3 synthetic GeoTIFFs with embedded acquisition-date and
vendor metadata tags — 2 of which deliberately overlap the same ground
area (from different vendors, different dates), 1 standalone tile with
no overlap. Run the indexer and both priority methods, and verify the
results against known ground truth.
"""
import os
import shutil
import numpy as np
import rasterio
from rasterio.transform import from_origin
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from imagery_tile_prioritizer import build_tile_index, prioritize_overlapping_tiles, write_tile_index


def make_tile(path, origin_x, origin_y, size, acquisition_date, vendor):
    data = np.random.randint(0, 255, size=(size, size), dtype="uint8")
    transform = from_origin(origin_x, origin_y, 1, 1)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(acquisition_date=acquisition_date, vendor=vendor)


if __name__ == "__main__":
    base = "sample_data"
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(f"{base}/ZoneA", exist_ok=True)
    os.makedirs(f"{base}/ZoneB", exist_ok=True)

    # ZoneA: two OVERLAPPING tiles (same footprint), different vendor/date
    make_tile(f"{base}/ZoneA/vendorX_old.tif", 0, 10, 10, "2023-01-15", "VendorX")
    make_tile(f"{base}/ZoneA/vendorY_new.tif", 0, 10, 10, "2025-06-01", "VendorY")

    # ZoneB: one standalone tile, no overlap with anything
    make_tile(f"{base}/ZoneB/vendorX_solo.tif", 50, 10, 10, "2024-03-10", "VendorX")

    print("Created 3 synthetic tiles: 2 overlapping (ZoneA, different vendor/date), 1 standalone (ZoneB)")

    index = build_tile_index(base)

    # --- Test 1: recency method ---
    ranked_recency = prioritize_overlapping_tiles(index, method="recency")
    zoneA = ranked_recency[ranked_recency["group_id"] == "ZoneA"]
    newer = zoneA[zoneA["vendor"] == "VendorY"].iloc[0]
    older = zoneA[zoneA["vendor"] == "VendorX"].iloc[0]
    assert newer["priority_rank"] == 1, f"Newer tile (VendorY, 2025) should be priority 1, got {newer['priority_rank']}"
    assert older["priority_rank"] == 2, f"Older tile (VendorX, 2023) should be priority 2, got {older['priority_rank']}"

    solo = ranked_recency[ranked_recency["group_id"] == "ZoneB"].iloc[0]
    assert solo["priority_rank"] == 1, "Standalone tile with no overlap should trivially be priority 1"
    print("\n[recency method] PASSED: newer VendorY tile ranked above older VendorX tile; standalone tile unaffected.")

    # --- Test 2: vendor_order method (VendorX preferred regardless of date) ---
    ranked_vendor = prioritize_overlapping_tiles(index, method="vendor_order", vendor_order=["VendorX", "VendorY"])
    zoneA_v = ranked_vendor[ranked_vendor["group_id"] == "ZoneA"]
    x_tile = zoneA_v[zoneA_v["vendor"] == "VendorX"].iloc[0]
    y_tile = zoneA_v[zoneA_v["vendor"] == "VendorY"].iloc[0]
    assert x_tile["priority_rank"] == 1, f"VendorX should win under vendor_order despite being older, got {x_tile['priority_rank']}"
    assert y_tile["priority_rank"] == 2, f"VendorY should be ranked 2 under vendor_order, got {y_tile['priority_rank']}"
    print("[vendor_order method] PASSED: VendorX correctly wins despite being the older tile, per the specified order.")

    os.makedirs("sample_output", exist_ok=True)
    write_tile_index(ranked_recency, "sample_output/tile_index_recency.geojson")
    write_tile_index(ranked_vendor, "sample_output/tile_index_vendor_order.geojson")

    # --- Visual: footprints colored by recency priority ---
    # ZoneA's two tiles share an identical footprint by design (true overlap
    # test) — draw one solid, one hatched, with offset labels so both are
    # legible rather than rendering as indistinguishable stacked text.
    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = {1: "#2E7D32", 2: "#C62828"}

    zoneA_rows = ranked_recency[ranked_recency["group_id"] == "ZoneA"].sort_values("priority_rank")
    hatches = ["", "///"]
    label_offsets = [1.5, -2.5]
    for (_, row), hatch, y_off in zip(zoneA_rows.iterrows(), hatches, label_offsets):
        x, y = row.geometry.exterior.xy
        color = colors.get(row["priority_rank"], "gray")
        ax.fill(x, y, alpha=0.35, facecolor=color, edgecolor=color, linewidth=2, hatch=hatch)
        cx, cy = row.geometry.centroid.x, row.geometry.centroid.y
        ax.annotate(f"{row['vendor']} ({row['acquisition_date']}) - rank {row['priority_rank']}",
                    (cx, cy + y_off), ha="center", fontsize=8, weight="bold" if row["priority_rank"] == 1 else "normal")

    zoneB_row = ranked_recency[ranked_recency["group_id"] == "ZoneB"].iloc[0]
    x, y = zoneB_row.geometry.exterior.xy
    ax.fill(x, y, alpha=0.35, facecolor=colors[1], edgecolor=colors[1], linewidth=2)
    cx, cy = zoneB_row.geometry.centroid.x, zoneB_row.geometry.centroid.y
    ax.annotate(f"{zoneB_row['vendor']} ({zoneB_row['acquisition_date']}) - rank 1\n(no overlap)",
                (cx, cy), ha="center", fontsize=8, weight="bold")

    ax.set_title("ZoneA: two overlapping tiles (hatched = lower priority) | ZoneB: standalone tile")
    ax.set_xlim(-5, 65)
    ax.set_ylim(0, 25)
    plt.tight_layout()
    plt.savefig("tile_priority_demo.png", dpi=150)
    print("\nSaved demo image: tile_priority_demo.png")

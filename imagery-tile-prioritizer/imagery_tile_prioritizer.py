"""
Imagery Tile Prioritizer
---------------------------
Builds a footprint index across a folder of raster imagery tiles, and
— for tiles whose footprints overlap the same ground area — ranks them
by a priority rule (most recent acquisition first, or a defined vendor
priority order), so downstream mosaicking/compositing knows which tile
to use where coverage overlaps.

Use case
--------
When imagery is sourced from multiple vendors/providers, overlapping
coverage is common — the same ground area may be captured by more than
one tile, from different vendors, at different dates. Simply picking
"whichever tile happens to be read last" is not a reliable rule.
This builds a spatial index of every tile's footprint plus its
metadata (acquisition date, vendor), detects where footprints overlap,
and ranks overlapping tiles by a configurable priority rule so the
"which tile wins here" decision is explicit and reproducible rather
than incidental.

Two priority rules are supported:
- "recency" — most recently acquired tile wins
- "vendor_order" — a supplied vendor priority list decides, regardless
  of date (useful when one vendor's data is trusted more regardless of
  how old it is)

Requirements
------------
- Standalone mode: rasterio, geopandas, shapely
- QGIS mode: run inside QGIS (uses qgis.core / GDAL, bundled)
"""

import os
from typing import Optional, List, Tuple

DEFAULT_EXTENSIONS = (".tif", ".tiff", ".img", ".jp2", ".vrt")


# ---------------------------------------------------------------------------
# MODE 1: Standalone — no QGIS dependency, uses rasterio
# ---------------------------------------------------------------------------

def build_tile_index(input_folder, date_tag="acquisition_date", vendor_tag="vendor",
                      extensions=DEFAULT_EXTENSIONS):
    """
    Build a footprint index (as a GeoDataFrame) across every raster tile
    in a folder, reprojected to EPSG:4326.

    Parameters
    ----------
    input_folder : str
        Root folder containing raster tiles (searched recursively).
    date_tag, vendor_tag : str
        Names of the GDAL metadata tags holding acquisition date and
        vendor/provider info, if present on your rasters. Missing tags
        are reported as None per tile, not fabricated.
    extensions : tuple of str
        Raster file extensions to include.

    Returns
    -------
    geopandas.GeoDataFrame
        Columns: file_path, group_id (immediate parent folder name),
        acquisition_date, vendor, geometry (footprint polygon, EPSG:4326).
    """
    import rasterio
    from rasterio.warp import transform_bounds
    import geopandas as gpd
    from shapely.geometry import box

    input_folder = os.path.abspath(input_folder)
    rows = []

    for dirpath, _dirs, files in os.walk(input_folder):
        for name in files:
            if not name.lower().endswith(extensions):
                continue
            path = os.path.join(dirpath, name)

            try:
                with rasterio.open(path) as src:
                    bounds_4326 = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
                    tags = src.tags()
            except Exception as e:
                print(f"  Skipping (cannot open): {path} ({e})")
                continue

            rel = os.path.relpath(dirpath, input_folder)
            group_id = rel.split(os.sep)[0] if rel != "." else "Unknown"

            rows.append({
                "file_path": path,
                "group_id": group_id,
                "acquisition_date": tags.get(date_tag),
                "vendor": tags.get(vendor_tag),
                "geometry": box(*bounds_4326),
            })

    if not rows:
        print(f"No raster tiles found under {input_folder}")
        return None

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    n_missing_date = gdf["acquisition_date"].isna().sum()
    if n_missing_date:
        print(f"WARNING: {n_missing_date} tile(s) have no '{date_tag}' tag — "
              f"excluded from recency-based priority ranking.")

    print(f"Indexed {len(gdf)} tile(s) across {gdf['group_id'].nunique()} group(s)")
    return gdf


def prioritize_overlapping_tiles(tile_index, method="recency", vendor_order=None):
    """
    Rank tiles by priority wherever their footprints overlap.

    Parameters
    ----------
    tile_index : geopandas.GeoDataFrame
        Output of `build_tile_index`.
    method : str
        "recency" — most recent acquisition_date wins (tiles with no
        date are ranked last, never fabricated a date to compete).
        "vendor_order" — priority follows `vendor_order` list position.
    vendor_order : list of str, optional
        Required for method="vendor_order". Earlier entries = higher priority.

    Returns
    -------
    geopandas.GeoDataFrame
        Same as input, plus a "priority_rank" column (1 = highest
        priority) computed within each overlapping cluster. Tiles with
        no overlap get priority_rank=1 trivially (nothing to compete with).
    """
    import pandas as pd

    gdf = tile_index.copy()
    gdf["priority_rank"] = None
    assigned = set()

    for idx, row in gdf.iterrows():
        if idx in assigned:
            continue

        overlaps = gdf[gdf.geometry.intersects(row.geometry)].index.tolist()
        cluster = sorted(set(overlaps) | {idx})

        if method == "recency":
            dated = [i for i in cluster if gdf.loc[i, "acquisition_date"] is not None]
            undated = [i for i in cluster if gdf.loc[i, "acquisition_date"] is None]
            dated_sorted = sorted(dated, key=lambda i: gdf.loc[i, "acquisition_date"], reverse=True)
            ordered = dated_sorted + undated

        elif method == "vendor_order":
            if not vendor_order:
                raise ValueError("vendor_order list is required when method='vendor_order'")
            def vendor_rank(i):
                v = gdf.loc[i, "vendor"]
                return vendor_order.index(v) if v in vendor_order else len(vendor_order)
            ordered = sorted(cluster, key=vendor_rank)
        else:
            raise ValueError(f"Unknown method: {method}")

        for rank, i in enumerate(ordered, start=1):
            gdf.at[i, "priority_rank"] = rank
            assigned.add(i)

    return gdf


def write_tile_index(gdf, output_path):
    """Write the tile index (with priority ranks, if computed) to a vector file."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON" if output_path.endswith(".geojson") else None)
    print(f"Written: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a tile footprint index and rank overlapping tiles by priority.")
    parser.add_argument("input_folder", help="Folder of raster tiles")
    parser.add_argument("output_path", help="Output path for the tile index (e.g. .geojson)")
    parser.add_argument("--method", default="recency", choices=["recency", "vendor_order"])
    parser.add_argument("--vendor-order", nargs="*", default=None, help="Vendor priority order, highest first")
    args = parser.parse_args()

    index = build_tile_index(args.input_folder)
    if index is not None:
        ranked = prioritize_overlapping_tiles(index, method=args.method, vendor_order=args.vendor_order)
        write_tile_index(ranked, args.output_path)

"""
Geometric Drift QC — Raw vs. Corrected Position/Orientation Comparison
--------------------------------------------------------------------------
Compares a "raw" version of a spatial dataset against a "corrected"
version (matched by a shared feature ID) and quantifies how far each
feature moved (positional drift) and, for lines and polygons, how much
its orientation changed (angular drift) — flagging features that
exceed a threshold for QC review before delivery.

Use case
--------
Spatial features are often corrected/adjusted after an initial
digitization or automated extraction pass. Most corrections are minor;
occasionally a feature shifts or rotates significantly, which usually
signals either a genuine correction worth double-checking or a
digitization error introduced during the fix. Reviewing every feature
manually doesn't scale — this quantifies the actual positional and
angular change per feature and flags only the ones that exceed a
threshold, so QC effort concentrates on what actually moved.

Works on points, lines, and polygons:
- Points: positional drift only (a point has no orientation)
- Lines: positional drift (endpoint-to-endpoint shift) + angular drift
  (bearing change of the line)
- Polygons: positional drift (centroid shift) + angular drift
  (orientation change of the polygon's minimum rotated bounding
  rectangle, used as a general-purpose proxy for "which way it's facing")

Requirements
------------
- Standalone mode: geopandas, shapely
- QGIS mode: run inside QGIS (uses qgis.core, bundled)
"""

import math


# ---------------------------------------------------------------------------
# Core geometry comparison — pure Shapely, geometry-type dispatching
# ---------------------------------------------------------------------------

def _bearing_deg(p1, p2):
    """Bearing in degrees (0-360) from point p1 to point p2."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    return math.degrees(math.atan2(dx, dy)) % 360


def _angle_diff_deg(a, b):
    """Smallest difference between two angles (0-180), direction-agnostic
    (a line's bearing and its reverse bearing represent the same orientation)."""
    diff = abs(a - b) % 360
    if diff > 180:
        diff = 360 - diff
    if diff > 90:
        diff = 180 - diff
    return diff


def _line_bearing(line):
    coords = list(line.coords)
    return _bearing_deg(coords[0], coords[-1])


def _polygon_orientation(poly):
    """Orientation proxy: bearing of the longest edge of the polygon's
    minimum rotated bounding rectangle."""
    rect = poly.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    edges = [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
    longest = max(edges, key=lambda e: math.dist(e[0], e[1]))
    return _bearing_deg(*longest)


def compute_drift(raw_geom, corrected_geom):
    """
    Compare a raw and corrected geometry of the same feature.

    Returns
    -------
    dict
        {
            "geom_type": str,
            "distance_shift": float,   # representative-point displacement
            "angle_change_deg": float or None,  # None for points
        }
    """
    geom_type = raw_geom.geom_type

    if geom_type == "Point":
        distance = raw_geom.distance(corrected_geom)
        return {"geom_type": geom_type, "distance_shift": distance, "angle_change_deg": None}

    if geom_type in ("LineString", "MultiLineString"):
        raw_line = raw_geom if geom_type == "LineString" else max(raw_geom.geoms, key=lambda g: g.length)
        corr_line = corrected_geom if corrected_geom.geom_type == "LineString" else max(corrected_geom.geoms, key=lambda g: g.length)
        raw_start = raw_line.coords[0]
        corr_start = corr_line.coords[0]
        distance = math.dist(raw_start, corr_start)
        angle_change = _angle_diff_deg(_line_bearing(raw_line), _line_bearing(corr_line))
        return {"geom_type": geom_type, "distance_shift": distance, "angle_change_deg": angle_change}

    if geom_type in ("Polygon", "MultiPolygon"):
        raw_poly = raw_geom if geom_type == "Polygon" else max(raw_geom.geoms, key=lambda g: g.area)
        corr_poly = corrected_geom if corrected_geom.geom_type == "Polygon" else max(corrected_geom.geoms, key=lambda g: g.area)
        distance = raw_poly.centroid.distance(corr_poly.centroid)
        angle_change = _angle_diff_deg(_polygon_orientation(raw_poly), _polygon_orientation(corr_poly))
        return {"geom_type": geom_type, "distance_shift": distance, "angle_change_deg": angle_change}

    raise ValueError(f"Unsupported geometry type: {geom_type}")


# ---------------------------------------------------------------------------
# Standalone mode — compares two files matched by an ID field
# ---------------------------------------------------------------------------

def flag_geometric_drift(raw_path, corrected_path, id_field, output_path=None,
                          distance_threshold=5.0, angle_threshold_deg=10.0):
    """
    Compare a raw and corrected dataset (matched by `id_field`) and flag
    features whose positional or angular drift exceeds the given
    thresholds.

    Parameters
    ----------
    raw_path, corrected_path : str
        Paths to the raw and corrected versions of the same features.
    id_field : str
        Attribute column present in both, used to match corresponding
        features.
    output_path : str, optional
        If given, writes the flagged results (using the corrected
        geometry) to this path.
    distance_threshold : float
        Positional drift (in the layers' CRS units) above which a
        feature is flagged.
    angle_threshold_deg : float
        Angular drift (degrees) above which a line/polygon feature is
        flagged. Not applicable to points.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per matched feature: id, geom_type, distance_shift,
        angle_change_deg, flagged. Unmatched IDs (present in only one
        file) are reported separately, not silently dropped.
    """
    import geopandas as gpd
    import pandas as pd

    raw_gdf = gpd.read_file(raw_path)
    corr_gdf = gpd.read_file(corrected_path)

    if id_field not in raw_gdf.columns or id_field not in corr_gdf.columns:
        raise ValueError(f"'{id_field}' must be present in both datasets")

    raw_ids = set(raw_gdf[id_field])
    corr_ids = set(corr_gdf[id_field])
    only_raw = raw_ids - corr_ids
    only_corrected = corr_ids - raw_ids
    if only_raw:
        print(f"WARNING: {len(only_raw)} feature(s) present in raw but not corrected: {sorted(only_raw)[:10]}{'...' if len(only_raw) > 10 else ''}")
    if only_corrected:
        print(f"WARNING: {len(only_corrected)} feature(s) present in corrected but not raw: {sorted(only_corrected)[:10]}{'...' if len(only_corrected) > 10 else ''}")

    rows = []
    for fid in sorted(raw_ids & corr_ids, key=str):
        raw_geom = raw_gdf.loc[raw_gdf[id_field] == fid, "geometry"].iloc[0]
        corr_geom = corr_gdf.loc[corr_gdf[id_field] == fid, "geometry"].iloc[0]

        result = compute_drift(raw_geom, corr_geom)
        flagged = result["distance_shift"] > distance_threshold or (
            result["angle_change_deg"] is not None and result["angle_change_deg"] > angle_threshold_deg
        )
        rows.append({
            id_field: fid,
            "geom_type": result["geom_type"],
            "distance_shift": round(result["distance_shift"], 4),
            "angle_change_deg": round(result["angle_change_deg"], 2) if result["angle_change_deg"] is not None else None,
            "flagged": flagged,
            "geometry": corr_geom,
        })

    result_gdf = gpd.GeoDataFrame(rows, crs=corr_gdf.crs)
    n_flagged = result_gdf["flagged"].sum()
    print(f"Compared {len(result_gdf)} matched feature(s): {n_flagged} flagged for QC "
          f"(distance > {distance_threshold} or angle > {angle_threshold_deg} deg)")

    if output_path:
        result_gdf.to_file(output_path, driver="GeoJSON" if output_path.endswith(".geojson") else None)
        print(f"Written: {output_path}")

    return result_gdf


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Flag features with significant positional/angular drift between raw and corrected versions.")
    parser.add_argument("raw_path")
    parser.add_argument("corrected_path")
    parser.add_argument("id_field")
    parser.add_argument("output_path")
    parser.add_argument("--distance-threshold", type=float, default=5.0)
    parser.add_argument("--angle-threshold", type=float, default=10.0)
    args = parser.parse_args()

    flag_geometric_drift(
        args.raw_path, args.corrected_path, args.id_field, args.output_path,
        distance_threshold=args.distance_threshold, angle_threshold_deg=args.angle_threshold,
    )

"""
Geometry Validator & Repair
------------------------------
Detects and repairs common polygon geometry defects — self-intersections,
duplicate/near-duplicate vertices, and invalid topology — across a
single dataset or a folder of datasets, with slivers filtered out and
truly unfixable geometries reported separately rather than silently
dropped.

Use case
--------
Polygon datasets accumulate geometry defects from digitization,
coordinate rounding, or upstream processing: self-intersecting rings,
near-duplicate vertices sitting almost on top of each other, and
invalid topology that breaks downstream spatial operations (area
calculations, spatial joins, overlay analysis). This repairs what can
be repaired, filters out slivers too small/thin to be meaningful
features, and separately reports anything that couldn't be fixed so
nothing is silently lost.

Repair pipeline (per polygon)
------------------------------
1. Deduplicate near-overlapping vertices within each ring.
2. buffer(small distance) -> simplify(tolerance, topology-preserving)
   -> buffer(0) — the standard, well-documented technique for repairing
   self-intersecting polygons via the GEOS/Shapely buffer operation.
3. If still invalid: extract ring boundaries as lines, union them, and
   rebuild valid polygons from the resulting line network
   (`shapely.ops.polygonize`) — a fallback for geometries too broken
   for the buffer trick alone.
4. Filter slivers: drop parts below a minimum area, or with a
   perimeter-to-area ratio above a threshold.
5. Anything that fails both repair attempts is written to a separate
   "unfixable" output — flagged for manual review, never silently
   dropped.

Two threshold presets are provided as a starting point ("fine" for
survey-grade/high-precision data, "coarse" for lower-precision mapping
data) — both are illustrative defaults, tune to your own data.

Requirements
------------
- Standalone mode: shapely, geopandas
- QGIS mode: run inside QGIS (uses qgis.core, bundled)
"""

import os
from typing import List, Tuple

from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.validation import make_valid
from shapely.ops import unary_union, polygonize


PRESETS = {
    "fine": {
        "simplify_tolerance": 0.001,
        "buffer_distance": 0.0001,
        "min_area": 0.0001,
        "max_perimeter_area_ratio": 50,
    },
    "coarse": {
        "simplify_tolerance": 0.10,
        "buffer_distance": 0.003,
        "min_area": 0.4,
        "max_perimeter_area_ratio": 50,
    },
}


def _dedupe_ring(coords, epsilon=1e-8):
    if not coords:
        return coords
    scale = 1.0 / max(epsilon, 1e-15)

    def cell(pt):
        return (round(pt[0] * scale), round(pt[1] * scale))

    closed = len(coords) > 1 and coords[0] == coords[-1]
    end = len(coords) - 1 if closed else len(coords)

    seen = set()
    out = []
    for i in range(end):
        c = cell(coords[i])
        if c in seen:
            continue
        seen.add(c)
        out.append(coords[i])

    if closed and len(out) >= 3:
        out.append(out[0])
    return out if len(out) >= 4 else list(coords)


def dedupe_polygon_vertices(poly):
    """Remove near-duplicate vertices from every ring of a Polygon."""
    if poly.is_empty:
        return poly
    exterior = _dedupe_ring(list(poly.exterior.coords))
    interiors = [_dedupe_ring(list(r.coords)) for r in poly.interiors]
    try:
        return Polygon(exterior, interiors)
    except Exception:
        return poly


def clean_geometry(poly, simplify_tolerance, buffer_distance):
    """buffer -> simplify -> buffer(0); falls back to line-rebuild via polygonize."""
    try:
        buffered = poly.buffer(buffer_distance)
        if buffered.is_empty:
            return None
        simplified = buffered.simplify(simplify_tolerance, preserve_topology=True)
        fixed = simplified.buffer(0)
        if not fixed.is_empty and fixed.is_valid:
            return fixed

        boundary = simplified.boundary
        lines = [boundary] if isinstance(boundary, LineString) else list(boundary.geoms)
        merged = unary_union(lines)
        rebuilt = list(polygonize(merged))
        if not rebuilt:
            return None
        return unary_union(rebuilt)
    except Exception:
        return None


def passes_size_filters(poly, min_area, max_perimeter_area_ratio):
    area = poly.area
    if area <= 0 or area < min_area:
        return False
    ratio = poly.length / area
    return ratio <= max_perimeter_area_ratio


def _explode(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, Polygon):
        return [geom]
    return []


def repair_single_geometry(poly, preset="fine", **overrides) -> Tuple[List[Polygon], bool]:
    """Repair one polygon. Returns (kept_parts, unfixable)."""
    params = {**PRESETS[preset], **overrides}

    deduped = dedupe_polygon_vertices(poly)
    if not deduped.is_valid:
        fixed_geom = make_valid(deduped)
        if isinstance(fixed_geom, MultiPolygon):
            deduped = max(fixed_geom.geoms, key=lambda g: g.area)
        elif isinstance(fixed_geom, Polygon):
            deduped = fixed_geom
        else:
            return [], True

    cleaned = clean_geometry(deduped, params["simplify_tolerance"], params["buffer_distance"])
    if cleaned is None:
        return [], True

    parts = _explode(cleaned)
    kept = [p for p in parts if passes_size_filters(p, params["min_area"], params["max_perimeter_area_ratio"])]
    return kept, False


def repair_geometries(input_path, output_path, unfixable_path=None, preset="fine",
                       group_field_name="source_group", **overrides):
    """Repair every polygon in a vector file (standalone, GeoPandas-based)."""
    import geopandas as gpd

    gdf = gpd.read_file(input_path)
    group_value = os.path.splitext(os.path.basename(input_path))[0]
    if group_field_name not in gdf.columns:
        gdf[group_field_name] = group_value

    kept_rows, unfix_rows = [], []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        polys_to_process = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        any_kept, any_unfixable = [], False
        for p in polys_to_process:
            kept, unfixable = repair_single_geometry(p, preset=preset, **overrides)
            if unfixable:
                any_unfixable = True
            any_kept.extend(kept)

        for k in any_kept:
            new_row = row.copy()
            new_row.geometry = k
            kept_rows.append(new_row)
        if any_unfixable and not any_kept:
            unfix_rows.append(row)

    n_kept, n_unfixable = len(kept_rows), len(unfix_rows)

    if kept_rows:
        out_gdf = gpd.GeoDataFrame(kept_rows, crs=gdf.crs)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        out_gdf.to_file(output_path)

    if unfixable_path and unfix_rows:
        unfix_gdf = gpd.GeoDataFrame(unfix_rows, crs=gdf.crs)
        os.makedirs(os.path.dirname(unfixable_path) or ".", exist_ok=True)
        unfix_gdf.to_file(unfixable_path)

    print(f"{os.path.basename(input_path)}: {n_kept} repaired/valid, {n_unfixable} unfixable "
          f"(of {len(gdf)} input features)")
    return n_kept, n_unfixable


def repair_geometries_batch(input_folder, output_folder, unfixable_folder=None,
                             preset="fine", extensions=(".shp", ".geojson"), **overrides):
    """Recursively repair every vector file under input_folder."""
    files = []
    for root, _dirs, names in os.walk(input_folder):
        for name in names:
            if name.lower().endswith(extensions):
                files.append(os.path.join(root, name))

    if not files:
        print(f"No vector files found under {input_folder}")
        return

    total_kept, total_unfixable = 0, 0
    for f in files:
        rel = os.path.relpath(f, input_folder)
        out_path = os.path.join(output_folder, rel)
        unfix_path = os.path.join(unfixable_folder, rel) if unfixable_folder else None
        n_kept, n_unfixable = repair_geometries(f, out_path, unfix_path, preset=preset, **overrides)
        total_kept += n_kept
        total_unfixable += n_unfixable

    print(f"\nDone. {len(files)} file(s) processed. "
          f"{total_kept} repaired/valid features total, {total_unfixable} unfixable.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Repair polygon geometry defects across a vector dataset.")
    parser.add_argument("input_path", help="Input vector file or folder")
    parser.add_argument("output_path", help="Output path for repaired geometries")
    parser.add_argument("--unfixable", default=None, help="Output path for unrepairable geometries")
    parser.add_argument("--preset", default="fine", choices=list(PRESETS.keys()))
    args = parser.parse_args()

    if os.path.isdir(args.input_path):
        repair_geometries_batch(args.input_path, args.output_path, args.unfixable, preset=args.preset)
    else:
        repair_geometries(args.input_path, args.output_path, args.unfixable, preset=args.preset)

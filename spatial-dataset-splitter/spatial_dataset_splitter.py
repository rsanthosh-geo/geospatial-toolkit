"""
Spatial Dataset Splitter — Split a Merged Dataset by Group Attribute
-----------------------------------------------------------------------
Splits a single spatial dataset (points, lines, or polygons) containing
multiple groups merged into one file back into one output file per
group, based on a group-identifier attribute.

Use case
--------
Spatial data is often delivered or worked on as a single merged file
covering many logical units at once (e.g. multiple network segments,
survey zones, or delivery batches combined into one dataset for
convenience during editing). Before final delivery, the data typically
needs to be split back into one file per unit — this automates that
split for an arbitrary number of groups in a single pass, instead of
manually filtering and exporting each one.

Works on any geometry type (point, line, or polygon) and any group
field name — both are parameters, not assumptions baked into the code.

Two usage modes are provided:

1. Standalone (`split_by_group`) - pure Python (GeoPandas), no QGIS
   dependency. Works on any OGR-readable format.
2. QGIS Console (`split_by_group_qgis`) - operates on a layer already
   loaded in the active QGIS project.

Requirements
------------
- Standalone mode: geopandas
- QGIS mode: run inside QGIS (uses qgis.core, bundled)
"""

import os
import re


def _safe_filename(value):
    """Sanitize a group value into a filesystem-safe filename fragment."""
    s = str(value).strip()
    s = re.sub(r'[^A-Za-z0-9_\-]', '_', s)
    return s or "UNKNOWN"


# ---------------------------------------------------------------------------
# MODE 1: Standalone — no QGIS dependency
# ---------------------------------------------------------------------------

def split_by_group(input_path, group_field, output_folder, output_format="GeoJSON"):
    """
    Split a merged spatial dataset into one file per unique value of
    `group_field`. Works on any geometry type (point, line, polygon).

    Parameters
    ----------
    input_path : str
        Path to the merged input dataset (any OGR-readable format:
        shapefile, GeoJSON, GPKG, etc.).
    group_field : str
        Attribute column identifying which group each feature belongs to
        (e.g. a feeder ID, zone ID, batch ID — any grouping attribute).
    output_folder : str
        Destination folder; one output file per group is written here.
    output_format : str
        Output driver name for GeoPandas (`"GeoJSON"`, `"ESRI Shapefile"`,
        `"GPKG"`, etc.). Defaults to GeoJSON.

    Returns
    -------
    dict
        {group_value: (output_path, feature_count)} for every group written.
    """
    import geopandas as gpd

    gdf = gpd.read_file(input_path)
    if group_field not in gdf.columns:
        raise ValueError(
            f"Group field '{group_field}' not found. Available columns: {list(gdf.columns)}"
        )

    os.makedirs(output_folder, exist_ok=True)

    ext = {"GeoJSON": ".geojson", "ESRI Shapefile": ".shp", "GPKG": ".gpkg"}.get(output_format, ".geojson")

    results = {}
    groups = gdf[group_field].dropna().unique()
    print(f"Found {len(groups)} group(s) in '{group_field}'")

    for group_value in sorted(groups, key=str):
        subset = gdf[gdf[group_field] == group_value]
        safe_name = _safe_filename(group_value)
        out_path = os.path.join(output_folder, f"{safe_name}{ext}")
        subset.to_file(out_path, driver=output_format)
        results[group_value] = (out_path, len(subset))
        print(f"  {group_value}: {len(subset)} feature(s) -> {out_path}")

    n_missing = gdf[group_field].isna().sum()
    if n_missing:
        print(f"WARNING: {n_missing} feature(s) had a null '{group_field}' value and were not written to any output file.")

    return results


# ---------------------------------------------------------------------------
# MODE 2: QGIS Console — operates on a layer already loaded in the project
# ---------------------------------------------------------------------------

def split_by_group_qgis(layer_name, group_field, output_folder, output_format="GeoJSON"):
    """
    Split a loaded QGIS layer into one file per unique value of
    `group_field`. Mirrors `split_by_group` exactly, just sourced from
    the active QGIS project instead of a file path.
    """
    from qgis.core import QgsProject, QgsVectorFileWriter, QgsFeatureRequest

    layer = None
    for lyr in QgsProject.instance().mapLayers().values():
        if lyr.name() == layer_name:
            layer = lyr
            break

    if layer is None:
        available = [l.name() for l in QgsProject.instance().mapLayers().values()]
        print(f"Layer '{layer_name}' not found. Available layers: {available}")
        return {}

    field_names = [f.name() for f in layer.fields()]
    if group_field not in field_names:
        print(f"Group field '{group_field}' not found. Available fields: {field_names}")
        return {}

    os.makedirs(output_folder, exist_ok=True)
    field_idx = layer.fields().indexOf(group_field)

    groups = set()
    for feat in layer.getFeatures():
        val = feat[field_idx]
        if val is not None:
            groups.add(val)

    print(f"Found {len(groups)} group(s) in '{group_field}'")
    ext = {"GeoJSON": ".geojson", "ESRI Shapefile": ".shp", "GPKG": ".gpkg"}.get(output_format, ".geojson")

    results = {}
    for group_value in sorted(groups, key=str):
        expr = f'"{group_field}" = \'{group_value}\'' if isinstance(group_value, str) else f'"{group_field}" = {group_value}'
        request = QgsFeatureRequest().setFilterExpression(expr)

        safe_name = _safe_filename(group_value)
        out_path = os.path.join(output_folder, f"{safe_name}{ext}")

        transform_context = QgsProject.instance().transformContext()
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = output_format
        options.onlySelectedFeatures = False
        options.filterExpression = expr

        QgsVectorFileWriter.writeAsVectorFormatV3(layer, out_path, transform_context, options)
        count = sum(1 for _ in layer.getFeatures(request))
        results[group_value] = (out_path, count)
        print(f"  {group_value}: {count} feature(s) -> {out_path}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Split a merged spatial dataset into one file per group.")
    parser.add_argument("input_path", help="Merged input dataset (shapefile, GeoJSON, GPKG, etc.)")
    parser.add_argument("group_field", help="Attribute column identifying each feature's group")
    parser.add_argument("output_folder", help="Destination folder for split outputs")
    parser.add_argument("--format", default="GeoJSON", help="Output format (default: GeoJSON)")
    args = parser.parse_args()

    split_by_group(args.input_path, args.group_field, args.output_folder, args.format)

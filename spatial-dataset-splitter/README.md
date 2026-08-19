# Spatial Dataset Splitter

Splits a single merged spatial dataset (points, lines, or polygons)
back into one output file per group, based on a group-identifier
attribute — e.g. multiple network segments, survey zones, or delivery
batches that were combined into one file for editing convenience and
need to be split apart again before final delivery.

## The problem

Spatial data is often worked on as one merged file spanning multiple
logical units. Manually filtering and exporting each unit before
delivery is slow and error-prone at scale; this automates the split
for an arbitrary number of groups in a single pass.

## How it works

1. Read the merged dataset
2. Group features by the specified attribute column
3. Write one output file per unique group value
4. Report (not silently drop) any features with a missing group value —
   same honesty-about-gaps principle used throughout this toolkit

Works on **any geometry type** (point, line, polygon) and **any group
field name** — both are parameters you pass in, not assumptions baked
into the code.

## Demo — verified against known ground truth

`example_usage.py` builds a synthetic dataset with 3 known groups (4,
2, and 3 features respectively) plus one feature with a missing group
value, splits it, and asserts every output file has exactly the
expected feature count:
```
Found 3 group(s) in 'unit_id'
  A: 4 feature(s) -> sample_output/A.geojson
  B: 2 feature(s) -> sample_output/B.geojson
  C: 3 feature(s) -> sample_output/C.geojson
WARNING: 1 feature(s) had a null 'unit_id' value and were not written to any output file.

Ground-truth verification PASSED: all group counts match exactly, null-group feature correctly excluded and flagged.
```

## Usage

```python
from spatial_dataset_splitter import split_by_group

split_by_group(
    "merged_dataset.geojson",
    group_field="unit_id",       # your grouping attribute — any name
    output_folder="split_output",
    output_format="GeoJSON",     # or "ESRI Shapefile", "GPKG"
)
```

**QGIS Console mode** (operates on a layer already loaded in the project):
```python
from spatial_dataset_splitter import split_by_group_qgis

split_by_group_qgis("MyLayerName", "unit_id", "split_output")
```

**Command line:**
```bash
python spatial_dataset_splitter.py merged_dataset.geojson unit_id split_output --format GeoJSON
```

## Adapting this live to a different schema

If you're handed a new dataset with different attribute names (e.g. in
an interview or on a new project), there is exactly **one thing to
change** — the `group_field` argument itself:

```python
split_by_group("new_dataset.shp", group_field="zone_code", output_folder="out")
```

No other code needs to change. The function reads whatever column name
you pass in; it doesn't assume a fixed schema. If the field doesn't
exist, the error message lists every available column so you can
immediately see the correct name:
```
ValueError: Group field 'unit_id' not found. Available columns: ['zone_code', 'asset_type', 'geometry']
```

## Requirements

- **Standalone mode:** `geopandas`
- **QGIS mode:** run inside QGIS (uses `qgis.core`, bundled)

## Tech stack

Python, GeoPandas, QGIS API

## License

MIT

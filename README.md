# Geospatial Toolkit

Quality-control and automation tools for geospatial AI and delivery
workflows in utility vegetation management: model-output QC, imagery
preparation, and spatial network operations. Generalized from
production work in remote sensing and spatial data QC. Every tool
ships with a standalone mode (no proprietary or company-specific
dependency), a synthetic/reproducible demo, and an honest README about
what's illustrative versus measured.

## Model-output QC and ground truth

| Tool | What it does |
|---|---|
| [polygon-delta-qc-engine](polygon-delta-qc-engine/) | Quantifies correction volume between model output and human-corrected polygon sets, per feeder and feature ID. Dependency-free DBF parsing, ground-truth-verified against known test data |
| [geometric-drift-qc](geometric-drift-qc/) | Flags positional and angular displacement between raw and corrected geometries (points, lines, polygons) against thresholds |
| [geometry-validator-repair](geometry-validator-repair/) | Topology validation and repair: self-intersections, slivers, duplicate vertices. Unfixable features are reported, never dropped |

## Imagery preparation

| Tool | What it does |
|---|---|
| [raster-nodata-cleanup](raster-nodata-cleanup/) | Batch NoData-mask removal on satellite, aerial, and drone rasters. QGIS and standalone modes |
| [imagery-tile-prioritizer](imagery-tile-prioritizer/) | Tile footprint indexing with overlap-priority ranking (recency or vendor order) for multi-vendor imagery |
| [vegetation-extraction](vegetation-extraction/) | Excess Green Index vegetation-polygon extraction from RGB imagery |

## Network and delivery operations

| Tool | What it does |
|---|---|
| [spatial-feature-snapping](spatial-feature-snapping/) | 1:1 point-to-line-vertex conflation within a distance threshold |
| [spatial-dataset-splitter](spatial-dataset-splitter/) | Splits a merged spatial dataset into one file per group, any geometry type |
| [linear-network-delivery-estimator](linear-network-delivery-estimator/) | Per-feeder line-mile aggregation with a planning-level delivery-time estimate |

Each folder is self-contained: read its README for the problem it
solves, how it works, and how to run its demo yourself.

## Design principles across every tool here

- **Standalone by default** — most tools run outside QGIS entirely
  (pure Python: rasterio / GeoPandas / Shapely / pandas), with a QGIS
  Processing-framework mode available where it adds real value.
- **Every demo is runnable, not just described** — `example_usage.py`
  in each folder generates synthetic data, runs the tool, and produces
  the exact image or output shown in that tool's README.
- **Honest about estimates vs. measurements** — where a tool produces
  a planning-level heuristic (e.g. delivery-time estimates), the README
  and code say so explicitly rather than presenting it as precise.

## Tech stack

Python · GDAL / rasterio · GeoPandas / Shapely / scikit-image
· Google Earth Engine · pandas / openpyxl · PyQt5 · PyQGIS (optional QGIS-console modes)

## License

[MIT](LICENSE)

## Author

[Santhosh Kumar R](https://github.com/rsanthosh-geo) — see [profile](https://github.com/rsanthosh-geo) for background and contact.

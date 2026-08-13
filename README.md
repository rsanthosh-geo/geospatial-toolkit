# Geospatial Toolkit

Five open-source geospatial automation tools, generalized from real
production workflows in electrical T&D vegetation risk, remote sensing,
and spatial data QC. Every tool ships with a standalone mode (no
proprietary or company-specific dependency), a synthetic/reproducible
demo, and an honest README about what's illustrative versus measured.

## Tools

| Tool | What it does |
|---|---|
| [raster-nodata-cleanup](raster-nodata-cleanup/) | Batch NoData/white-patch removal from satellite, aerial, and drone imagery — QGIS and standalone modes |
| [vegetation-extraction](vegetation-extraction/) | Excess Green Index vegetation-polygon extraction from RGB imagery |
| [spatial-feature-snapping](spatial-feature-snapping/) | Point-to-line-vertex snapping with a strict 1:1 constraint |
| [line-miles-calculator](line-miles-calculator/) | Feeder line-miles aggregation with recency-based delivery-time estimation |
| [polygon-delta-qc-engine](polygon-delta-qc-engine/) | Shapefile delta QC — dependency-free DBF parsing, ground-truth-verified against known test data |

Each folder is self-contained: read its README for the problem it
solves, how it works, and how to run its demo yourself.

## Design principles across all five

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

Python · PyQGIS · GDAL / rasterio · GeoPandas / Shapely / scikit-image
· Google Earth Engine · pandas / openpyxl · PyQt5

## License

[MIT](LICENSE)

## Author

[Santhosh Kumar R](https://github.com/rsanthosh-geo) — see [profile](https://github.com/rsanthosh-geo) for background and contact.

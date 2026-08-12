"""
Raster NoData / White-Patch Cleanup
------------------------------------
Removes stale NoData masking from raster imagery that causes blank/white
patches to render over valid pixel data. Two usage modes are provided:

1. QGIS Console Mode  - operates on every raster layer currently loaded
   in an open QGIS project. Useful for interactive cleanup during a
   mapping session.
2. Standalone Batch Mode - operates on a folder of raster files directly
   via rasterio, with no QGIS dependency. Useful for automated pipelines
   processing large batches of imagery at once (an entire network of
   tiles in a single pass, rather than one file at a time).

Use case
--------
Multi-band satellite/aerial/drone imagery is sometimes delivered with an
embedded NoData value that does not match the actual valid data range,
or that masks pixels unnecessarily. GIS software then renders those
pixels as blank white patches, obscuring real ground features
underneath. Re-processing images one at a time is slow when working
across an entire imagery set; this tool clears the NoData flag across
an arbitrary number of rasters in a single pass.

Requirements
------------
- QGIS Console Mode: run inside the QGIS Python console (uses the
  bundled qgis.core API — no separate install needed).
- Standalone Batch Mode: pip install rasterio
"""

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# MODE 1: QGIS Console — operates on all raster layers currently loaded
# ---------------------------------------------------------------------------

def clean_qgis_project_layers():
    """
    Unset the NoData value on every band of every raster layer currently
    loaded in the active QGIS project. Run this from the QGIS Python
    Console.

    This does not delete or alter pixel values — it only clears the
    NoData flag so QGIS stops masking those pixels as blank/white.

    Returns
    -------
    int
        Number of raster layers processed.
    """
    from qgis.core import QgsProject, QgsRasterLayer

    cleaned = 0
    for layer in QgsProject.instance().mapLayers().values():
        if isinstance(layer, QgsRasterLayer):
            provider = layer.dataProvider()
            for band in range(1, layer.bandCount() + 1):
                provider.setNoDataValue(band, float("nan"))
            layer.triggerRepaint()
            cleaned += 1

    print(f"NoData value unset for {cleaned} raster layer(s) in the current project.")
    return cleaned


# ---------------------------------------------------------------------------
# MODE 2: Standalone batch mode — no QGIS dependency, works on a folder
# ---------------------------------------------------------------------------

def clean_raster_folder(input_folder, output_folder=None, extensions=(".tif", ".tiff")):
    """
    Batch-clear the NoData value across every raster file in a folder.

    Parameters
    ----------
    input_folder : str
        Folder containing raster files (e.g. a full imagery tile set).
    output_folder : str, optional
        Destination folder for cleaned rasters. If None, files are
        cleaned in place.
    extensions : tuple of str
        File extensions to process. Defaults to GeoTIFF.

    Returns
    -------
    list of str
        Paths to the rasters that were processed.
    """
    import rasterio

    input_folder = os.path.normpath(input_folder)
    rasters = [
        str(p) for p in Path(input_folder).glob("*")
        if p.suffix.lower() in extensions
    ]

    if not rasters:
        print(f"No rasters found in {input_folder}")
        return []

    if output_folder:
        output_folder = os.path.normpath(output_folder)
        os.makedirs(output_folder, exist_ok=True)

    processed = []
    for raster_path in rasters:
        name = Path(raster_path).name
        target_path = os.path.join(output_folder, name) if output_folder else raster_path

        with rasterio.open(raster_path) as src:
            profile = src.profile
            data = src.read()

        # Clear the NoData flag entirely - same effect as the QGIS-mode fix
        profile.update(nodata=None)

        with rasterio.open(target_path, "w", **profile) as dst:
            dst.write(data)

        processed.append(target_path)
        print(f"  Cleaned: {name}")

    print(f"\nDone. {len(processed)} raster(s) processed.")
    return processed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch-clear NoData flags across a folder of raster imagery."
    )
    parser.add_argument("input_folder", help="Folder containing raster files")
    parser.add_argument(
        "-o", "--output_folder", default=None,
        help="Output folder (default: clean files in place)"
    )
    args = parser.parse_args()

    clean_raster_folder(args.input_folder, args.output_folder)

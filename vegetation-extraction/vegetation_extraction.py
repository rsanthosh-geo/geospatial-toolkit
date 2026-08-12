"""
Vegetation Extraction from RGB Imagery (Excess Green Index)
-------------------------------------------------------------
Extracts vegetation (trees, bushes, grass, plant cover) from RGB
satellite/aerial/drone imagery as clean vector polygons, using the
Excess Green Index (ExG) — a standard, published vegetation index that
needs only ordinary RGB bands (no near-infrared required).

    ExG = (2 x Green) - Red - Blue

Two usage modes are provided:

1. QGIS Mode (`run_qgis_batch`) - runs inside QGIS, using the QGIS
   Processing framework (sieve / polygonize / extract-by-expression) for
   batch folder processing with full QGIS algorithm support.
2. Standalone Mode (`extract_vegetation`) - pure Python (rasterio +
   scikit-image + shapely), no QGIS dependency. Produces the same
   ExG -> threshold -> denoise -> polygonize -> filter pipeline and
   writes results as GeoJSON, usable in any Python environment.

Use case
--------
Given a raster tile (or a folder of tiles covering an area of interest),
extract polygons for whatever the imagery's green-vegetation signal
covers — useful for vegetation encroachment checks, land-cover context,
or any workflow that needs "where is the vegetation" as a vector layer
rather than a raster mask.

Requirements
------------
- Standalone mode: rasterio, numpy, scikit-image, shapely
- QGIS mode: run inside QGIS (uses qgis.core / processing, bundled)
"""

import os
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# MODE 1: Standalone — no QGIS dependency
# ---------------------------------------------------------------------------

def compute_exg(red, green, blue):
    """Excess Green Index: (2*G) - R - B, computed as float32."""
    return (2.0 * green.astype("float32")
            - red.astype("float32")
            - blue.astype("float32"))


def extract_vegetation(
    raster_path,
    output_path,
    threshold=30,
    min_blob_size=30,
    use_green_dominance=False,
):
    """
    Extract vegetation polygons from a single RGB raster.

    Parameters
    ----------
    raster_path : str
        Path to an RGB (3-band) raster.
    output_path : str
        Path to write the output vegetation polygons (GeoJSON).
    threshold : int
        Minimum ExG value to classify a pixel as vegetation. 30 is a
        commonly used starting point in the remote-sensing literature;
        tune per imagery source/lighting conditions.
    min_blob_size : int
        Minimum connected-pixel-group size to keep (removes speckle
        noise, equivalent to a sieve filter).
    use_green_dominance : bool
        If True, additionally require green > red and green > blue
        (stricter — reduces false positives from soil/urban surfaces
        that can register high ExG in some imagery).

    Returns
    -------
    int
        Number of vegetation polygons written.
    """
    import rasterio
    from rasterio.features import shapes
    from skimage.morphology import remove_small_objects
    import shapely.geometry as sgeom
    import geopandas as gpd

    with rasterio.open(raster_path) as src:
        red = src.read(1)
        green = src.read(2)
        blue = src.read(3)
        transform = src.transform
        crs = src.crs

    exg = compute_exg(red, green, blue)

    veg_mask = exg > threshold
    if use_green_dominance:
        veg_mask &= (green > red) & (green > blue)

    # Remove small speckle blobs (sieve-equivalent).
    # scikit-image renamed min_size -> max_size in 0.26; support both.
    try:
        veg_mask_clean = remove_small_objects(veg_mask, max_size=min_blob_size)
    except TypeError:
        veg_mask_clean = remove_small_objects(veg_mask, min_size=min_blob_size)

    # Polygonize
    polygons = []
    for geom, value in shapes(veg_mask_clean.astype("uint8"), transform=transform):
        if value == 1:
            polygons.append(sgeom.shape(geom))

    if not polygons:
        print(f"No vegetation detected in {Path(raster_path).name} "
              f"(try lowering threshold, currently {threshold})")
        return 0

    gdf = gpd.GeoDataFrame({"class": ["vegetation"] * len(polygons)},
                            geometry=polygons, crs=crs)
    gdf.to_file(output_path, driver="GeoJSON")

    print(f"  {Path(raster_path).name}: {len(polygons)} vegetation polygon(s) -> {output_path}")
    return len(polygons)


def extract_vegetation_batch(input_folder, output_folder, **kwargs):
    """
    Batch-run `extract_vegetation` across every raster in a folder.

    Parameters
    ----------
    input_folder : str
        Folder of RGB raster tiles.
    output_folder : str
        Destination folder for per-tile GeoJSON outputs.
    **kwargs
        Passed through to `extract_vegetation` (threshold, min_blob_size,
        use_green_dominance).
    """
    input_folder = os.path.normpath(input_folder)
    output_folder = os.path.normpath(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    rasters = sorted(
        p for p in Path(input_folder).glob("*")
        if p.suffix.lower() in (".tif", ".tiff")
    )

    if not rasters:
        print(f"No rasters found in {input_folder}")
        return []

    results = []
    for raster_path in rasters:
        out_path = os.path.join(output_folder, f"{raster_path.stem}_vegetation.geojson")
        count = extract_vegetation(str(raster_path), out_path, **kwargs)
        results.append((str(raster_path), out_path, count))

    total = sum(r[2] for r in results)
    print(f"\nDone. {len(rasters)} raster(s) processed, {total} total vegetation polygon(s).")
    return results


# ---------------------------------------------------------------------------
# MODE 2: QGIS batch mode — full QGIS Processing framework
# ---------------------------------------------------------------------------

def run_qgis_batch(
    input_folder,
    output_folder,
    threshold=30,
    use_green_dominance=False,
    skip_sieve=False,
    merge_all=False,
    clip_layer=None,
):
    """
    Batch vegetation extraction using the QGIS Processing framework.
    Run this from the QGIS Python Console.

    Parameters mirror `extract_vegetation_batch`, plus QGIS-specific
    options (sieve skipping, merge-all-into-one-layer, optional AOI clip).
    """
    from qgis.core import (
        QgsRasterLayer, QgsRasterCalculator, QgsRasterCalculatorEntry,
        QgsVectorLayer, QgsProject,
    )
    import processing

    input_folder = os.path.normpath(input_folder)
    output_folder = os.path.normpath(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    rasters = [str(p) for ext in (".tif", ".tiff", ".TIF", ".TIFF")
               for p in Path(input_folder).glob(f"*{ext}")]

    if not rasters:
        print("No rasters found")
        return

    print(f"Found {len(rasters)} raster(s). Threshold: {threshold}")

    all_results = []
    for i, raster_path in enumerate(rasters, 1):
        name = Path(raster_path).stem
        safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)
        out_dir = os.path.join(output_folder, safe_name)
        os.makedirs(out_dir, exist_ok=True)
        print(f"[{i}/{len(rasters)}] {name}")

        try:
            raster_layer = QgsRasterLayer(raster_path, "input_raster")
            if not raster_layer.isValid():
                raise Exception("Cannot load raster")

            exg_path = os.path.join(out_dir, f"{safe_name}_exg.tif")
            veg_path = os.path.join(out_dir, f"{safe_name}_veg.tif")
            poly_path = os.path.join(out_dir, f"{safe_name}_poly.shp")
            final_path = os.path.join(out_dir, f"{safe_name}_vegetation.shp")

            entries = []
            for ref, band in (("red@1", 1), ("green@1", 2), ("blue@1", 3)):
                e = QgsRasterCalculatorEntry()
                e.ref, e.raster, e.bandNumber = ref, raster_layer, band
                entries.append(e)

            QgsRasterCalculator(
                "(2 * green@1) - (red@1 + blue@1)", exg_path, "GTiff",
                raster_layer.extent(), raster_layer.width(), raster_layer.height(), entries,
            ).processCalculation()

            exg_layer = QgsRasterLayer(exg_path, "exg_raster")
            entries2 = [_calc_entry("exg@1", exg_layer, 1)]
            extra_cond = ""
            if use_green_dominance:
                extra_cond = " AND (green@1 > red@1) AND (green@1 > blue@1)"
                entries2 += [_calc_entry(r, raster_layer, b)
                             for r, b in (("red@1", 1), ("green@1", 2), ("blue@1", 3))]

            expr = f"((exg@1 > {threshold}){extra_cond}) * 255"
            QgsRasterCalculator(
                expr, veg_path, "GTiff",
                exg_layer.extent(), exg_layer.width(), exg_layer.height(), entries2,
            ).processCalculation()

            to_process = veg_path
            if not skip_sieve:
                sieved = os.path.join(out_dir, f"{safe_name}_sieved.tif")
                processing.run("gdal:sieve", {
                    "INPUT": veg_path, "THRESHOLD": 30, "EIGHT_CONNECTEDNESS": True,
                    "NO_MASK": True, "MASK_LAYER": None, "EXTRA": "", "OUTPUT": sieved,
                })
                if os.path.exists(sieved):
                    to_process = sieved

            processing.run("gdal:polygonize", {
                "INPUT": to_process, "BAND": 1, "FIELD": "veg",
                "EIGHT_CONNECTEDNESS": False, "EXTRA": "", "OUTPUT": poly_path,
            })

            processing.run("native:extractbyexpression", {
                "INPUT": poly_path, "EXPRESSION": '"veg" = 255', "OUTPUT": final_path,
            })

            if clip_layer and os.path.exists(clip_layer):
                clipped = os.path.join(out_dir, f"{safe_name}_vegetation_clip.shp")
                processing.run("native:clip", {
                    "INPUT": final_path, "OVERLAY": clip_layer, "OUTPUT": clipped,
                })
                if os.path.exists(clipped):
                    final_path = clipped

            layer = QgsVectorLayer(final_path, "check", "ogr")
            if layer.isValid() and layer.featureCount() > 0:
                all_results.append(final_path)
                print(f"  ok ({layer.featureCount()} features)")

        except Exception as e:
            print(f"  FAILED: {e}")

    if merge_all and len(all_results) > 1:
        merged = os.path.join(output_folder, "MERGED_vegetation.shp")
        dissolved = os.path.join(output_folder, "FINAL_vegetation.shp")
        processing.run("native:mergevectorlayers", {"LAYERS": all_results, "CRS": None, "OUTPUT": merged})
        processing.run("native:dissolve", {"INPUT": merged, "FIELD": [], "OUTPUT": dissolved})
        layer = QgsVectorLayer(dissolved, "FINAL_vegetation", "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            print(f"Merged + dissolved output: {dissolved}")

    print(f"\nDone. {len(all_results)}/{len(rasters)} raster(s) produced vegetation output.")
    return all_results


def _calc_entry(ref, raster, band):
    from qgis.core import QgsRasterCalculatorEntry
    e = QgsRasterCalculatorEntry()
    e.ref, e.raster, e.bandNumber = ref, raster, band
    return e


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Batch vegetation extraction from RGB imagery (standalone mode).")
    parser.add_argument("input_folder", help="Folder of RGB raster tiles")
    parser.add_argument("output_folder", help="Destination folder for GeoJSON outputs")
    parser.add_argument("-t", "--threshold", type=int, default=30)
    parser.add_argument("--green-dominance", action="store_true")
    args = parser.parse_args()

    extract_vegetation_batch(
        args.input_folder, args.output_folder,
        threshold=args.threshold, use_green_dominance=args.green_dominance,
    )

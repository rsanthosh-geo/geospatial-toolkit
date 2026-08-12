"""
Example: generate a small synthetic RGB raster with simulated vegetation
patches (green blobs) over a non-vegetated background, run vegetation
extraction, and visualize the result. Fully synthetic - no real imagery
required to try this out.
"""
import os
import numpy as np
import rasterio
from rasterio.transform import from_origin
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from vegetation_extraction import extract_vegetation, compute_exg


def make_synthetic_rgb(path, size=100, seed=7):
    """
    Create a synthetic 3-band RGB raster: a bare/urban-toned background
    with a few rounded vegetation patches (green-dominant) scattered in.
    """
    rng = np.random.default_rng(seed)

    # Background: bare soil / urban tones (red and blue somewhat higher than green)
    red = rng.integers(110, 150, size=(size, size)).astype("uint8")
    green = rng.integers(90, 120, size=(size, size)).astype("uint8")
    blue = rng.integers(100, 140, size=(size, size)).astype("uint8")

    # Vegetation patches: green-dominant blobs
    yy, xx = np.mgrid[0:size, 0:size]
    blob_centers = [(25, 30, 12), (70, 65, 16), (45, 80, 9)]
    for cy, cx, r in blob_centers:
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r ** 2
        green[mask] = rng.integers(150, 200, size=mask.sum())
        red[mask] = rng.integers(60, 100, size=mask.sum())
        blue[mask] = rng.integers(50, 90, size=mask.sum())

    transform = from_origin(0, size, 1, 1)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=3,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(red, 1)
        dst.write(green, 2)
        dst.write(blue, 3)

    return red, green, blue


if __name__ == "__main__":
    os.makedirs("sample_data", exist_ok=True)
    os.makedirs("sample_output", exist_ok=True)

    raster_path = "sample_data/synthetic_tile.tif"
    red, green, blue = make_synthetic_rgb(raster_path)
    print(f"Created synthetic RGB raster with 3 simulated vegetation patches: {raster_path}")

    out_path = "sample_output/synthetic_tile_vegetation.geojson"
    n_polygons = extract_vegetation(raster_path, out_path, threshold=30, min_blob_size=30)

    # Visualize: RGB composite, ExG heatmap, and extracted polygons overlaid
    import geopandas as gpd

    rgb = np.dstack([red, green, blue])
    exg = compute_exg(red, green, blue)
    gdf = gpd.read_file(out_path) if n_polygons else None

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3))
    size = rgb.shape[0]
    # Explicit extent so the vector overlay's geographic coordinates line up
    # with the displayed array (row 0 = top = y-max, matching the raster's
    # north-up transform used when the tile was created).
    extent = (0, size, 0, size)

    axes[0].imshow(rgb, extent=extent, origin="upper")
    axes[0].set_title("Input: synthetic RGB tile")
    axes[0].axis("off")

    im = axes[1].imshow(exg, cmap="RdYlGn", extent=extent, origin="upper")
    axes[1].set_title("Excess Green Index (ExG)")
    axes[1].axis("off")
    plt.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)

    axes[2].imshow(rgb, extent=extent, origin="upper")
    if gdf is not None:
        gdf.plot(ax=axes[2], facecolor="none", edgecolor="red", linewidth=1.5)
    axes[2].set_title(f"Extracted vegetation polygons (n={n_polygons})")
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig("extraction_demo.png", dpi=150)
    print("\nSaved demo image: extraction_demo.png")

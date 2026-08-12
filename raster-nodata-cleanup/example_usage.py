"""
Example: generate a small synthetic raster with a simulated white-patch
region, run the cleanup tool on it, and visualize the before/after
result. Fully synthetic data - no real imagery required to try this out.
"""
import os
import numpy as np
import rasterio
from rasterio.transform import from_origin
import matplotlib.pyplot as plt

from raster_nodata_cleanup import clean_raster_folder


def make_synthetic_raster(path, size=40, nodata_value=120, seed=42):
    """
    Create a synthetic single-band raster that reproduces the real-world
    problem: a block of pixels holds ordinary, valid data (within the
    normal value range), but that same value has been flagged as the
    file's NoData value - so GIS software masks and renders it blank,
    even though the underlying data is legitimate.
    """
    rng = np.random.default_rng(seed)
    data = rng.integers(50, 200, size=(size, size)).astype("float32")

    # Simulate a region whose real pixel values collide with the NoData flag
    patch = size // 3
    start = size // 2 - patch // 2
    data[start:start + patch, start:start + patch] = nodata_value

    transform = from_origin(0, size, 1, 1)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
        nodata=nodata_value,
    ) as dst:
        dst.write(data, 1)
    return data


def load_masked(path):
    """Load a raster the way GIS software renders it — NoData shown as blank."""
    with rasterio.open(path) as src:
        arr = src.read(1, masked=True)
    return arr


if __name__ == "__main__":
    os.makedirs("sample_data", exist_ok=True)
    os.makedirs("sample_output", exist_ok=True)

    sample_path = "sample_data/synthetic_tile.tif"
    make_synthetic_raster(sample_path)
    print(f"Created synthetic raster with a simulated white-patch region: {sample_path}")

    clean_raster_folder("sample_data", "sample_output")

    before = load_masked(sample_path)
    after = load_masked("sample_output/synthetic_tile.tif")

    # Shared color scale so the comparison is visually honest
    vmin, vmax = 50, 200

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
    axes[0].imshow(before, cmap="viridis", vmin=vmin, vmax=vmax)
    axes[0].set_title("Before: NoData renders as blank patch")
    axes[0].axis("off")

    axes[1].imshow(after, cmap="viridis", vmin=vmin, vmax=vmax)
    axes[1].set_title("After: NoData cleared, pixel data visible")
    axes[1].axis("off")

    plt.tight_layout()
    plt.savefig("before_after_demo.png", dpi=150)
    print("\nSaved comparison image: before_after_demo.png")

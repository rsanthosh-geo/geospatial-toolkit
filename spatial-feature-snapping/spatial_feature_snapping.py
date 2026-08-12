"""
Spatial Feature Snapping: Point-to-Line-Vertex Automation
------------------------------------------------------------
Snaps point features to the nearest vertex on a line network, enforcing
a strict 1:1 relationship — each point can snap to only one vertex, and
each vertex can receive only one point. Points beyond a distance
threshold are left unchanged.

Originally built for snapping utility poles onto a conductor-line
network (a common electrical T&D data-cleanup task), but the underlying
technique — nearest-vertex snapping with a 1:1 constraint — is a
generic spatial-conflation operation applicable anywhere a point layer
needs to align with an existing line network's vertices: address points
to road-centerline nodes, sensor locations to pipeline junctions, asset
points to any linear network, etc.

Two usage modes are provided:

1. QGIS Mode (`snap_points_to_lines_qgis`) - runs inside QGIS, operates
   on layers already loaded in the project, modifies the point layer
   in place (line layer is never modified).
2. Standalone Mode (`snap_points_to_lines`) - pure Python (geopandas +
   shapely), no QGIS dependency. Reads/writes GeoJSON or any
   OGR-supported format, usable in any Python environment or pipeline.

Requirements
------------
- Standalone mode: geopandas, shapely
- QGIS mode: run inside QGIS (uses qgis.core, bundled)
"""

import math


# ---------------------------------------------------------------------------
# MODE 1: Standalone — no QGIS dependency
# ---------------------------------------------------------------------------

def _line_vertices(line_geom):
    """Yield every vertex (x, y) from a LineString or MultiLineString."""
    geom_type = line_geom.geom_type
    if geom_type == "LineString":
        yield from line_geom.coords
    elif geom_type == "MultiLineString":
        for part in line_geom.geoms:
            yield from part.coords


def snap_points_to_lines(points, lines, snap_threshold=6.0, output_path=None):
    """
    Snap point features onto the nearest vertex of a line network,
    enforcing a 1:1 point-to-vertex relationship.

    Parameters
    ----------
    points : geopandas.GeoDataFrame or str
        Point layer (or path to one) to snap. Only this layer is modified.
    lines : geopandas.GeoDataFrame or str
        Line layer (or path to one), read-only — never modified.
    snap_threshold : float
        Maximum distance (in the layers' CRS units) within which a point
        may snap to a vertex. Points beyond this are left unchanged.
    output_path : str, optional
        If given, writes the snapped point layer to this path (format
        inferred from extension, e.g. .geojson).

    Returns
    -------
    geopandas.GeoDataFrame
        Copy of the point layer with an added 'snapped' field ('Yes'/'No')
        and updated geometry for snapped points.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    if isinstance(points, str):
        points = gpd.read_file(points)
    if isinstance(lines, str):
        lines = gpd.read_file(lines)

    if points.crs != lines.crs:
        print(f"WARNING: CRS mismatch (points: {points.crs}, lines: {lines.crs}). "
              f"Reproject before snapping for accurate results.")

    vertices = []
    for geom in lines.geometry:
        if geom is not None:
            vertices.extend(_line_vertices(geom))

    if not vertices:
        raise ValueError("No vertices found in line layer")

    print(f"Points: {len(points)} | Line vertices: {len(vertices)} | Threshold: {snap_threshold}")

    candidates = []
    for pt_idx, geom in enumerate(points.geometry):
        px, py = geom.x, geom.y
        best_dist = math.inf
        best_vertex_idx = None
        for v_idx, (vx, vy) in enumerate(vertices):
            d = math.hypot(px - vx, py - vy)
            if d < best_dist:
                best_dist, best_vertex_idx = d, v_idx
        if best_dist <= snap_threshold:
            candidates.append((pt_idx, best_vertex_idx, best_dist))

    candidates.sort(key=lambda c: c[2])
    used_vertices, used_points = set(), set()
    snapping_plan = {}
    for pt_idx, v_idx, dist in candidates:
        if pt_idx in used_points or v_idx in used_vertices:
            continue
        snapping_plan[pt_idx] = v_idx
        used_points.add(pt_idx)
        used_vertices.add(v_idx)

    result = points.copy()
    result["snapped"] = "No"
    for pt_idx, v_idx in snapping_plan.items():
        result.at[pt_idx, "geometry"] = Point(vertices[v_idx])
        result.at[pt_idx, "snapped"] = "Yes"

    print(f"Snapped: {len(snapping_plan)} | Unchanged: {len(points) - len(snapping_plan)}")

    if output_path:
        result.to_file(output_path, driver="GeoJSON" if output_path.endswith(".geojson") else None)
        print(f"Written: {output_path}")

    return result


# ---------------------------------------------------------------------------
# MODE 2: QGIS Console — operates on layers loaded in the active project
# ---------------------------------------------------------------------------

def snap_points_to_lines_qgis(point_layer_name, line_layer_name, snap_threshold=6.0):
    """
    Snap point features to the nearest line-network vertex, using layers
    already loaded in the active QGIS project. Only the point layer is
    modified (adds a 'snapped' field and moves snapped point geometries);
    the line layer is never altered.

    Parameters
    ----------
    point_layer_name : str
        Name of the point layer in the QGIS project (e.g. a utility
        pole layer, address-point layer, sensor layer, etc.)
    line_layer_name : str
        Name of the line layer in the QGIS project (e.g. a conductor
        network, road centerlines, pipeline network, etc.)
    snap_threshold : float
        Maximum snap distance in the layers' CRS units.
    """
    from qgis.core import QgsProject, QgsGeometry, QgsWkbTypes, QgsField
    from qgis.PyQt.QtCore import QVariant
    from qgis.utils import iface

    print("=" * 70)
    print("POINT-TO-LINE-VERTEX SNAPPING TOOL")
    print("=" * 70)

    point_layer = line_layer = None
    for layer in QgsProject.instance().mapLayers().values():
        if layer.name() == point_layer_name and layer.geometryType() == QgsWkbTypes.PointGeometry:
            point_layer = layer
        elif layer.name() == line_layer_name and layer.geometryType() == QgsWkbTypes.LineGeometry:
            line_layer = layer

    if not point_layer or not line_layer:
        available = [l.name() for l in QgsProject.instance().mapLayers().values()]
        print(f"ERROR: layer(s) not found. Available layers: {available}")
        return

    print(f"Point layer: {point_layer.name()} ({point_layer.featureCount()} features)")
    print(f"Line layer: {line_layer.name()} ({line_layer.featureCount()} features)")
    if point_layer.crs() != line_layer.crs():
        print("WARNING: CRS mismatch between point and line layers.")

    field_name = "snapped"
    if field_name not in [f.name() for f in point_layer.fields()]:
        point_layer.dataProvider().addAttributes([QgsField(field_name, QVariant.String, len=3)])
        point_layer.updateFields()
    snap_idx = point_layer.fields().indexOf(field_name)

    line_vertices = []
    for feature in line_layer.getFeatures():
        geom = feature.geometry()
        if geom.isMultipart():
            for part in geom.asMultiPolyline():
                line_vertices.extend(part)
        else:
            line_vertices.extend(geom.asPolyline())

    print(f"Line vertices: {len(line_vertices)}")
    if not line_vertices:
        print("ERROR: no vertices found in line layer")
        return

    candidates = []
    for feature in point_layer.getFeatures():
        pt = feature.geometry().asPoint()
        best_dist, best_idx = math.inf, None
        for idx, v in enumerate(line_vertices):
            d = pt.distance(v.x(), v.y())
            if d < best_dist:
                best_dist, best_idx = d, idx
        if best_dist <= snap_threshold:
            candidates.append((feature.id(), best_idx, best_dist))

    candidates.sort(key=lambda c: c[2])
    used_vertices, used_points, plan = set(), set(), {}
    for fid, v_idx, dist in candidates:
        if fid in used_points or v_idx in used_vertices:
            continue
        plan[fid] = v_idx
        used_points.add(fid)
        used_vertices.add(v_idx)

    print(f"Snapping plan: {len(plan)} point(s) to snap, "
          f"{point_layer.featureCount() - len(plan)} unchanged")

    point_layer.startEditing()
    for feature in point_layer.getFeatures():
        fid = feature.id()
        if fid in plan:
            point_layer.changeAttributeValue(fid, snap_idx, "Yes")
            point_layer.changeGeometry(fid, QgsGeometry.fromPointXY(line_vertices[plan[fid]]))
        else:
            point_layer.changeAttributeValue(fid, snap_idx, "No")

    if point_layer.commitChanges():
        print("Changes saved.")
    else:
        print("ERROR saving changes:", point_layer.commitErrors())
        return

    point_layer.triggerRepaint()
    iface.mapCanvas().refresh()
    print("=" * 70)
    print("DONE")

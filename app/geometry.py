"""Port of Honeycomb 3D Design v0.7.0 geometry rules, for web deployment.
Retains hex layout, fallback, exact axis orientation, triangulation, and watertight checks.
"""
import math
import numpy as np
import trimesh
from shapely.geometry import Polygon, box
from shapely.ops import unary_union, triangulate

STYLES = {'bin': (5.0, 2.2, 2.0), 'clean': (9.0, 3.0, 6.0), 'large': (9.0, 3.0, 6.0)}

def parameters(style='bin', radius=None, rib=None, border=None):
    if style not in STYLES:
        raise ValueError('Unknown style.')
    dr, dt, db = STYLES[style]
    return (dr if radius is None else radius, dt if rib is None else rib, db if border is None else border)

def hole_layout(width, height, radius, rib, border):
    if not all(math.isfinite(v) for v in (width, height, radius, rib, border)):
        raise ValueError('All dimensions must be finite.')
    if min(width, height, radius, rib) <= 0 or border < 0:
        raise ValueError('Panel dimensions, radius and rib must be positive; border may be zero.')
    if max(width, height) > 2000:
        raise ValueError('Dimension exceeds 2000 mm limit.')
    edge = border if border > 0 else rib / 2
    hh = math.sqrt(3) * radius / 2
    ux = width - 2 * (edge + radius)
    uy = height - 2 * (edge + hh)
    if ux < -1e-8 or uy < -1e-8:
        raise ValueError('No hex opening fits. Reduce hex size or border.')
    dx, dy = 1.5 * radius + rib, math.sqrt(3) * radius + rib
    cols = math.floor((ux + 1e-8) / dx) + 1
    points = []
    for col in range(cols):
        offset = dy / 2 if col % 2 else 0
        maxrow = math.floor((uy - offset + 1e-8) / dy)
        for row in range(max(0, maxrow + 1)):
            points.append((col * dx, offset + row * dy))
    if not points:
        raise ValueError('No openings fit this panel.')
    ox = width / 2 - (min(p[0] for p in points) + max(p[0] for p in points)) / 2
    oy = height / 2 - (min(p[1] for p in points) + max(p[1] for p in points)) / 2
    return [(ox + px, oy + py) for px, py in points], edge

def effective_radius(width, height, style, radius, rib, border):
    selected, rib, border = parameters(style, radius, rib, border)
    if radius is None and style == 'bin':
        try:
            hole_layout(width, height, selected, rib, border)
        except ValueError as e:
            if 'No hex opening fits' not in str(e):
                raise
            selected = 3.0
            hole_layout(width, height, selected, rib, border)
    return selected

def resolve_axis(x, y, z, axis='auto'):
    vals = {'x': x, 'y': y, 'z': z}
    if not all(math.isfinite(v) and 0 < v <= 2000 for v in vals.values()):
        raise ValueError('All dimensions must be positive and at most 2000 mm.')
    if axis != 'auto':
        if axis not in vals:
            raise ValueError('Invalid thickness axis.')
        return axis
    smallest = min(vals.values())
    matches = [k for k, v in vals.items() if math.isclose(v, smallest)]
    if len(matches) != 1:
        raise ValueError('Thickness axis is ambiguous; choose X, Y, or Z.')
    return matches[0]

def face_dimensions(x, y, z, axis):
    return {'x': (y, z), 'y': (x, z), 'z': (x, y)}[axis]

def layout_info(x, y, z, axis='auto', style='bin', hole_size=None, rib=None, border=None):
    axis = resolve_axis(x, y, z, axis)
    width, height = face_dimensions(x, y, z, axis)
    requested_radius = hole_size / 2 if hole_size is not None else None
    radius = effective_radius(width, height, style, requested_radius, rib, border)
    _, rib, border = parameters(style, radius, rib, border)
    centers, edge = hole_layout(width, height, radius, rib, border)
    if len(centers) > 3000:
        raise ValueError('Too many openings (maximum 3000). Increase hex size or reduce panel size.')
    return {'axis': axis, 'width': width, 'height': height, 'radius': radius,
            'hole_size': radius*2, 'rib': rib, 'border': border,
            'centers': centers, 'edge': edge, 'holes': len(centers),
            'fallback': hole_size is None and style == 'bin' and radius == 3.0}

def svg_string(info):
    from xml.sax.saxutils import escape
    f = lambda v: f'{v:.8f}'.rstrip('0').rstrip('.')
    width, height, r = info['width'], info['height'], info['radius']
    paths = [f'M 0,0 H {f(width)} V {f(height)} H 0 Z']
    for cx, cy in info['centers']:
        verts = [(cx + r*math.cos(i*math.pi/3), cy+r*math.sin(i*math.pi/3)) for i in range(6)]
        paths.append('M ' + ' L '.join(f'{f(px)},{f(py)}' for px, py in verts) + ' Z')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(width)}mm" '
            f'height="{f(height)}mm" viewBox="0 0 {f(width)} {f(height)}">\n'
            f' <title>Honeycomb face {f(width)} by {f(height)} mm</title>\n'
            f' <path d="{escape(" ".join(paths))}" fill="black" fill-rule="evenodd"/>\n</svg>\n')

def mesh_for_panel(x, y, z, info, flat=False):
    axis = info['axis']
    width, height, radius = info['width'], info['height'], info['radius']
    thickness = {'x':x, 'y':y, 'z':z}[axis]
    cutters = [Polygon([(cx+radius*math.cos(i*math.pi/3), cy+radius*math.sin(i*math.pi/3)) for i in range(6)])
               for cx, cy in info['centers']]
    polygon = box(0, 0, width, height).difference(unary_union(cutters))
    if polygon.geom_type != 'Polygon' or not polygon.is_valid:
        raise ValueError('Non-manifold geometry. Increase rib or border.')
    edge = info['edge']
    interior = box(edge-1e-6, edge-1e-6, width-edge+1e-6, height-edge+1e-6)
    if any(not interior.covers(c) for c in cutters):
        raise ValueError('Opening violates outer border.')
    triangles = [tri for tri in triangulate(polygon) if polygon.covers(tri)]
    if not triangles:
        raise ValueError('No printable triangulation.')
    vertices, lookup, faces = [], {}, []
    def v(point, h):
        key = (h, round(point[0],8), round(point[1],8))
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append((float(h), float(point[0]), float(point[1])))
        return lookup[key]
    for tri in triangles:
        pts = list(tri.exterior.coords)[:3]
        low = [v(p,0) for p in pts]
        high = [v(p,thickness) for p in pts]
        faces.extend(((low[0],low[2],low[1]), (high[0],high[1],high[2])))
    for ring in [polygon.exterior, *polygon.interiors]:
        pts = list(ring.coords)
        for a,b in zip(pts[:-1], pts[1:]):
            ab,bb = v(a,0),v(b,0)
            at,bt = v(a,thickness),v(b,thickness)
            faces.extend(((ab,bb,bt),(ab,bt,at)))
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices),faces=np.asarray(faces),process=True)
    mesh.fix_normals()
    order = {'x': (0,1,2), 'y': (1,0,2), 'z': (1,2,0)}[axis]
    if order != (0,1,2):
        mesh.vertices = mesh.vertices[:,order]
        mesh.fix_normals()
    if not np.allclose(mesh.bounds, [[0,0,0],[x,y,z]],atol=.01):
        raise RuntimeError('STL dimensions do not match requested X/Y/Z.')
    if flat:
        new_order = {'x':(1,2,0), 'y':(0,2,1), 'z':(0,1,2)}[axis]
        mesh.vertices = mesh.vertices[:,new_order]
        mesh.fix_normals()
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise RuntimeError('Watertight/winding STL verification failed.')
    return mesh

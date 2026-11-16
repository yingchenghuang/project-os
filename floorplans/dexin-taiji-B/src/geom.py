"""Geometry kernel shared by the DXF, COLLADA/GLB and SketchUp exporters.

Units: millimetres. World axes: X = east, Y = north, Z = up.
Every solid is either
  * Prism  : a planar 2D polygon (may contain holes) placed in 3D by an origin and
             two in-plane axes (u, v), then extruded along vector e;
  * Mesh   : a closed polygon mesh (used only for rounded plant canopies).
The same primitives drive every exporter, so the 2D plan and the 3D model can never drift apart.
"""
from __future__ import annotations

import math

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box as _sbox

X = (1.0, 0.0, 0.0)
Y = (0.0, 1.0, 0.0)
Z = (0.0, 0.0, 1.0)


def _clean_ring(coords, tol=0.5):
    pts = [tuple(map(float, c)) for c in coords]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > tol:
            out.append(p)
    if len(out) > 2 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def clean_poly(poly: Polygon) -> Polygon:
    poly = poly.simplify(0.3, preserve_topology=True)
    return Polygon(_clean_ring(poly.exterior.coords), [_clean_ring(r.coords) for r in poly.interiors])


class Prism:
    __slots__ = ("poly", "o", "u", "v", "e", "mat", "plan", "circle")

    def __init__(self, poly, o, u, v, e, mat, plan=True, circle=None):
        self.poly = clean_poly(poly)
        self.o = np.asarray(o, float)
        self.u = np.asarray(u, float)
        self.v = np.asarray(v, float)
        self.e = np.asarray(e, float)
        self.mat = mat
        self.plan = plan
        self.circle = circle  # (s, t, r) in local coords when the profile is a true circle

    def transformed(self, M):
        R = M[:3, :3]
        o = M[:3, :3] @ self.o + M[:3, 3]
        p = Prism.__new__(Prism)
        p.poly, p.o, p.u, p.v, p.e = self.poly, o, R @ self.u, R @ self.v, R @ self.e
        p.mat, p.plan, p.circle = self.mat, self.plan, self.circle
        return p

    # ---- plan helpers -------------------------------------------------
    def is_vertical_extrusion(self):
        n = self.e / np.linalg.norm(self.e)
        return abs(n[2]) > 0.999 and abs(self.u[2]) < 1e-9 and abs(self.v[2]) < 1e-9

    def to_world2d(self, s, t):
        p = self.o + s * self.u + t * self.v
        return float(p[0]), float(p[1])

    def footprint(self):
        """World XY footprint polygon (only for vertical extrusions)."""
        ext = [self.to_world2d(s, t) for s, t in self.poly.exterior.coords]
        holes = [[self.to_world2d(s, t) for s, t in r.coords] for r in self.poly.interiors]
        return Polygon(ext, holes)

    def zrange(self):
        z0 = self.o[2]
        return min(z0, z0 + self.e[2]), max(z0, z0 + self.e[2])


class Mesh:
    __slots__ = ("verts", "faces", "mat", "plan", "plan_circle")

    def __init__(self, verts, faces, mat, plan=True, plan_circle=None):
        self.verts = np.asarray(verts, float)
        self.faces = faces
        self.mat = mat
        self.plan = plan
        self.plan_circle = plan_circle  # (cx, cy, r)

    def transformed(self, M):
        V = (M[:3, :3] @ self.verts.T).T + M[:3, 3]
        pc = None
        if self.plan_circle:
            c = M @ np.array([self.plan_circle[0], self.plan_circle[1], 0, 1.0])
            pc = (float(c[0]), float(c[1]), self.plan_circle[2])
        return Mesh(V, self.faces, self.mat, self.plan, pc)


# ---------------------------------------------------------------- constructors
def rect(x0, y0, x1, y1):
    return _sbox(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def box(x0, y0, z0, x1, y1, z1, mat, plan=True):
    return Prism(rect(x0, y0, x1, y1), (0, 0, min(z0, z1)), X, Y, (0, 0, abs(z1 - z0)), mat, plan)


def xyprism(poly, z0, z1, mat, plan=True):
    return Prism(poly, (0, 0, z0), X, Y, (0, 0, z1 - z0), mat, plan)


def circle_poly(cx, cy, r, seg=24):
    return Point(cx, cy).buffer(r, quad_segs=max(2, seg // 4))


def cyl(cx, cy, r, z0, z1, mat, plan=True, seg=24):
    return Prism(circle_poly(0, 0, r, seg), (cx, cy, z0), X, Y, (0, 0, z1 - z0), mat, plan, circle=(0.0, 0.0, r))


def cyl_axis(p0, axis, r, mat, plan=False, seg=16):
    """Cylinder starting at p0 extruded along vector axis (any direction)."""
    a = np.asarray(axis, float)
    n = a / np.linalg.norm(a)
    helper = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(helper, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return Prism(circle_poly(0, 0, r, seg), p0, u, v, a, mat, plan, circle=(0.0, 0.0, r))


def ellipse(cx, cy, a, b, seg=48):
    return affinity.translate(affinity.scale(Point(0, 0).buffer(1.0, quad_segs=seg // 4), a, b), cx, cy)


def stadium(cx, cy, length, width, along="x"):
    half = max(length - width, 0) / 2
    line = LineString([(-half, 0), (half, 0)]) if along == "x" else LineString([(0, -half), (0, half)])
    return affinity.translate(line.buffer(width / 2, quad_segs=8), cx, cy)


def ring(poly, inset):
    inner = poly.buffer(-inset, join_style=2)
    return Polygon(poly.exterior.coords, [inner.exterior.coords])


def elevation_prism(poly_sz, origin, along, thickness_vec, mat, plan=True):
    """Polygon drawn in a vertical plane: s along `along`, t = Z, extruded by thickness_vec."""
    return Prism(poly_sz, origin, along, Z, thickness_vec, mat, plan)


def sphere(cx, cy, cz, r, mat, plan=True, rings=7, segs=12):
    verts = [(cx, cy, cz + r)]
    for i in range(1, rings):
        phi = math.pi * i / rings
        for j in range(segs):
            th = 2 * math.pi * j / segs
            verts.append((cx + r * math.sin(phi) * math.cos(th), cy + r * math.sin(phi) * math.sin(th), cz + r * math.cos(phi)))
    verts.append((cx, cy, cz - r))
    faces = []
    bottom = len(verts) - 1
    for j in range(segs):
        faces.append([0, 1 + j, 1 + (j + 1) % segs])
    for i in range(rings - 2):
        a = 1 + i * segs
        b = a + segs
        for j in range(segs):
            j2 = (j + 1) % segs
            faces.append([a + j, b + j, b + j2, a + j2])
    last = 1 + (rings - 2) * segs
    for j in range(segs):
        faces.append([last + j, bottom, last + (j + 1) % segs])
    return Mesh(verts, faces, mat, plan, plan_circle=(cx, cy, r))


# ---------------------------------------------------------------- transforms
def tmat(tx=0.0, ty=0.0, tz=0.0, rot_deg=0.0):
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    M = np.eye(4)
    M[:2, :2] = [[c, -s], [s, c]]
    M[:3, 3] = [tx, ty, tz]
    return M


def transform2d(M, x, y):
    p = M @ np.array([x, y, 0.0, 1.0])
    return float(p[0]), float(p[1])


# ---------------------------------------------------------------- triangulation
def prism_triangles(p: Prism):
    import trimesh

    h = float(np.linalg.norm(p.e))
    m = trimesh.creation.extrude_polygon(p.poly, h)
    n = p.e / h
    V = p.o + np.outer(m.vertices[:, 0], p.u) + np.outer(m.vertices[:, 1], p.v) + np.outer(m.vertices[:, 2], n)
    F = np.asarray(m.faces)
    if np.dot(np.cross(p.u, p.v), n) < 0:
        F = F[:, ::-1]
    return V, F


def mesh_triangles(m: Mesh):
    tris = []
    for f in m.faces:
        for k in range(1, len(f) - 1):
            tris.append([f[0], f[k], f[k + 1]])
    return m.verts, np.asarray(tris)


def triangles(prim):
    return prism_triangles(prim) if isinstance(prim, Prism) else mesh_triangles(prim)

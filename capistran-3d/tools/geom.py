"""Light-weight mesh kernel: primitives, banded wall solids, smoothing.

Units: metres, Z up. UVs are produced in metres (world scale) unless a
primitive says otherwise; the exporters divide by each material's tile size.
"""
import math
import numpy as np
import mapbox_earcut as earcut
from shapely.geometry import Polygon, MultiPolygon, Point, box as sbox
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


class Mesh:
    def __init__(self, smooth_deg=0.0):
        self.P = []   # per-corner positions
        self.T = []   # per-corner uvs
        self.smooth_deg = smooth_deg

    # -- raw adders (counter-clockwise seen from the front side)
    def tri(self, a, b, c, ta=(0, 0), tb=(0, 0), tc=(0, 0)):
        self.P += [a, b, c]
        self.T += [ta, tb, tc]

    def quad(self, a, b, c, d, ta=(0, 0), tb=(1, 0), tc=(1, 1), td=(0, 1)):
        self.tri(a, b, c, ta, tb, tc)
        self.tri(a, c, d, ta, tc, td)

    def extend(self, other):
        self.P += other.P
        self.T += other.T

    def empty(self):
        return len(self.P) == 0

    # -- finalisation into indexed arrays with crease-angle normals
    def finalize(self):
        P = np.asarray(self.P, float).reshape(-1, 3)
        T = np.asarray(self.T, float).reshape(-1, 2)
        nf = len(P) // 3
        if nf == 0:
            return None
        A, B, C = P[0::3], P[1::3], P[2::3]
        fn = np.cross(B - A, C - A)
        area = np.linalg.norm(fn, axis=1)
        keep = area > 1e-12
        fnu = np.zeros_like(fn)
        fnu[keep] = fn[keep] / area[keep, None]
        N = np.repeat(fnu, 3, axis=0)
        if self.smooth_deg > 0:
            cosT = math.cos(math.radians(self.smooth_deg))
            key = np.round(P / 1e-4).astype(np.int64)
            # group corners by position
            _, inv = np.unique(key, axis=0, return_inverse=True)
            inv = inv.ravel()
            order = np.argsort(inv, kind='stable')
            bounds = np.flatnonzero(np.diff(inv[order])) + 1
            groups = np.split(order, bounds)
            fw = np.repeat(fn, 3, axis=0)  # area weighted
            Nn = N.copy()
            for g in groups:
                if len(g) < 2:
                    continue
                gn = N[g]
                dots = gn @ gn.T
                acc = (dots >= cosT).astype(float) @ fw[g]
                ln = np.linalg.norm(acc, axis=1)
                ok = ln > 1e-12
                Nn[g[ok]] = acc[ok] / ln[ok, None]
            N = Nn
        # drop degenerate faces
        fk = np.repeat(keep, 3)
        P, T, N = P[fk], T[fk], N[fk]
        # weld identical corners
        key = np.hstack([np.round(P / 1e-5), np.round(T / 1e-5), np.round(N / 1e-3)]).astype(np.int64)
        uniq, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.ravel()
        return {
            'P': P[idx], 'N': N[idx], 'T': T[idx],
            'F': inv.reshape(-1, 3).astype(np.int64),
        }


# ---------------------------------------------------------------- transforms
def xf_translate(x, y, z):
    M = np.eye(4); M[:3, 3] = [x, y, z]; return M


def xf_rotz(a):
    c, s = math.cos(a), math.sin(a)
    M = np.eye(4); M[0, 0] = c; M[0, 1] = -s; M[1, 0] = s; M[1, 1] = c; return M


def xf_scale(sx, sy, sz):
    return np.diag([sx, sy, sz, 1.0])


def apply_xf(mesh, M):
    out = Mesh(mesh.smooth_deg)
    if mesh.P:
        P = np.asarray(mesh.P, float)
        P = (np.c_[P, np.ones(len(P))] @ M.T)[:, :3]
        out.P = [tuple(p) for p in P]
        out.T = list(mesh.T)
    return out


# ---------------------------------------------------------------- primitives
def add_box(m, x0, x1, y0, y1, z0, z1, uvscale=1.0):
    """Axis aligned box with box-projected UVs (metres)."""
    s = uvscale
    v = lambda x, y, z: (x, y, z)
    # -X
    m.quad(v(x0, y1, z0), v(x0, y0, z0), v(x0, y0, z1), v(x0, y1, z1), (y1 * s, z0 * s), (y0 * s, z0 * s), (y0 * s, z1 * s), (y1 * s, z1 * s))
    # +X
    m.quad(v(x1, y0, z0), v(x1, y1, z0), v(x1, y1, z1), v(x1, y0, z1), (y0 * s, z0 * s), (y1 * s, z0 * s), (y1 * s, z1 * s), (y0 * s, z1 * s))
    # -Y
    m.quad(v(x0, y0, z0), v(x1, y0, z0), v(x1, y0, z1), v(x0, y0, z1), (x0 * s, z0 * s), (x1 * s, z0 * s), (x1 * s, z1 * s), (x0 * s, z1 * s))
    # +Y
    m.quad(v(x1, y1, z0), v(x0, y1, z0), v(x0, y1, z1), v(x1, y1, z1), (x1 * s, z0 * s), (x0 * s, z0 * s), (x0 * s, z1 * s), (x1 * s, z1 * s))
    # top / bottom
    m.quad(v(x0, y0, z1), v(x1, y0, z1), v(x1, y1, z1), v(x0, y1, z1), (x0 * s, y0 * s), (x1 * s, y0 * s), (x1 * s, y1 * s), (x0 * s, y1 * s))
    m.quad(v(x0, y1, z0), v(x1, y1, z0), v(x1, y0, z0), v(x0, y0, z0), (x0 * s, y1 * s), (x1 * s, y1 * s), (x1 * s, y0 * s), (x0 * s, y0 * s))
    return m


def box_mesh(x0, x1, y0, y1, z0, z1):
    return add_box(Mesh(), x0, x1, y0, y1, z0, z1)


def add_cylinder(m, cx, cy, r, z0, z1, seg=24, caps=True, r1=None, uv_circ=None, z_axis=True):
    """Vertical (truncated) cylinder. UV u = arc length, v = z."""
    r1 = r if r1 is None else r1
    for i in range(seg):
        a0 = 2 * math.pi * i / seg; a1 = 2 * math.pi * (i + 1) / seg
        p00 = (cx + r * math.cos(a0), cy + r * math.sin(a0), z0)
        p10 = (cx + r * math.cos(a1), cy + r * math.sin(a1), z0)
        p11 = (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z1)
        p01 = (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z1)
        u0 = a0 * max(r, 0.05); u1 = a1 * max(r, 0.05)
        m.quad(p00, p10, p11, p01, (u0, z0), (u1, z0), (u1, z1), (u0, z1))
        if caps:
            if r1 > 0:
                m.tri((cx, cy, z1), p01, p11, (cx, cy), (p01[0], p01[1]), (p11[0], p11[1]))
            if r > 0:
                m.tri((cx, cy, z0), p10, p00, (cx, cy), (p10[0], p10[1]), (p00[0], p00[1]))
    return m


def add_revolve(m, prof, cx=0.0, cy=0.0, seg=64, a0=0.0, a1=2 * math.pi, uv='arc', tile_u=None):
    """Revolve a polyline profile [(r,z),...] around a vertical axis.

    Profile order bottom->top with outward-facing normal when r increases
    to the right of travel (i.e. listing an outer surface from bottom to top).
    uv='arc'  : u = r*angle (m), v = cumulative profile length (m)
    uv='angle': u = angle/(2pi)*tile_u (radial stripes), v = cumulative length
    uv='plan' : planar xy
    """
    L = [0.0]
    for i in range(1, len(prof)):
        L.append(L[-1] + math.hypot(prof[i][0] - prof[i - 1][0], prof[i][1] - prof[i - 1][1]))
    for i in range(seg):
        t0 = a0 + (a1 - a0) * i / seg; t1 = a0 + (a1 - a0) * (i + 1) / seg
        for j in range(len(prof) - 1):
            (ra, za), (rb, zb) = prof[j], prof[j + 1]
            P = lambda r, z, t: (cx + r * math.cos(t), cy + r * math.sin(t), z)
            pa0, pa1, pb1, pb0 = P(ra, za, t0), P(ra, za, t1), P(rb, zb, t1), P(rb, zb, t0)
            if uv == 'arc':
                rm = max(0.05, 0.5 * (ra + rb))
                ta0, ta1, tb1, tb0 = (t0 * rm, L[j]), (t1 * rm, L[j]), (t1 * rm, L[j + 1]), (t0 * rm, L[j + 1])
            elif uv == 'angle':
                k = tile_u / (2 * math.pi)
                ta0, ta1, tb1, tb0 = (t0 * k, L[j]), (t1 * k, L[j]), (t1 * k, L[j + 1]), (t0 * k, L[j + 1])
            else:
                ta0, ta1, tb1, tb0 = [(p[0], p[1]) for p in (pa0, pa1, pb1, pb0)]
            if ra < 1e-9:
                m.tri(pa0, pb1, pb0, ta0, tb1, tb0)
            elif rb < 1e-9:
                m.tri(pa0, pa1, pb0, ta0, ta1, tb0)
            else:
                m.quad(pa0, pa1, pb1, pb0, ta0, ta1, tb1, tb0)
    return m


def flip(m):
    out = Mesh(m.smooth_deg)
    for i in range(0, len(m.P), 3):
        out.P += [m.P[i], m.P[i + 2], m.P[i + 1]]
        out.T += [m.T[i], m.T[i + 2], m.T[i + 1]]
    return out


# ---------------------------------------------------------------- polygons
def circle_poly(cx, cy, r, seg=480):
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    return Polygon(np.c_[cx + r * np.cos(a), cy + r * np.sin(a)])


def ring_poly(cx, cy, r_out, r_in, seg=480):
    return circle_poly(cx, cy, r_out, seg).difference(circle_poly(cx, cy, r_in, seg))


def sector_poly(cx, cy, r, a0, a1, seg=96):
    a = np.linspace(a0, a1, seg)
    pts = [(cx, cy)] + [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in a]
    return Polygon(pts)


def polys_of(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    out = []
    for g in getattr(geom, 'geoms', []):
        out += polys_of(g)
    return out


def triangulate_poly(poly):
    poly = orient(poly, 1.0)
    rings = [np.asarray(poly.exterior.coords)[:-1]]
    for h in poly.interiors:
        rings.append(np.asarray(h.coords)[:-1])
    verts = np.vstack(rings)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tris = earcut.triangulate_float64(verts, ends)
    return verts, np.asarray(tris).reshape(-1, 3)


def add_cap(m, geom, z, up=True, uv_off=(0, 0)):
    for p in polys_of(geom):
        if p.area < 1e-7:
            continue
        V, Tr = triangulate_poly(p)
        for a, b, c in Tr:
            A, B, C = V[a], V[b], V[c]
            # earcut keeps input winding? enforce orientation by signed area
            cr = (B[0] - A[0]) * (C[1] - A[1]) - (B[1] - A[1]) * (C[0] - A[0])
            if (cr > 0) != up:
                B, C = C, B
            m.tri((A[0], A[1], z), (B[0], B[1], z), (C[0], C[1], z),
                  (A[0] + uv_off[0], A[1] + uv_off[1]), (B[0] + uv_off[0], B[1] + uv_off[1]), (C[0] + uv_off[0], C[1] + uv_off[1]))


def _ring_edges(poly):
    poly = orient(poly, 1.0)
    rings = [poly.exterior] + list(poly.interiors)
    for r in rings:
        c = np.asarray(r.coords)
        for i in range(len(c) - 1):
            yield c[i], c[i + 1]


def default_side_uv(a, b, za, zb):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    return (0.0, L)


def add_sides(m, geom, z0, z1, uvfun=None):
    for p in polys_of(geom):
        for a, b in _ring_edges(p):
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-7:
                continue
            ua, ub = (uvfun or default_side_uv)(a, b, z0, z1)
            m.quad((a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1),
                   (ua, z0), (ub, z0), (ub, z1), (ua, z1))


def add_prism(m, geom, z0, z1, uvfun=None, top=True, bottom=True):
    add_sides(m, geom, z0, z1, uvfun)
    if top:
        add_cap(m, geom, z1, True)
    if bottom:
        add_cap(m, geom, z0, False)


def banded_solid(m, components, cuts, uvfun=None, min_area=1e-6):
    """Build a solid from plan components extruded over z-ranges, minus cuts.

    components / cuts: list of (shapely_geom, z0, z1). The result is the
    union of components active in each horizontal band, minus cuts active in
    that band; side faces, and the horizontal caps where consecutive bands
    differ, are emitted. This makes curved walls with rectangular openings.
    """
    zs = sorted(set([c[1] for c in components] + [c[2] for c in components] +
                    [c[1] for c in cuts] + [c[2] for c in cuts]))
    zmin = min(c[1] for c in components); zmax = max(c[2] for c in components)
    zs = [z for z in zs if zmin - 1e-9 <= z <= zmax + 1e-9]
    bands = []
    for za, zb in zip(zs[:-1], zs[1:]):
        if zb - za < 1e-6:
            continue
        zm = 0.5 * (za + zb)
        comp = [c[0] for c in components if c[1] <= zm <= c[2]]
        S = unary_union(comp) if comp else None
        if S is not None:
            ct = [c[0] for c in cuts if c[1] <= zm <= c[2]]
            if ct:
                S = S.difference(unary_union(ct))
            S = S.buffer(0)
        bands.append((za, zb, S))
    empty = Polygon()
    for i, (za, zb, S) in enumerate(bands):
        if S is None or S.is_empty:
            continue
        add_sides(m, S, za, zb, uvfun)
        above = bands[i + 1][2] if i + 1 < len(bands) else None
        below = bands[i - 1][2] if i > 0 else None
        topcap = S if (above is None or above.is_empty) else S.difference(above)
        botcap = S if (below is None or below.is_empty) else S.difference(below)
        add_cap(m, _clean(topcap, min_area), zb, True)
        add_cap(m, _clean(botcap, min_area), za, False)
    return m


def _clean(g, min_area):
    ps = [p for p in polys_of(g) if p.area > min_area]
    # drop sliver polygons (thin numerical residue)
    ps = [p for p in ps if p.area / max(p.length, 1e-9) > 2e-4]
    return MultiPolygon(ps) if ps else Polygon()


def arc_uv(center):
    """UV function for side faces of curved walls around `center`: u = arc length
    for tangential edges, radial distance for radial (jamb) edges."""
    cx, cy = center

    def f(a, b, za, zb):
        ex, ey = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ex, ey)
        mx, my = 0.5 * (a[0] + b[0]) - cx, 0.5 * (a[1] + b[1]) - cy
        rm = math.hypot(mx, my)
        if rm < 1e-6:
            return (0.0, L)
        tang = abs((ex * mx + ey * my) / (L * rm)) < 0.5
        if tang:
            r = rm
            ta = math.atan2(a[1] - cy, a[0] - cx); tb = math.atan2(b[1] - cy, b[0] - cx)
            if tb - ta > math.pi:
                tb -= 2 * math.pi
            elif ta - tb > math.pi:
                tb += 2 * math.pi
            return (ta * r, tb * r)
        ra = math.hypot(a[0] - cx, a[1] - cy); rb = math.hypot(b[0] - cx, b[1] - cy)
        return (ra, rb)
    return f


def multi_center_uv(centers_fn):
    """centers_fn(point)->center; pick arc_uv centre per edge."""
    def f(a, b, za, zb):
        m = (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))
        return arc_uv(centers_fn(m))(a, b, za, zb)
    return f


def add_arc_panel(m, cx, cy, r, a0, a1, z0, z1, seg=None, uvmode='m', inward=True):
    """Vertical cylindrical panel (zero thickness). uvmode 'm' metres or 'unit' 0..1."""
    seg = seg or max(2, int(abs(a1 - a0) * r / 0.15))
    for i in range(seg):
        t0 = a0 + (a1 - a0) * i / seg; t1 = a0 + (a1 - a0) * (i + 1) / seg
        p0 = (cx + r * math.cos(t0), cy + r * math.sin(t0)); p1 = (cx + r * math.cos(t1), cy + r * math.sin(t1))
        if uvmode == 'unit':
            u0 = i / seg; u1 = (i + 1) / seg; v0, v1 = 0.0, 1.0
        else:
            u0 = t0 * r; u1 = t1 * r; v0, v1 = z0, z1
        if inward:  # normal toward centre
            m.quad((p1[0], p1[1], z0), (p0[0], p0[1], z0), (p0[0], p0[1], z1), (p1[0], p1[1], z1),
                   (-u1, v0), (-u0, v0), (-u0, v1), (-u1, v1))
        else:
            m.quad((p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z1), (p0[0], p0[1], z1),
                   (u0, v0), (u1, v0), (u1, v1), (u0, v1))
    return m


def add_sphere(m, cx, cy, cz, r, seg=12, rings=8, sx=1, sy=1, sz=1, jitter=0.0, rng=None):
    pts = {}
    for i in range(rings + 1):
        ph = math.pi * i / rings
        for j in range(seg):
            th = 2 * math.pi * j / seg
            k = 1.0
            if jitter and rng is not None and 0 < i < rings:
                k = 1 + jitter * (rng.random() - 0.5)
            pts[(i, j)] = (cx + sx * r * k * math.sin(ph) * math.cos(th), cy + sy * r * k * math.sin(ph) * math.sin(th), cz + sz * r * k * math.cos(ph))
    for i in range(rings):
        for j in range(seg):
            a, b = pts[(i, j)], pts[(i, (j + 1) % seg)]
            c, d = pts[(i + 1, (j + 1) % seg)], pts[(i + 1, j)]
            ua, ub = j / seg * 2 * math.pi * r, (j + 1) / seg * 2 * math.pi * r
            va, vb = -i / rings * math.pi * r, -(i + 1) / rings * math.pi * r
            if i == 0:
                m.tri(a, d, c, (ua, va), (ua, vb), (ub, vb))
            elif i == rings - 1:
                m.tri(a, d, b, (ua, va), (ua, vb), (ub, va))
            else:
                m.quad(a, d, c, b, (ua, va), (ua, vb), (ub, vb), (ub, va))
    return m


def add_oriented_box(m, p, u, v, w, su, sv, sw):
    """Box centred at p with orthonormal axes u,v,w and half sizes."""
    p = np.asarray(p, float); u = np.asarray(u, float); v = np.asarray(v, float); w = np.asarray(w, float)
    c = lambda i, j, k: tuple(p + i * su * u + j * sv * v + k * sw * w)
    faces = [
        ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1), sv, sw),
        ((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1), sv, sw),
        ((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1), su, sw),
        ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1), su, sw),
        ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1), su, sv),
        ((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1), su, sv),
    ]
    for a, b, cc, d, s1, s2 in faces:
        m.quad(c(*a), c(*b), c(*cc), c(*d), (0, 0), (2 * s1, 0), (2 * s1, 2 * s2), (0, 2 * s2))
    return m

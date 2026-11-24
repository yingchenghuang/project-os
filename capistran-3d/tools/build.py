"""Scene description of St. Johann von Capistran, Munich (Sep Ruf, 1958-60).

Sources (in the user's package):
 * Bauen + Wohnen 17 (1963) Heft 2, "Katholische Kirche St. Johann von
   Capistran in München" (ETH e-periodica, doi 10.5169/seals-331550)
 * Kirchenkurzführer St. Johann von Capistran (Okt 2012)
 * Photographs and plan sketches supplied with the brief.

Key dimensions (Kurzführer): outer circle 32.00 m, inner circle 28.00 m,
eccentric; crescent 4.00 m wide in the east (4 storeys), circles meet at
the west portal; wall height 12.50 m; height incl. dome 16.00 m; dome
(Plexiglas) 5.00 m; roof overhang 4.50 m; 22 iron pendulum rods at 5.35 m
spacing ending in buried, ton-heavy concrete counterweights; Nagelfluh altar
2 x 2 m; bell wall 13.5 x 12.5 m.

Coordinates: metres, Z up, X = east, Y = north. Origin = centre of the
outer circle (= dome axis) at finished interior floor level +-0.00.
"""
import math
import numpy as np
from shapely.geometry import Polygon, Point, box as sbox, LineString
from shapely.ops import unary_union

from geom import (Mesh, add_box, box_mesh, add_cylinder, add_revolve, add_cap, add_prism,
                  add_sides, banded_solid, ring_poly, circle_poly, sector_poly, arc_uv,
                  multi_center_uv, add_arc_panel, add_sphere, add_oriented_box, apply_xf,
                  xf_translate, xf_rotz, xf_scale, flip, polys_of)

D = math.radians
RNG = np.random.default_rng(1456)

# ------------------------------------------------------------- key numbers
O = (0.0, 0.0)            # outer circle centre / dome axis
C = (-2.0, 0.0)           # inner circle centre (eccentric to the west)
R_OUT, T_OUT = 16.00, 0.49
R_OUT_I = R_OUT - T_OUT   # 15.51
R_IN, T_IN = 14.00, 0.365
R_IN_O = R_IN + T_IN      # 14.365
X_PORTAL = -13.00         # glass portal plane
H_OUT_BRICK = 11.25       # outer brick wall top (clerestory gallery glazing above)
H_IN = 11.95              # inner wall (gallery runs behind it)
Z_GALLERY = 10.25
Z_CLR_TOP = 12.25
Z_SOFFIT = 12.55
R_ROOF = R_OUT + 4.50     # 20.50
Z_CEIL_RIM, Z_CEIL_TOP = 12.30, 13.60
R_LANTERN = 2.80
R_DOME = 2.50
Z_DOME_TOP = 16.00
N_RODS, R_RODS = 22, 22 * 5.35 / (2 * math.pi)   # 18.73 m
Y_PORTAL = math.sqrt(R_IN ** 2 - (X_PORTAL - C[0]) ** 2)   # 8.66


def roof_z(r):
    """Copper roof top: shallow vault from the cornice (13.05) to the lantern curb."""
    return 13.05 + 1.92 * (1 - (r / R_ROOF) ** 2)


def ceil_point(t, s):
    """Interior star ceiling: loft between rim (circle around C) and lantern
    ring (circle around O). t = angle, s = 0 rim .. 1 lantern."""
    rx, ry = C[0] + (R_IN - 0.02) * math.cos(t), C[1] + (R_IN - 0.02) * math.sin(t)
    lx, ly = O[0] + R_LANTERN * math.cos(t), O[1] + R_LANTERN * math.sin(t)
    z = Z_CEIL_RIM + (Z_CEIL_TOP - Z_CEIL_RIM) * math.sin(s * math.pi / 2)
    return (rx + (lx - rx) * s, ry + (ly - ry) * s, z)


_CEIL_LUT = None


def ceil_z_at(x, y):
    """Height of the ceiling surface above plan point (x,y) (numerical inverse)."""
    global _CEIL_LUT
    if _CEIL_LUT is None:
        ts = np.linspace(-math.pi, math.pi, 721); ss = np.linspace(0, 1, 121)
        pts = np.array([[ceil_point(t, s) for s in ss] for t in ts]).reshape(-1, 3)
        _CEIL_LUT = pts
    d = (_CEIL_LUT[:, 0] - x) ** 2 + (_CEIL_LUT[:, 1] - y) ** 2
    return float(_CEIL_LUT[np.argmin(d), 2])


def on_inner(phi_deg, r=R_IN):
    a = D(phi_deg)
    return (C[0] + r * math.cos(a), C[1] + r * math.sin(a))


def on_outer(phi_deg, r=R_OUT):
    a = D(phi_deg)
    return (O[0] + r * math.cos(a), O[1] + r * math.sin(a))


# ------------------------------------------------------------- scene model
class Scene:
    def __init__(self):
        self.materials = {}
        self.objects = []     # dict(name, layer, parts=[(mat, Mesh)])
        self.defs = {}        # name -> dict(parts=[(mat, Mesh)], layer)
        self.instances = []   # dict(name, layer, defname, M)
        self.lights = []
        self.views = []
        self.curves = []      # dict(layer, name, kind, data)
        self.dots = []        # (layer, text, (x,y,z))

    def mat(self, name, **kw):
        self.materials[name] = kw

    def obj(self, name, layer, parts):
        parts = [(m, me) for m, me in parts if not me.empty()]
        if parts:
            self.objects.append(dict(name=name, layer=layer, parts=parts))

    def define(self, name, layer, parts):
        self.defs[name] = dict(layer=layer, parts=[(m, me) for m, me in parts if not me.empty()])

    def inst(self, name, layer, defname, M):
        self.instances.append(dict(name=name, layer=layer, defname=defname, M=M))

    def light(self, **kw):
        self.lights.append(kw)


def K(kelvin):
    """Approximate RGB of a black body (Tanner Helland fit)."""
    t = kelvin / 100.0
    r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = lambda v: int(max(0, min(255, v)))
    return (c(r), c(g), c(b))


# ------------------------------------------------------------- materials
def define_materials(S, tiles):
    m = S.mat
    m('Brick_HardFired', color=(140, 62, 48), tex='brick_hardfired.png', bump='brick_hardfired_bump.png', tile=tiles['brick'], refl=0.03, gloss=0.15)
    m('Brick_Unjointed_Absorber', color=(120, 52, 44), tex='brick_unjointed.png', bump='brick_unjointed_bump.png', tile=tiles['brick_unjointed'], refl=0.02)
    m('Brick_Screen_Steingitter', color=(140, 62, 48), tex='brick_screen_alpha.png', alpha=True, tile=tiles['brick_screen'], double=True)
    m('Clinker_Floor_Red', color=(146, 62, 46), tex='clinker_floor.png', bump='clinker_floor_bump.png', tile=tiles['clinker'], refl=0.08, gloss=0.45)
    m('Wood_Spruce_Slat_Light', color=(186, 140, 96), tex='wood_spruce_slat.png', tile=tiles['wood_slat'], refl=0.02)
    m('Ceiling_Backing_Dark', color=(34, 26, 22), refl=0.0)
    m('Wood_Soffit_Dark', color=(70, 50, 36), tex='soffit_slats_dark.png', tile=(1.0, 2.0))
    m('Copper_Roof_Aged', color=(96, 70, 52), tex='copper_roof.png', bump='copper_roof_bump.png', tile=(1.0, 4.0), refl=0.25, gloss=0.35, metal=True)
    m('Aluminium_Cornice_Riveted', color=(180, 184, 188), tex='alu_fascia.png', bump='alu_fascia_bump.png', tile=tiles['alu'], refl=0.45, gloss=0.55, metal=True)
    m('Steel_Galvanized_Rods', color=(150, 154, 158), refl=0.45, gloss=0.6, metal=True)
    m('Steel_Dark_Painted', color=(42, 44, 47), refl=0.15, gloss=0.5)
    m('Glass_Clear', color=(206, 222, 218), transp=0.9, ior=1.52, refl=0.1, gloss=1.0, double=True)
    m('Glass_Clerestory', color=(190, 205, 205), transp=0.85, ior=1.52, refl=0.12, gloss=1.0, double=True)
    m('Plexiglas_Dome_Frosted', color=(242, 244, 246), tex='plexiglas_frosted.png', tile=(5.0, 5.0), transp=0.6, ior=1.49, refl=0.05, gloss=0.3, double=True)
    m('Stained_Glass_Oberberger', color=(120, 110, 140), tex='stained_glass_oberberger.png', tile=(1.0, 1.0), transp=0.45, refl=0.06, double=True)
    m('Bronze_Portal_Relief', color=(66, 54, 40), tex='bronze_door_relief.png', bump='bronze_door_relief_bump.png', tile=(1.0, 1.0), refl=0.25, gloss=0.4, metal=True)
    m('Copper_Clad_Door', color=(58, 50, 44), refl=0.12, gloss=0.3, metal=True)
    m('Nagelfluh_Conglomerate', color=(186, 176, 158), tex='nagelfluh.png', bump='nagelfluh_bump.png', tile=tiles['nagelfluh'], refl=0.03)
    m('Tombak_FireGilded', color=(214, 170, 82), refl=0.7, gloss=0.85, metal=True)
    m('Bronze_Dark', color=(92, 68, 44), refl=0.35, gloss=0.5, metal=True)
    m('Wood_Ash_Pew', color=(222, 192, 146), tex='wood_ash_bench.png', tile=tiles['wood_bench'], refl=0.06, gloss=0.4)
    m('Wood_Dark_Stain', color=(70, 50, 36), tex='wood_dark_stain.png', tile=tiles['wood_dark'], refl=0.05, gloss=0.4)
    m('Wood_Carved_Lime', color=(176, 140, 98), refl=0.02)
    m('Organ_Tin', color=(206, 206, 202), refl=0.6, gloss=0.75, metal=True)
    m('Plaster_White', color=(236, 233, 226))
    m('Paint_Dark_Gallery', color=(36, 33, 31))
    m('Concrete_Slab', color=(152, 150, 144))
    m('Concrete_BoardFormed', color=(150, 148, 142), tex='concrete_board.png', bump='concrete_board_bump.png', tile=tiles['concrete'])
    m('Concrete_Honeycomb_CastGlass', color=(166, 170, 164), tex='honeycomb_concrete_glass.png', tile=tiles['honeycomb'])
    m('Paving_Hex_Concrete', color=(194, 184, 166), tex='hex_pavers.png', bump='hex_pavers_bump.png', tile=tiles['hex'])
    m('Paving_GrassGrid', color=(110, 128, 96), tex='grass_pavers.png', tile=tiles['grasspaver'])
    m('Lawn', color=(76, 116, 50), tex='lawn.png', tile=tiles['lawn'])
    m('Asphalt', color=(72, 72, 74), tex='asphalt.png', tile=tiles['asphalt'])
    m('Render_White', color=(232, 228, 218))
    m('Roof_Tile_Dark', color=(84, 58, 52))
    m('Granite_Grey', color=(150, 146, 142), refl=0.05)
    m('Bell_Bronze', color=(120, 86, 46), refl=0.4, gloss=0.5, metal=True)
    m('Bark', color=(88, 76, 64), tex='bark.png', tile=tiles['bark'])
    m('Foliage', color=(62, 100, 44), tex='foliage.png', tile=tiles['foliage'])
    m('Lamp_Aluminium', color=(196, 198, 202), refl=0.55, gloss=0.75, metal=True)
    m('Emissive_Diffuser_2700K', color=(255, 236, 206), emit=K(2700))
    m('Emissive_Neon_3500K', color=(255, 246, 232), emit=K(3500))
    m('Candle_Wax', color=(242, 238, 224))
    m('Black_Rubber', color=(20, 20, 20))


# ------------------------------------------------------------- helpers
def uv_swap(mesh):
    mesh.T = [(t[1], t[0]) for t in mesh.T]
    return mesh


def arc_box(m, center, r0, r1, a0, a1, z0, z1, seg=None):
    """Curved slab segment (annular sector) as a closed solid."""
    seg = seg or max(2, int(abs(a1 - a0) * r1 / 0.2))
    g = sector_poly(center[0], center[1], r1, a0, a1, seg).difference(circle_poly(center[0], center[1], r0, 720)) if r0 > 0 else sector_poly(center[0], center[1], r1, a0, a1, seg)
    add_prism(m, g, z0, z1, uvfun=arc_uv(center))
    return m


def wedge_cut(center, r_out, r_in, a0, a1):
    return sector_poly(center[0], center[1], r_out, a0, a1, 24).difference(circle_poly(center[0], center[1], r_in, 720))


def place(S, name, layer, defname, x, y, z=0.0, rot=0.0, scale=None):
    M = xf_translate(x, y, z) @ xf_rotz(rot)
    if scale is not None:
        M = M @ xf_scale(*scale)
    S.inst(name, layer, defname, M)


# ------------------------------------------------------------- 1 masonry
def build_masonry(S):
    outer = ring_poly(O[0], O[1], R_OUT, R_OUT_I)
    inner = ring_poly(C[0], C[1], R_IN_O, R_IN)
    comps = [(outer, 0.0, H_OUT_BRICK), (inner, 0.0, H_IN)]
    cuts = [(sbox(-40, -40, X_PORTAL, 40), -1, 30)]
    screens_outer, screens_inner = [], []
    # --- outer wall: two side portals (copper-clad doors) at +-71 deg
    door_w, door_h = 1.25, 2.60
    for sgn in (1, -1):
        a = D(71 * sgn); da = door_w / R_OUT / 2
        cuts.append((wedge_cut(O, R_OUT + 0.3, R_OUT_I - 0.05, a - da, a + da), -1, door_h))
    # --- outer wall: Steingitter band in the lower east wall (windows behind)
    n = 23
    for i in range(n):
        phi = -62 + 124 * i / (n - 1)
        a = D(phi); da = 1.10 / R_OUT / 2
        cuts.append((wedge_cut(O, R_OUT + 0.3, R_OUT_I - 0.05, a - da, a + da), 0.30, 2.20))
        screens_outer.append((a - da, a + da, 0.30, 2.20))
    # --- inner wall: side doors at +-56 deg (around C)
    for sgn in (1, -1):
        a = D(56 * sgn); da = 1.20 / R_IN / 2
        cuts.append((wedge_cut(C, R_IN_O + 0.05, R_IN - 0.3, a - da, a + da), -1, 2.50))
    # --- inner wall, east: opening to the baptismal chapel + stone grilles
    s2a = lambda s: s / R_IN
    cuts.append((wedge_cut(C, R_IN_O + 0.05, R_IN - 0.3, s2a(-1.25), s2a(1.25)), -1, 2.55))
    grid = [(-1.25, 1.25, 2.85, 5.05), (-1.25, 1.25, 5.35, 9.35),
            (-2.85, -1.55, 0.30, 2.55), (-2.85, -1.55, 2.85, 5.05), (-2.85, -1.55, 5.35, 7.25), (-2.85, -1.55, 7.55, 9.35),
            (1.55, 2.85, 0.30, 2.55), (1.55, 2.85, 2.85, 4.15), (1.55, 2.85, 4.45, 7.25), (1.55, 2.85, 7.55, 9.35),
            (-3.95, -3.15, 5.35, 9.35), (3.15, 3.95, 5.35, 9.35)]
    for s0, s1, z0, z1 in grid:
        cuts.append((wedge_cut(C, R_IN_O + 0.05, R_IN - 0.3, s2a(s0), s2a(s1)), z0, z1))
        screens_inner.append((s2a(s0), s2a(s1), z0, z1))

    def centre_for(pt):
        x, y = pt
        do = min(abs(math.hypot(x, y) - R_OUT), abs(math.hypot(x, y) - R_OUT_I))
        di = min(abs(math.hypot(x - C[0], y) - R_IN_O), abs(math.hypot(x - C[0], y) - R_IN))
        return O if do < di else C

    wall = Mesh(smooth_deg=12)
    banded_solid(wall, comps, cuts, uvfun=multi_center_uv(centre_for))
    S.obj('Masonry_Double_Shell (outer 32 m / inner 28 m)', '03_Structure::Brick Walls', [('Brick_HardFired', wall)])

    # Steingitter screens (alpha textured, inside the reveals) + windows behind
    scr = Mesh(); win = Mesh()
    for a0, a1, z0, z1 in screens_outer:
        add_arc_panel(scr, O[0], O[1], R_OUT - 0.12, a0, a1, z0, z1, seg=4, inward=False)
        add_arc_panel(win, O[0], O[1], R_OUT_I + 0.06, a0, a1, z0, z1, seg=4, inward=False)
    for a0, a1, z0, z1 in screens_inner:
        add_arc_panel(scr, C[0], C[1], R_IN + 0.10, a0, a1, z0, z1, seg=6, inward=True)
    S.obj('Steingitter_Perforated_Brick_Screens', '03_Structure::Stone Grilles', [('Brick_Screen_Steingitter', scr)])
    S.obj('Windows_behind_Grilles', '05_Facade::Glazing', [('Glass_Clear', win)])

    # absorber fields with unjointed brick (10 places, Bauen+Wohnen 1963)
    ab = Mesh()
    for phi in (72, 90, 108, 124, 137):
        for sgn in (1, -1):
            a = D(phi * sgn); da = 2.4 / R_IN / 2
            add_arc_panel(ab, C[0], C[1], R_IN - 0.004, a - da, a + da, 2.25, 3.45, seg=8, inward=True)
    S.obj('Sound_Absorber_Fields_Unjointed_Brick', '06_Interior::Wall Finishes', [('Brick_Unjointed_Absorber', ab)])

    # stone lintels / ledges in the east wall composition
    led = Mesh()
    arc_box(led, C, R_IN - 0.05, R_IN + 0.02, s2a(-1.40), s2a(1.40), 2.55, 2.85)
    arc_box(led, C, R_IN - 0.08, R_IN + 0.02, s2a(-1.40), s2a(1.40), 5.05, 5.35)
    S.obj('East_Wall_Lintels', '07_Liturgy::Sanctuary', [('Nagelfluh_Conglomerate', led)])

    # copper clad doors (outer) and bronze-framed doors (inner)
    dr = Mesh(); fr = Mesh()
    for sgn in (1, -1):
        a = D(71 * sgn); da = door_w / R_OUT / 2
        arc_box(dr, O, R_OUT - 0.30, R_OUT - 0.24, a - da, a + da, 0.0, door_h)
        a = D(56 * sgn); da = 1.20 / R_IN / 2
        arc_box(dr, C, R_IN + 0.12, R_IN + 0.18, a - da, a + da, 0.0, 2.50)
        arc_box(fr, C, R_IN - 0.02, R_IN + 0.02, a - da - 0.004, a + da + 0.004, 2.50, 2.58)
    S.obj('Side_Portals_Copper_Clad_Doors', '05_Facade::Doors', [('Copper_Clad_Door', dr), ('Steel_Dark_Painted', fr)])

    # brick sill on outer wall top + clerestory glazing + posts + ring beam
    top = Mesh()
    add_prism(top, ring_poly(O[0], O[1], R_OUT + 0.04, R_OUT_I - 0.04).difference(sbox(-40, -40, X_PORTAL, 40)), H_OUT_BRICK, H_OUT_BRICK + 0.05, uvfun=arc_uv(O))
    S.obj('Outer_Wall_Coping', '03_Structure::Brick Walls', [('Aluminium_Cornice_Riveted', top)])
    a_lim = math.acos(X_PORTAL / (R_OUT - 0.25))
    gl = Mesh(); posts = Mesh()
    # glazing covers the whole ring except the portal: angles from a_lim .. 2pi-a_lim going through pi is the portal
    add_arc_panel(gl, O[0], O[1], R_OUT - 0.25, -a_lim, a_lim, H_OUT_BRICK + 0.05, Z_CLR_TOP, seg=300, inward=False)
    for k in range(int(2 * a_lim / D(3))):
        a = -a_lim + D(1.5) + k * D(3)
        x, y = on_outer(math.degrees(a), R_OUT - 0.30)
        add_box(posts, x - 0.03, x + 0.03, y - 0.03, y + 0.03, H_OUT_BRICK + 0.05, Z_CLR_TOP)
    S.obj('Gallery_Clerestory_Glazing', '05_Facade::Glazing', [('Glass_Clerestory', gl), ('Steel_Dark_Painted', posts)])
    rb = Mesh()
    add_prism(rb, ring_poly(O[0], O[1], R_OUT - 0.05, R_OUT_I - 0.10, 480), Z_CLR_TOP, Z_SOFFIT, uvfun=arc_uv(O))
    S.obj('Steel_Ring_Beam', '03_Structure::Roof Steel', [('Steel_Dark_Painted', rb)])


# ------------------------------------------------------------- 2 roof
def build_roof(S):
    # copper top
    prof = [(R_ROOF, 13.05)] + [(r, roof_z(r)) for r in np.linspace(R_ROOF, R_LANTERN + 0.10, 26)[1:]]
    top = Mesh(smooth_deg=30)
    # profile from outside inwards & upwards -> upward normals
    add_revolve(top, prof, seg=180, uv='angle', tile_u=48)
    S.obj('Roof_Copper_Vault', '04_Roof::Copper Roof', [('Copper_Roof_Aged', top)])
    # cornice / Aluminiumgesims
    fa = Mesh(smooth_deg=30)
    add_revolve(fa, [(R_ROOF, 12.45), (R_ROOF, 13.05)], seg=240, uv='arc')
    add_revolve(fa, [(R_ROOF - 0.06, 13.05), (R_ROOF, 13.05)], seg=240, uv='arc')
    add_revolve(fa, [(R_ROOF, 12.45), (R_ROOF - 0.06, 12.45)], seg=240, uv='arc')
    add_revolve(fa, [(R_ROOF - 0.06, 12.55), (R_ROOF - 0.06, 12.45)], seg=240, uv='arc')
    S.obj('Roof_Aluminium_Cornice', '04_Roof::Cornice', [('Aluminium_Cornice_Riveted', fa)])
    # exterior soffit (dark timber slats, radial)
    so = Mesh(smooth_deg=30)
    add_revolve(so, [(R_OUT - 0.05, Z_SOFFIT), (R_ROOF - 0.06, Z_SOFFIT)], seg=240, uv='angle', tile_u=130)
    S.obj('Roof_Soffit_Timber', '04_Roof::Soffit', [('Wood_Soffit_Dark', so)])
    # lantern curb + dome
    lc = Mesh(smooth_deg=30)
    add_revolve(lc, [(R_LANTERN + 0.10, roof_z(R_LANTERN + 0.10)), (R_LANTERN + 0.10, 15.15), (R_DOME + 0.05, 15.15)], seg=96, uv='arc')
    S.obj('Lantern_Curb', '04_Roof::Lantern', [('Copper_Roof_Aged', lc)])
    dome = Mesh(smooth_deg=40)
    h = Z_DOME_TOP - 15.15
    Rs = (R_DOME ** 2 + h ** 2) / (2 * h)
    prof = []
    for i in range(13):
        r = R_DOME * (1 - i / 12)
        z = 15.15 + (math.sqrt(max(0, Rs ** 2 - r ** 2)) - (Rs - h))
        prof.append((r, z))
    add_revolve(dome, prof, seg=96, uv='plan')
    S.obj('Plexiglas_Dome_D5m', '04_Roof::Lantern', [('Plexiglas_Dome_Frosted', dome)])
    # steel ring carrying the dome ("ein eiserner schwerer Ring")
    ir = Mesh(smooth_deg=30)
    add_revolve(ir, [(R_LANTERN, 14.85), (R_LANTERN - 0.18, 14.85), (R_LANTERN - 0.18, 15.15), (R_LANTERN, 15.15)][::-1], seg=96, uv='arc')
    S.obj('Lantern_Iron_Ring', '04_Roof::Lantern', [('Steel_Dark_Painted', ir)])


# ------------------------------------------------------------- 3 ceiling
def build_ceiling(S):
    nt, ns = 360, 14
    back = Mesh(smooth_deg=30)
    for i in range(nt):
        t0 = -math.pi + 2 * math.pi * i / nt; t1 = -math.pi + 2 * math.pi * (i + 1) / nt
        for j in range(ns):
            s0, s1 = j / ns, (j + 1) / ns
            a, b, c, d = ceil_point(t0, s0), ceil_point(t1, s0), ceil_point(t1, s1), ceil_point(t0, s1)
            back.quad(a, d, c, b, (0, 0), (0, 1), (1, 1), (1, 0))  # facing down
    S.obj('Ceiling_Backing (acoustic, dark)', '06_Interior::Ceiling', [('Ceiling_Backing_Dark', back)])
    # star-shaped slat ceiling ("sternförmige, hellfarbige Holzverschalung")
    N = 560
    sl = Mesh(smooth_deg=0)
    depth = 0.045
    for k in range(N):
        t = -math.pi + 2 * math.pi * (k + 0.5) / N
        tan = (-math.sin(t), math.cos(t), 0.0)
        pts = [ceil_point(t, s) for s in np.linspace(0, 1, 13)]
        L = 0.0
        for j in range(len(pts) - 1):
            p0, p1 = np.array(pts[j]), np.array(pts[j + 1])
            r0 = math.hypot(p0[0] - O[0], p0[1] - O[1]); r1 = math.hypot(p1[0] - O[0], p1[1] - O[1])
            w0 = 0.52 * 2 * math.pi * r0 / N; w1 = 0.52 * 2 * math.pi * r1 / N
            seg_l = float(np.linalg.norm(p1 - p0))
            T = np.array(tan)
            dz = np.array([0, 0, depth])
            A0, B0 = p0 - T * w0 / 2 - dz, p0 + T * w0 / 2 - dz
            A1, B1 = p1 - T * w1 / 2 - dz, p1 + T * w1 / 2 - dz
            A0t, B0t, A1t, B1t = A0 + dz, B0 + dz, A1 + dz, B1 + dz
            v0, v1 = L, L + seg_l
            # underside (facing down)
            sl.quad(tuple(A0), tuple(A1), tuple(B1), tuple(B0), (0, v0), (0, v1), (w1, v1), (w0, v0))
            # two flanks
            sl.quad(tuple(B0), tuple(B1), tuple(B1t), tuple(B0t), (0, v0), (0, v1), (depth, v1), (depth, v0))
            sl.quad(tuple(A0t), tuple(A1t), tuple(A1), tuple(A0), (depth, v0), (depth, v1), (0, v1), (0, v0))
            L += seg_l
    S.obj('Ceiling_Radial_Spruce_Slats (560 pcs)', '06_Interior::Ceiling', [('Wood_Spruce_Slat_Light', sl)])
    # gallery soffit closing between the ceiling rim and the outer wall
    gs = Mesh()
    g = circle_poly(O[0], O[1], R_OUT_I, 480).difference(circle_poly(C[0], C[1], R_IN - 0.02, 480)).difference(sbox(-40, -40, X_PORTAL, 40))
    add_cap(gs, g, Z_CEIL_RIM, up=False)
    S.obj('Gallery_Soffit', '06_Interior::Ceiling', [('Paint_Dark_Gallery', gs)])
    # lantern shaft with vertical slats
    sh = Mesh(smooth_deg=30)
    add_revolve(sh, [(R_LANTERN, Z_CEIL_TOP), (R_LANTERN, 14.85)][::-1], seg=96, uv='arc')
    S.obj('Lantern_Shaft', '06_Interior::Ceiling', [('Plaster_White', sh)])
    vs = Mesh()
    n = 150
    for k in range(n):
        a = 2 * math.pi * k / n
        c = (O[0] + (R_LANTERN - 0.16) * math.cos(a), O[1] + (R_LANTERN - 0.16) * math.sin(a), 0.5 * (Z_CEIL_TOP - 0.05 + 14.85))
        u = (math.cos(a), math.sin(a), 0); v = (-math.sin(a), math.cos(a), 0)
        add_oriented_box(vs, c, u, v, (0, 0, 1), 0.035, 0.016, 0.5 * (14.85 - Z_CEIL_TOP + 0.05))
    S.obj('Lantern_Vertical_Slats (150 pcs)', '06_Interior::Ceiling', [('Wood_Spruce_Slat_Light', vs)])


# ------------------------------------------------------------- 4 glass portal
def build_portal(S):
    x = X_PORTAL + 0.02
    gl = Mesh(); st = Mesh(); fins = Mesh(); stain = Mesh(); door = Mesh(); vest = Mesh(); vgl = Mesh()
    yE = Y_PORTAL + 0.25
    girders = [-6.0, -2.0, 2.0, 6.0]
    # four roof girders coming down as pilasters ("wie durch Lisenen gegliedert")
    for y in girders:
        add_box(st, x - 0.30, x + 0.15, y - 0.11, y + 0.11, 0.0, Z_SOFFIT + 0.4)
        add_box(st, -20.5, x + 0.15, y - 0.11, y + 0.11, Z_SOFFIT, Z_SOFFIT + 0.40)  # girder in the soffit
    # fins every ~1.0 m
    ys = []
    bays = [(-yE, -6.0), (-6.0, -2.0), (-2.0, 2.0), (2.0, 6.0), (6.0, yE)]
    for y0, y1 in bays:
        n = max(1, round((y1 - y0 - 0.22) / 1.0))
        for i in range(1, n):
            ys.append(y0 + (y1 - y0) * i / n)
    for y in ys:
        add_box(fins, x - 0.12, x + 0.02, y - 0.012, y + 0.012, 0.0, Z_CLR_TOP + 0.3)
    # frame head & sill
    add_box(st, x - 0.15, x + 0.15, -yE, yE, Z_CLR_TOP + 0.05, Z_SOFFIT)
    add_box(st, x - 0.10, x + 0.10, -yE, yE, -0.02, 0.06)
    # transom above doors
    add_box(st, x - 0.55, x + 0.08, -4.1, 4.1, 3.55, 3.75)
    # glass panes
    for y0, y1 in bays:
        if (y0, y1) == (-2.0, 2.0):
            # stained glass bay (Oberberger) from 3.75 to the top, bronze door below
            stain.quad((x, y1 - 0.11, 3.75), (x, y0 + 0.11, 3.75), (x, y0 + 0.11, Z_CLR_TOP + 0.05), (x, y1 - 0.11, Z_CLR_TOP + 0.05),
                       (0, 0), (1, 0), (1, 1), (0, 1))
            continue
        zb = 3.75 if abs(y0) < 6.5 or abs(y1) < 6.5 else 0.06
        gl.quad((x, y1, zb), (x, y0, zb), (x, y0, Z_CLR_TOP + 0.05), (x, y1, Z_CLR_TOP + 0.05), (y1, zb), (y0, zb), (y0, Z_CLR_TOP), (y1, Z_CLR_TOP))
    # lower glazing next to the vestibules
    for y0, y1 in ((-6.0, -3.95), (3.95, 6.0), (-1.62, -1.32), (1.32, 1.62)):
        gl.quad((x, y1, 0.06), (x, y0, 0.06), (x, y0, 3.55), (x, y1, 3.55), (y1, 0), (y0, 0), (y0, 3.5), (y1, 3.5))
    S.obj('West_Glass_Portal_Glazing', '05_Facade::West Glass Portal', [('Glass_Clear', gl), ('Steel_Dark_Painted', fins)])
    S.obj('West_Portal_Steel_Girders_Lisenen', '05_Facade::West Glass Portal', [('Steel_Dark_Painted', st)])
    S.obj('Stained_Glass_Wurzel_Jesse (J. Oberberger)', '05_Facade::Stained Glass', [('Stained_Glass_Oberberger', stain)])
    # bronze portal: two leaves, 6 reliefs by H. Kirchner
    for y0, y1 in ((-1.32, 0.0), (0.0, 1.32)):
        add_box(door, x - 0.06, x + 0.02, y0 + 0.005, y1 - 0.005, 0.0, 3.55)
    m = Mesh()
    for y0, y1 in ((-1.32, 0.0), (0.0, 1.32)):
        m.quad((x - 0.065, y1 - 0.005, 0.0), (x - 0.065, y0 + 0.005, 0.0), (x - 0.065, y0 + 0.005, 3.55), (x - 0.065, y1 - 0.005, 3.55), (0, 0), (1, 0), (1, 1), (0, 1))
        m.quad((x + 0.025, y0 + 0.005, 0.0), (x + 0.025, y1 - 0.005, 0.0), (x + 0.025, y1 - 0.005, 3.55), (x + 0.025, y0 + 0.005, 3.55), (0, 0), (1, 0), (1, 1), (0, 1))
    S.obj('Bronze_Portal_Doors (reliefs H. Kirchner)', '05_Facade::Doors', [('Bronze_Dark', door), ('Bronze_Portal_Relief', m)])
    # two glazed wind-lobbies (aluminium frames) projecting to the west
    for s in (1, -1):
        y0, y1 = sorted((s * 1.70, s * 3.90))
        x0, x1 = x - 1.10, x
        fw = 0.06
        for yy in (y0, y1):
            add_box(vest, x0 - fw / 2, x0 + fw / 2, yy - fw / 2, yy + fw / 2, 0.0, 3.05)   # corner posts
            add_box(vest, x0, x1, yy - fw / 2, yy + fw / 2, 0.0, 0.10)                     # side sills
        add_box(vest, x0 - 0.04, x1, y0 - 0.04, y1 + 0.04, 3.05, 3.45)  # deep aluminium head
        ym = 0.5 * (y0 + y1)
        add_box(vest, x0 - 0.03, x0 + 0.03, ym - 0.025, ym + 0.025, 0.0, 3.05)          # meeting stile
        for yy0, yy1 in ((y0 + 0.03, ym - 0.025), (ym + 0.025, y1 - 0.03)):
            add_box(vest, x0 - 0.03, x0 + 0.03, yy0, yy1, 0.0, 0.12)                     # door bottom rail
            add_box(vest, x0 - 0.03, x0 + 0.03, yy0, yy1, 2.95, 3.05)                    # door top rail
            add_box(vest, x0 - 0.09, x0 - 0.05, yy0 + 0.25, yy1 - 0.25, 1.00, 1.04)      # push bar
        vgl.quad((x0, y0, 0.02), (x0, y1, 0.02), (x0, y1, 3.05), (x0, y0, 3.05), (y0, 0), (y1, 0), (y1, 3), (y0, 3))
        vgl.quad((x1, y0, 0.02), (x0, y0, 0.02), (x0, y0, 3.05), (x1, y0, 3.05), (x1, 0), (x0, 0), (x0, 3), (x1, 3))
        vgl.quad((x0, y1, 0.02), (x1, y1, 0.02), (x1, y1, 3.05), (x0, y1, 3.05), (x0, 0), (x1, 0), (x1, 3), (x0, 3))
    S.obj('Wind_Lobbies_Aluminium_Glass', '05_Facade::Doors', [('Lamp_Aluminium', vest), ('Glass_Clear', vgl)])


# ------------------------------------------------------------- 5 floors / crescent
def build_floors(S):
    inner_floor = circle_poly(C[0], C[1], R_IN + 0.01, 480).difference(sbox(-40, -40, X_PORTAL, 40))
    fl = Mesh()
    add_cap(fl, inner_floor, 0.0, up=True)
    crescent = circle_poly(O[0], O[1], R_OUT_I + 0.01, 480).difference(circle_poly(C[0], C[1], R_IN_O - 0.01, 480)).difference(sbox(-40, -40, X_PORTAL, 40))
    add_cap(fl, crescent, 0.0, up=True)
    # door thresholds
    for sgn in (1, -1):
        a = D(71 * sgn); da = 1.25 / R_OUT / 2
        add_cap(fl, wedge_cut(O, R_OUT + 0.01, R_OUT_I - 0.02, a - da, a + da), 0.0, up=True)
        a = D(56 * sgn); da = 1.20 / R_IN / 2
        add_cap(fl, wedge_cut(C, R_IN_O + 0.02, R_IN - 0.02, a - da, a + da), 0.0, up=True)
    add_cap(fl, wedge_cut(C, R_IN_O + 0.02, R_IN - 0.02, -1.25 / R_IN, 1.25 / R_IN), 0.0, up=True)
    S.obj('Floor_Clinker_Warm_Red', '06_Interior::Floor', [('Clinker_Floor_Red', fl)])

    # crescent storeys: 1st floor choir loft (+3.00), 2nd organ (+6.00), 3rd (+9.00), gallery ring (+11.00)
    sect = sector_poly(O[0], O[1], 30, D(-84), D(84), 96)
    stair_holes = {3.0: (D(22), D(43)), 6.0: (D(-43), D(-22)), Z_GALLERY: (D(22), D(43))}
    slabs = Mesh(smooth_deg=10)
    for z in (3.0, 6.0):
        g = crescent.intersection(sect)
        a0, a1 = stair_holes[z]
        g = g.difference(wedge_cut(O, R_OUT_I + 0.1, R_OUT_I - 1.15, a0, a1))
        banded_solid(slabs, [(g, z - 0.22, z)], [], uvfun=arc_uv(O))
    gal = circle_poly(O[0], O[1], R_OUT_I + 0.005, 480).difference(circle_poly(C[0], C[1], R_IN_O - 0.005, 480)).difference(sbox(-40, -40, X_PORTAL, 40))
    gal = gal.difference(wedge_cut(O, R_OUT_I + 0.1, R_OUT_I - 1.15, *stair_holes[Z_GALLERY]))
    banded_solid(slabs, [(gal, Z_GALLERY - 0.20, Z_GALLERY)], [], uvfun=arc_uv(O))
    S.obj('Crescent_Floor_Slabs_and_Gallery', '09_Crescent::Slabs', [('Concrete_Slab', slabs)])
    # walking surfaces on the slabs
    top = Mesh()
    for z in (3.0, 6.0):
        g = crescent.intersection(sect)
        a0, a1 = stair_holes[z]
        g = g.difference(wedge_cut(O, R_OUT_I + 0.1, R_OUT_I - 1.15, a0, a1))
        add_cap(top, g, z + 0.003, up=True)
    add_cap(top, gal, Z_GALLERY + 0.003, up=True)
    S.obj('Crescent_Floor_Finish', '09_Crescent::Slabs', [('Clinker_Floor_Red', top)])

    # radial partitions inside the crescent (chapels, sacristy, paraments)
    pw = Mesh(smooth_deg=0)
    parts = []
    for phi, z1 in ((20, Z_GALLERY - 0.2), (-20, Z_GALLERY - 0.2), (46, Z_GALLERY - 0.2), (-46, Z_GALLERY - 0.2), (82, 3.0), (-82, 3.0)):
        a = D(phi)
        ln = LineString([(0, 0), (30 * math.cos(a), 30 * math.sin(a))]).buffer(0.0575, cap_style=2)
        g = ln.intersection(crescent)
        cuts = []
        # door in each partition
        mid = g.centroid
        cuts.append((Point(mid.x, mid.y).buffer(0.45, cap_style=3).intersection(g.buffer(0.2)), 0.0, 2.15))
        if z1 > 3.0:
            cuts.append((Point(mid.x, mid.y).buffer(0.45, cap_style=3).intersection(g.buffer(0.2)), 3.0, 5.15))
            cuts.append((Point(mid.x, mid.y).buffer(0.45, cap_style=3).intersection(g.buffer(0.2)), 6.0, 8.15))
        banded_solid(pw, [(g, 0.0, z1)], cuts)
    S.obj('Crescent_Partitions', '09_Crescent::Partitions', [('Plaster_White', pw)])

    # stair flights along the outer wall
    st = Mesh()
    flights = ((0.0, 3.0, stair_holes[3.0]), (3.0, 6.0, stair_holes[6.0]), (6.0, Z_GALLERY, stair_holes[Z_GALLERY]))
    for (z0, z1, (a0, a1)) in flights:
        n = int(round((z1 - z0) / 0.17))
        for i in range(n):
            t0 = a0 + (a1 - a0) * i / n; t1 = a0 + (a1 - a0) * (i + 1) / n
            if z0 == 3.0:  # southern flight runs the other way
                t0, t1 = a1 - (a1 - a0) * (i + 1) / n, a1 - (a1 - a0) * i / n
            arc_box(st, O, R_OUT_I - 1.10, R_OUT_I - 0.02, t0, t1, z0, z0 + (i + 1) * (z1 - z0) / n, seg=2)
    S.obj('Crescent_Stairs', '09_Crescent::Stairs', [('Concrete_Slab', st)])
    # stair / gallery handrails
    hr = Mesh()
    for (z0, z1, (a0, a1)) in flights:
        for i in range(19):
            t = a0 + (a1 - a0) * i / 18
            x, y = on_outer(math.degrees(t), R_OUT_I - 1.12)
            zz = z0 + (i if z0 != 3.0 else 18 - i) * (z1 - z0) / 18
            if i % 3 == 0:
                add_box(hr, x - 0.015, x + 0.015, y - 0.015, y + 0.015, zz, zz + 0.95)
        for i in range(18):
            ta = a0 + (a1 - a0) * i / 18; tb = a0 + (a1 - a0) * (i + 1) / 18
            za = z0 + (i if z0 != 3.0 else 18 - i) * (z1 - z0) / 18 + 0.95
            zb = z0 + (i + 1 if z0 != 3.0 else 17 - i) * (z1 - z0) / 18 + 0.95
            pa = on_outer(math.degrees(ta), R_OUT_I - 1.12); pb = on_outer(math.degrees(tb), R_OUT_I - 1.12)
            d = np.array([pb[0] - pa[0], pb[1] - pa[1], zb - za]); Ld = np.linalg.norm(d); u = d / Ld
            v = np.cross([0, 0, 1], u); v /= np.linalg.norm(v); w = np.cross(u, v)
            add_oriented_box(hr, ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (za + zb) / 2), u, v, w, Ld / 2, 0.02, 0.02)
    S.obj('Crescent_Handrails', '09_Crescent::Stairs', [('Steel_Dark_Painted', hr)])


# ------------------------------------------------------------- 6 liturgy
def build_liturgy(S):
    L = '07_Liturgy::'
    # podium "um mehrere niedrige Stufen", extends from the east towards the centre
    pod = Mesh()
    add_box(pod, -1.85, 9.60, -3.80, 3.80, 0.0, 0.16)
    add_box(pod, -0.70, 9.25, -2.10, 2.10, 0.16, 0.32)
    S.obj('Altar_Podium_Steps', L + 'Sanctuary', [('Clinker_Floor_Red', pod)])
    # Opferaltar: 2x2 m Nagelfluh block below the dome
    alt = Mesh()
    add_box(alt, 0.40, 2.40, -1.00, 1.00, 0.32, 1.22)
    add_box(alt, 0.37, 2.43, -1.03, 1.03, 1.22, 1.30)
    S.obj('Main_Altar_Nagelfluh_2x2m', L + 'Sanctuary', [('Nagelfluh_Conglomerate', alt)])
    # altar cloth runner + 6 candles on the east edge (pg. 90 photo)
    cl = Mesh(); cd = Mesh(); wx = Mesh()
    add_box(cl, 0.45, 2.35, -1.035, 1.035, 1.30, 1.305)
    for i in range(6):
        y = -0.85 + i * 0.34
        add_cylinder(cd, 2.15, y, 0.045, 1.305, 1.34, 12)
        add_cylinder(cd, 2.15, y, 0.012, 1.34, 1.62, 8)
        add_cylinder(wx, 2.15, y, 0.025, 1.62, 1.86, 10)
    S.obj('Altar_Linen', L + 'Sanctuary', [('Plaster_White', cl)])
    S.obj('Altar_Candlesticks', L + 'Sanctuary', [('Bronze_Dark', cd), ('Candle_Wax', wx)])
    # Sakramentsaltar with Tabernacle (Prof. Franz Rickert, fire-gilded tombak), cross-shaped superstructure
    sa = Mesh(); tb = Mesh()
    add_box(sa, 7.50, 8.10, -0.85, -0.25, 0.32, 1.20)
    add_box(sa, 7.50, 8.10, 0.25, 0.85, 0.32, 1.20)
    add_box(sa, 7.40, 8.20, -1.05, 1.05, 1.20, 1.30)
    add_box(tb, 7.55, 8.05, -0.28, 0.28, 1.30, 1.92)
    add_box(tb, 7.72, 7.88, -0.07, 0.07, 1.92, 3.10)
    add_box(tb, 7.72, 7.88, -0.55, 0.55, 2.62, 2.78)
    add_box(tb, 7.50, 8.10, -0.33, 0.33, 1.92, 1.96)
    S.obj('Sacrament_Altar', L + 'Sanctuary', [('Nagelfluh_Conglomerate', sa)])
    S.obj('Tabernacle_Rickert_Gilded_Tombak', L + 'Sanctuary', [('Tombak_FireGilded', tb)])
    # Ambo (2013) forged bronze-tombak
    am = Mesh()
    add_box(am, -0.55, -0.15, 2.55, 2.95, 0.16, 1.08)
    am2 = Mesh(); add_oriented_box(am2, (-0.42, 2.75, 1.17), (math.cos(D(-25)), 0, math.sin(D(-25))), (0, 1, 0), (-math.sin(D(-25)), 0, math.cos(D(-25))), 0.30, 0.34, 0.02)
    am.extend(am2)
    S.obj('Ambo_Bronze_Tombak', L + 'Sanctuary', [('Tombak_FireGilded', am)])
    # processional cross
    pc = Mesh()
    add_cylinder(pc, -0.30, -2.75, 0.18, 0.16, 0.22, 16)
    add_cylinder(pc, -0.30, -2.75, 0.02, 0.22, 2.40, 8)
    add_box(pc, -0.32, -0.28, -3.00, -2.50, 2.05, 2.09)
    add_box(pc, -0.32, -0.28, -2.77, -2.73, 1.80, 2.55)
    S.obj('Processional_Cross', L + 'Sanctuary', [('Bronze_Dark', pc)])
    # presider chair and two stools (oak)
    ch = Mesh()
    for (x, y, w) in ((6.2, -1.55, 0.6), (6.2, 1.55, 0.5), (6.9, 1.55, 0.5)):
        z = 0.32
        add_box(ch, x - 0.24, x + 0.24, y - w / 2, y + w / 2, z + 0.42, z + 0.46)          # seat
        add_box(ch, x + 0.19, x + 0.23, y - w / 2, y + w / 2, z + 0.70, z + 0.95)          # back board
        for dx in (-0.21, 0.20):
            for dy in (-w / 2 + 0.03, w / 2 - 0.03):
                add_box(ch, x + dx - 0.02, x + dx + 0.02, dy + y - 0.02, dy + y + 0.02, z, z + 0.42 if dx < 0 else z + 0.95)
    S.obj('Sedilia', L + 'Sanctuary', [('Wood_Ash_Pew', ch)])
    # baptismal font (Sep Ruf) in the eastern chapel behind the grille
    fx, fy = 13.95, 0.0
    fo = Mesh(smooth_deg=40)
    add_revolve(fo, [(0.0, 0.0), (0.42, 0.0), (0.42, 0.06), (0.36, 0.10), (0.36, 0.78), (0.48, 0.82), (0.48, 0.92), (0.0, 0.92)], fx, fy, seg=48, uv='arc')
    S.obj('Baptismal_Font_Sep_Ruf', L + 'Baptistery', [('Nagelfluh_Conglomerate', fo)])
    li = Mesh(smooth_deg=40)
    add_revolve(li, [(0.0, 0.92), (0.47, 0.92), (0.40, 1.00), (0.05, 1.06), (0.04, 1.22), (0.0, 1.24)], fx, fy, seg=48, uv='arc')
    S.obj('Font_Lid_Bronze', L + 'Baptistery', [('Bronze_Dark', li)])
    # Madonna (Sr. M. Bernardine Weber, wood) on a pedestal near the north side door
    mx, my = on_inner(40, R_IN - 0.75)
    md = Mesh()
    add_box(md, mx - 0.22, mx + 0.22, my - 0.22, my + 0.22, 0.0, 1.05)
    S.obj('Madonna_Pedestal', L + 'Devotional', [('Nagelfluh_Conglomerate', md)])
    fig = Mesh(smooth_deg=50)
    add_revolve(fig, [(0, 1.05), (0.20, 1.05), (0.22, 1.30), (0.19, 1.70), (0.16, 1.95), (0.13, 2.05), (0.10, 2.10), (0.11, 2.20), (0.09, 2.32), (0.0, 2.36)], mx, my, seg=24, uv='arc')
    S.obj('Madonna_Wood_Figure', L + 'Devotional', [('Wood_Carved_Lime', fig)])
    # stations of the cross (Prof. Karl Knappe 1968/69) - 14 bronze reliefs
    sc = Mesh()
    angs = [64, 80, 96, 112, 126, 140, 150]
    for sgn in (1, -1):
        for phi in angs:
            a = D(min(phi, 140) * sgn) if phi < 150 else D(133 * sgn)
            da = 0.48 / R_IN / 2
            arc_box(sc, C, R_IN - 0.035, R_IN - 0.002, a - da, a + da, 1.30, 1.92, seg=2)
    S.obj('Stations_of_the_Cross_14_Bronze_Reliefs (K. Knappe)', L + 'Devotional', [('Bronze_Dark', sc)])
    # holy water stoups at the doors
    hw = Mesh(smooth_deg=40)
    for sgn in (1, -1):
        x, y = on_inner(56 * sgn + 6 * sgn, R_IN - 0.15)
        add_revolve(hw, [(0.0, 0.98), (0.14, 1.0), (0.17, 1.12), (0.0, 1.10)], x, y, seg=24, uv='arc')
        x, y = X_PORTAL + 0.45, 4.3 * sgn
        add_revolve(hw, [(0.0, 0.98), (0.14, 1.0), (0.17, 1.12), (0.0, 1.10)], x, y, seg=24, uv='arc')
    S.obj('Holy_Water_Stoups', L + 'Devotional', [('Nagelfluh_Conglomerate', hw)])

    # organ (C. Schuster & Söhne, 27 registers) - 2nd floor of the crescent, behind the grilles
    pipes = Mesh(smooth_deg=40); case = Mesh(); con = Mesh()
    arc_box(case, O, R_OUT_I - 2.4, R_OUT_I - 0.1, D(-16), D(16), 6.0, 6.75, seg=20)
    for row, rr in enumerate((R_OUT_I - 0.45, R_OUT_I - 0.95, R_OUT_I - 1.50)):
        n = 26 - row * 4
        for i in range(n):
            a = D(-15 + 30 * (i + 0.5) / n)
            x, y = O[0] + rr * math.cos(a), O[1] + rr * math.sin(a)
            centre = abs(i - (n - 1) / 2) / ((n - 1) / 2)
            h = (2.2 - row * 0.45) * (0.45 + 0.55 * (centre ** 1.3)) + 0.2
            r = 0.035 + 0.035 * (h / 2.4)
            add_cylinder(pipes, x, y, r, 6.85, 6.85 + h, 12, caps=True)
            add_cylinder(pipes, x, y, r * 0.5, 6.75, 6.85, 8, r1=r, caps=False)
    S.obj('Organ_Pipes (Schuster & Söhne)', '09_Crescent::Organ', [('Organ_Tin', pipes), ('Wood_Dark_Stain', case)])
    x, y = on_outer(0, R_OUT_I - 1.6)
    add_box(con, x - 0.35, x + 0.35, -0.75, 0.75, 3.0, 4.10)
    add_box(con, x - 0.90, x - 0.55, -0.60, 0.60, 3.0, 3.50)
    S.obj('Organ_Console_Choir_Loft', '09_Crescent::Organ', [('Wood_Dark_Stain', con)])


# ------------------------------------------------------------- 7 pews (component)
def pew_def(S, name, L):
    wood = Mesh(); steel = Mesh()
    add_box(wood, -L / 2, L / 2, -0.17, 0.17, 0.42, 0.465)            # seat plank
    add_box(wood, -L / 2, L / 2, 0.20, 0.235, 0.74, 0.88)             # back rail
    add_box(wood, -L / 2, L / 2, -0.62, -0.48, 0.17, 0.205)           # kneeler
    add_box(wood, -L / 2, L / 2, -0.56, -0.52, 0.80, 0.84)            # book rail / hand rest
    uv_swap(wood)
    nlegs = max(2, int(L / 1.6) + 1)
    for i in range(nlegs):
        x = -L / 2 + 0.25 + (L - 0.5) * i / (nlegs - 1)
        add_box(steel, x - 0.015, x + 0.015, -0.16, -0.13, 0.0, 0.42)
        add_box(steel, x - 0.015, x + 0.015, 0.19, 0.22, 0.0, 0.88)
        add_box(steel, x - 0.015, x + 0.015, -0.16, 0.22, 0.38, 0.41)
        add_box(steel, x - 0.015, x + 0.015, -0.56, -0.53, 0.0, 0.80)
        add_box(steel, x - 0.015, x + 0.015, -0.60, -0.13, 0.05, 0.08)
    S.define(name, '08_Furniture::Pews', [('Wood_Ash_Pew', wood), ('Steel_Dark_Painted', steel)])


def build_pews(S):
    pew_def(S, 'Pew_5.10m', 5.10)
    pew_def(S, 'Pew_2.90m', 2.90)
    lay = '08_Furniture::Pews'
    k = 0
    # western block: benches N-S, facing east
    for x in (-7.45, -6.48, -5.51, -4.53, -3.56):
        for yc in (3.82, -3.82):
            place(S, f'Pew_W_{k:02d}', lay, 'Pew_5.10m', x, yc, 0.0, math.pi / 2); k += 1
    # northern block (facing south) and southern block (facing north)
    for sgn in (1, -1):
        for y in (9.90, 8.93, 7.96, 6.98, 6.00):
            place(S, f'Pew_{"N" if sgn > 0 else "S"}_{k:02d}', lay, 'Pew_5.10m', 0.73, sgn * y, 0.0, 0.0 if sgn > 0 else math.pi); k += 1
        for y in (6.98, 6.00):
            place(S, f'Pew_{"N" if sgn > 0 else "S"}_{k:02d}', lay, 'Pew_2.90m', 5.95, sgn * y, 0.0, 0.0 if sgn > 0 else math.pi); k += 1


# ------------------------------------------------------------- 8 luminaires + lights
def build_lighting(S):
    # pendant luminaire component: aluminium cylinder, opal diffuser at bottom
    diff = Mesh()
    body = Mesh(smooth_deg=40)
    add_revolve(body, [(0.105, 0.02), (0.11, 0.0), (0.11, 0.46), (0.04, 0.46), (0.012, 0.50)], seg=32, uv='arc')
    add_revolve(body, [(0.012, 0.50), (0.012, 0.0)][::-1], seg=8)
    add_revolve(diff, [(0.0, 0.025), (0.105, 0.025)], seg=32, uv='plan')
    diff = flip(diff)
    S.define('Pendant_Cylinder_Luminaire', '10_Luminaires::Pendants', [('Lamp_Aluminium', body), ('Emissive_Diffuser_2700K', diff)])
    cables = Mesh()
    pend = []
    for i in range(12):
        a = D(15 + 30 * i)
        pend.append((7.6 * math.cos(a), 7.6 * math.sin(a), 4.6 if i % 2 == 0 else 5.9))
    for i in range(6):
        a = D(30 + 60 * i)
        pend.append((4.4 * math.cos(a) - 1.0, 4.4 * math.sin(a), 7.1))
    for i in range(6):
        a = D(150 + 12 * i)
        pend.append((C[0] + 11.0 * math.cos(a) * 0.95, 11.0 * math.sin(a) * 0.95, 6.6))
    for i in range(6):
        a = D(-150 - 12 * i)
        pend.append((C[0] + 11.0 * math.cos(a) * 0.95, 11.0 * math.sin(a) * 0.95, 6.6))
    for k, (x, y, z) in enumerate(pend):
        if x < X_PORTAL + 1.5:
            continue
        place(S, f'Pendant_{k:02d}', '10_Luminaires::Pendants', 'Pendant_Cylinder_Luminaire', x, y, z)
        zc = ceil_z_at(x, y)
        add_cylinder(cables, x, y, 0.004, z + 0.5, zc, 6, caps=False)
        S.light(name=f'L_Pendant_{k:02d}', layer='11_Lights::Interior Pendants', kind='spot', pos=(x, y, z - 0.01), dir=(0, 0, -1),
                color=K(2700), watts=75, spot_deg=70, hotspot=0.55)
    S.obj('Pendant_Cables', '10_Luminaires::Pendants', [('Steel_Dark_Painted', cables)])

    # wall sconces (small aluminium cylinders, up/down light) at +4.60
    sb = Mesh(smooth_deg=40); sd = Mesh()
    add_cylinder(sb, 0, 0, 0.045, -0.12, 0.12, 20, caps=False)
    add_box(sb, -0.10, -0.045, -0.01, 0.01, -0.01, 0.01)
    add_revolve(sd, [(0.0, 0.118), (0.044, 0.118)], seg=20, uv='plan')
    add_revolve(sd, [(0.044, -0.118), (0.0, -0.118)], seg=20, uv='plan')
    S.define('Wall_Sconce_UpDown', '10_Luminaires::Wall Sconces', [('Lamp_Aluminium', sb), ('Emissive_Diffuser_2700K', sd)])
    k = 0
    for phi in list(range(30, 140, 13)) + [-p for p in range(30, 140, 13)]:
        x, y = on_inner(phi, R_IN - 0.11)
        place(S, f'Sconce_{k:02d}', '10_Luminaires::Wall Sconces', 'Wall_Sconce_UpDown', x, y, 4.60, D(phi))
        S.light(name=f'L_Sconce_Up_{k:02d}', layer='11_Lights::Wall Sconces', kind='spot', pos=(x, y, 4.75), dir=(0, 0, 1), color=K(3000), watts=20, spot_deg=50, hotspot=0.6)
        S.light(name=f'L_Sconce_Down_{k:02d}', layer='11_Lights::Wall Sconces', kind='spot', pos=(x, y, 4.45), dir=(0, 0, -1), color=K(3000), watts=15, spot_deg=50, hotspot=0.6)
        k += 1

    # neon tubes on the gallery parapet (hidden light slot under the ceiling)
    ne = Mesh(smooth_deg=40)
    a_lim = math.acos((X_PORTAL + 0.3 - C[0]) / (R_IN + 0.2))
    nseg = 40
    for i in range(nseg):
        a0 = -a_lim + 2 * a_lim * i / nseg; a1 = -a_lim + 2 * a_lim * (i + 1) / nseg
        p0 = on_inner(math.degrees(a0), R_IN + 0.18); p1 = on_inner(math.degrees(a1), R_IN + 0.18)
        S.light(name=f'L_Gallery_Neon_{i:02d}', layer='11_Lights::Gallery Neon Slot', kind='linear', pos=(p0[0], p0[1], H_IN + 0.06),
                vec=(p1[0] - p0[0], p1[1] - p0[1], 0), color=K(3500), watts=36)
    add_revolve(ne, [(R_IN + 0.18 - 0.013, H_IN + 0.06), (R_IN + 0.18 + 0.013, H_IN + 0.06)], C[0], C[1], seg=240, a0=-a_lim, a1=a_lim, uv='arc')
    add_revolve(ne, [(R_IN + 0.18, H_IN + 0.047), (R_IN + 0.18, H_IN + 0.073)], C[0], C[1], seg=240, a0=-a_lim, a1=a_lim, uv='arc')
    S.obj('Gallery_Neon_Tubes', '10_Luminaires::Neon', [('Emissive_Neon_3500K', ne)])
    # neon ring in the lantern ("im Kranz der Kuppelöffnung")
    rn = Mesh(smooth_deg=40)
    add_revolve(rn, [(R_LANTERN - 0.07, 14.70), (R_LANTERN - 0.07, 14.73)], seg=96, uv='arc')
    S.obj('Lantern_Neon_Ring', '10_Luminaires::Neon', [('Emissive_Neon_3500K', rn)])
    for i in range(16):
        a0 = 2 * math.pi * i / 16; a1 = 2 * math.pi * (i + 1) / 16
        r = R_LANTERN - 0.07
        S.light(name=f'L_Lantern_Neon_{i:02d}', layer='11_Lights::Lantern Neon Ring', kind='linear', pos=(r * math.cos(a0), r * math.sin(a0), 14.68),
                vec=(r * (math.cos(a1) - math.cos(a0)), r * (math.sin(a1) - math.sin(a0)), 0), color=K(3500), watts=36)

    # accent spots from the gallery
    tgt_alt = (1.4, 0.0, 1.3)
    for i, phi in enumerate((150, -150, 165, -165)):
        x, y = on_inner(phi, R_IN + 0.3)
        S.light(name=f'L_Accent_Altar_{i}', layer='11_Lights::Accent', kind='spot', pos=(x, y, 11.7), target=tgt_alt, color=K(3200), watts=150, spot_deg=14, hotspot=0.75)
    for name, tgt, src in (('L_Accent_Tabernacle', (7.8, 0, 2.2), on_inner(120, R_IN + 0.3)),
                           ('L_Accent_Ambo', (-0.4, 2.75, 1.2), on_inner(-120, R_IN + 0.3)),
                           ('L_Accent_Madonna', (*on_inner(40, R_IN - 0.75), 1.8), on_inner(-90, R_IN + 0.3))):
        S.light(name=name, layer='11_Lights::Accent', kind='spot', pos=(src[0], src[1], 11.7), target=tgt, color=K(3200), watts=100, spot_deg=12, hotspot=0.75)
    S.light(name='L_Baptistery_Down', layer='11_Lights::Accent', kind='spot', pos=(13.95, 0, 2.85), dir=(0, 0, -1), color=K(3000), watts=60, spot_deg=60, hotspot=0.5)
    S.light(name='L_Choir_Loft', layer='11_Lights::Crescent Rooms', kind='point', pos=(14.0, 0, 5.4), color=K(3000), watts=40)
    S.light(name='L_Organ_Room', layer='11_Lights::Crescent Rooms', kind='point', pos=(14.0, 0, 8.6), color=K(3000), watts=40)

    # bollards on the circuitus + soffit downlights
    bo = Mesh(smooth_deg=40); bd = Mesh()
    add_cylinder(bo, 0, 0, 0.065, 0.0, 0.62, 24, caps=True)
    add_cylinder(bd, 0, 0, 0.066, 0.40, 0.52, 24, caps=False)
    S.define('Bollard_Light', '10_Luminaires::Exterior', [('Lamp_Aluminium', bo), ('Emissive_Diffuser_2700K', bd)])
    for i in range(N_RODS):
        a = math.pi + 2 * math.pi * (i + 0.5) / N_RODS + math.pi / N_RODS
        x, y = 17.35 * math.cos(a), 17.35 * math.sin(a)
        if x < X_PORTAL - 1.5 and abs(y) < 8:
            continue
        place(S, f'Bollard_{i:02d}', '10_Luminaires::Exterior', 'Bollard_Light', x, y, -0.03)
        S.light(name=f'L_Bollard_{i:02d}', layer='11_Lights::Exterior Bollards', kind='point', pos=(x, y, 0.46), color=K(3000), watts=10)
    for i in range(N_RODS):
        a = math.pi + 2 * math.pi * i / N_RODS + math.pi / N_RODS
        x, y = 18.2 * math.cos(a), 18.2 * math.sin(a)
        S.light(name=f'L_Soffit_Wallwash_{i:02d}', layer='11_Lights::Exterior Soffit Wallwash (optional)', kind='spot', pos=(x, y, Z_SOFFIT - 0.05),
                target=(16.0 * math.cos(a), 16.0 * math.sin(a), 4.0), color=K(3000), watts=40, spot_deg=40, hotspot=0.5, off=True)


# ------------------------------------------------------------- 9 rods + counterweights
def build_rods(S):
    rod = Mesh(smooth_deg=40)
    add_cylinder(rod, 0, 0, 0.0571, -1.20, Z_SOFFIT + 0.05, 20, caps=False)
    add_cylinder(rod, 0, 0, 0.09, Z_SOFFIT - 0.12, Z_SOFFIT, 20, caps=True)
    cov = Mesh(smooth_deg=40)
    add_cylinder(cov, 0, 0, 0.32, -0.035, -0.015, 32, caps=True)
    S.define('Pendulum_Rod_D114', '03_Structure::Pendulum Rods', [('Steel_Galvanized_Rods', rod), ('Steel_Dark_Painted', cov)])
    cw = Mesh()
    add_box(cw, -0.55, 0.55, -0.55, 0.55, -2.80, -1.20)
    add_cylinder(cw, 0, 0, 0.03, -1.20, -1.0, 8)
    S.define('Counterweight_Concrete_Buried', '03_Structure::Counterweights (below ground)', [('Concrete_Slab', cw)])
    for i in range(N_RODS):
        a = math.pi + 2 * math.pi * i / N_RODS + math.pi / N_RODS
        x, y = R_RODS * math.cos(a), R_RODS * math.sin(a)
        place(S, f'Rod_{i + 1:02d}', '03_Structure::Pendulum Rods', 'Pendulum_Rod_D114', x, y, 0.0)
        place(S, f'Counterweight_{i + 1:02d}', '03_Structure::Counterweights (below ground)', 'Counterweight_Concrete_Buried', x, y, 0.0)


# ------------------------------------------------------------- 10 site
def build_site(S):
    Lsite = '01_Site::'
    ring = circle_poly(O[0], O[1], 21.2, 240).difference(circle_poly(O[0], O[1], R_OUT - 0.01, 240))
    forecourt = sbox(-28.7, -16.0, -16.0, 16.0)
    path_n = sbox(-28.7, 16.0, -24.0, 33.0)       # path to the street
    path_s = sbox(-28.7, -23.5, -18.0, -16.0)     # to the bell wall
    portal_apron = sbox(X_PORTAL - 8, -Y_PORTAL - 0.6, X_PORTAL + 0.02, Y_PORTAL + 0.6).difference(circle_poly(C[0], C[1], R_IN, 240))
    paving = unary_union([ring, forecourt, path_n, path_s, portal_apron]).difference(circle_poly(C[0], C[1], R_IN, 240).intersection(sbox(X_PORTAL, -20, 30, 20)))
    paving = paving.difference(circle_poly(O[0], O[1], R_OUT - 0.01, 240).intersection(sbox(X_PORTAL, -30, 30, 30)))
    pv = Mesh()
    add_cap(pv, paving, -0.03, up=True)
    S.obj('Paving_Circuitus_and_Forecourt', Lsite + 'Paving', [('Paving_Hex_Concrete', pv)])
    grid = sbox(-16.0, -27.0, 27.0, 27.0).difference(paving).difference(circle_poly(O[0], O[1], R_OUT, 240)).difference(sbox(-40, -12, X_PORTAL + 0.01, 12))
    gp = Mesh()
    add_cap(gp, grid, -0.035, up=True)
    S.obj('Grass_Pavers', Lsite + 'Paving', [('Paving_GrassGrid', gp)])
    road = sbox(-95, 34.0, 80, 42.0)
    side = sbox(-95, 32.0, 80, 34.0)
    rd = Mesh(); sw = Mesh()
    add_cap(rd, road, -0.06, up=True)
    add_prism(sw, side, -0.06, 0.06)
    S.obj('Gotthelfstrasse', Lsite + 'Street', [('Asphalt', rd)])
    S.obj('Sidewalk', Lsite + 'Street', [('Paving_Hex_Concrete', sw)])
    hall = sbox(-47, 13, -29, 31)
    pars = sbox(-78, -50, -36, -38)
    bell = sbox(-35.5, -25.4, -23.0, -24.2)
    lawn = sbox(-95, -80, 80, 32.0).difference(unary_union([paving, grid, circle_poly(O[0], O[1], R_OUT, 240), hall, pars]))
    lw = Mesh()
    add_cap(lw, lawn, -0.05, up=True)
    S.obj('Lawn', Lsite + 'Lawn', [('Lawn', lw)])
    # brick wall from the parish hall past the facade to the bell wall
    bw = Mesh()
    wall = LineString([(-29.0, 13.0), (-29.0, -24.2)]).buffer(0.18, cap_style=2)
    banded_solid(bw, [(wall, -0.05, 2.40)], [(sbox(-30, 15.5, -28, 17.5), -1, 2.2), (sbox(-30, -19.0, -28, -17.0), -1, 2.2)])
    S.obj('Brick_Enclosure_Wall', Lsite + 'Walls', [('Brick_HardFired', bw)])
    # trees: three variants
    for v in range(3):
        tr = Mesh(smooth_deg=40); fo = Mesh(smooth_deg=50)
        h = (7.0, 10.0, 13.0)[v]
        add_cylinder(tr, 0, 0, 0.16 + 0.08 * v, 0.0, h * 0.55, 10, caps=False, r1=0.10 + 0.05 * v)
        rng = np.random.default_rng(10 + v)
        for b in range(7 + 2 * v):
            ang = rng.random() * 2 * math.pi; rr = rng.random() * h * 0.22
            add_sphere(fo, math.cos(ang) * rr, math.sin(ang) * rr, h * (0.62 + rng.random() * 0.25), h * (0.16 + rng.random() * 0.08), seg=10, rings=7, sz=0.85, jitter=0.25, rng=rng)
        S.define(f'Tree_Deciduous_{v + 1}', Lsite + 'Trees', [('Bark', tr), ('Foliage', fo)])
    trees = [(-12, 30), (2, 31), (14, 29), (26, 22), (33, 18), (34, -20), (28, -27), (18, -31), (4, -33), (-10, -32),
             (-40, 2), (-45, -12), (-52, 8), (-60, -20), (-58, 20), (-70, 0), (-35, 42.0 - 50), (40, 25), (45, -30), (55, 5),
             (-20, -45), (-5, -55), (15, -52), (35, -48), (-85, 25), (-88, -30), (60, -55), (65, 28)]
    for i, (x, y) in enumerate(trees):
        v = i % 3
        place(S, f'Tree_{i:02d}', Lsite + 'Trees', f'Tree_Deciduous_{v + 1}', x, y, -0.05, RNG.random() * 6.28,
              scale=(1 + 0.15 * RNG.standard_normal(),) * 2 + (1 + 0.12 * RNG.standard_normal(),))

    La = '02_Ancillary::'
    # parish hall (flat-roofed brick, square, alu cornice; honeycomb + cast glass east face)
    ph = Mesh(); hc = Mesh(); rf = Mesh(); al = Mesh()
    banded_solid(ph, [(hall.difference(sbox(-46.6, 13.4, -29.4, 30.6)), -0.05, 6.0)],
                 [(sbox(-47.5, 18, -46, 26), 0.9, 4.2), (sbox(-42, 30.5, -34, 31.5), 0.9, 4.2)])
    hc.quad((-28.98, 13.4, 0.0), (-28.98, 30.6, 0.0), (-28.98, 30.6, 6.0), (-28.98, 13.4, 6.0), (13.4, 0), (30.6, 0), (30.6, 6), (13.4, 6))
    add_box(rf, -47.3, -28.7, 12.7, 31.3, 6.0, 6.25)
    add_box(al, -47.35, -28.65, 12.65, 31.35, 6.0, 6.45)
    S.obj('Parish_Hall_Pfarrsaal', La + 'Parish Hall', [('Brick_HardFired', ph), ('Concrete_Honeycomb_CastGlass', hc), ('Aluminium_Cornice_Riveted', al)])
    gw = Mesh()
    gw.quad((-47.02, 26, 0.9), (-47.02, 18, 0.9), (-47.02, 18, 4.2), (-47.02, 26, 4.2), (26, .9), (18, .9), (18, 4.2), (26, 4.2))
    S.obj('Parish_Hall_Glazing', La + 'Parish Hall', [('Glass_Clear', gw)])
    # bell wall (Glockenwand 13.5 h x 12.5 w, board-formed concrete) with three bells (Perner 1963: e', fis', a')
    bwm = Mesh()
    cuts = [(sbox(-34.2 + i * 3.9, -26, -31.6 + i * 3.9, -23), 9.0, 12.4) for i in range(3)]
    banded_solid(bwm, [(bell, -0.05, 13.5)], cuts)
    S.obj('Bell_Wall_Glockenwand', La + 'Bell Wall', [('Concrete_BoardFormed', bwm)])
    bells = Mesh(smooth_deg=50); yoke = Mesh()
    for i, sc in enumerate((1.0, 0.89, 0.75)):
        cx = -32.9 + i * 3.9; cy = -24.8
        prof = [(0.0, 11.95), (0.18 * sc, 11.95), (0.30 * sc, 11.80), (0.34 * sc, 11.45), (0.40 * sc, 11.15), (0.55 * sc, 10.85), (0.62 * sc, 10.78)]
        prof = [(r, 11.95 - (11.95 - z) * sc) for r, z in prof]
        add_revolve(bells, prof[::-1], cx, cy, seg=32, uv='arc')
        add_revolve(bells, [(0.55 * sc, 11.95 - 1.10 * sc), (0.0, 11.95 - 0.9 * sc)], cx, cy, seg=32, uv='arc')
        add_box(yoke, cx - 1.30, cx + 1.30, cy - 0.10, cy + 0.10, 11.95, 12.20)
    S.obj('Bells_Ecclesia_Maria_Capistran', La + 'Bell Wall', [('Bell_Bronze', bells), ('Steel_Dark_Painted', yoke)])
    # parsonage (long single-storey building)
    pa = Mesh(); pg = Mesh(); pr = Mesh()
    banded_solid(pa, [(pars.difference(sbox(-77.6, -49.6, -36.4, -38.4)), -0.05, 3.6)], [(sbox(-76, -38.6, -38, -37.6), 1.0, 2.9)])
    pg.quad((-38, -38.0, 1.0), (-76, -38.0, 1.0), (-76, -38.0, 2.9), (-38, -38.0, 2.9), (-38, 1), (-76, 1), (-76, 2.9), (-38, 2.9))
    add_box(pr, -78.4, -35.6, -50.4, -37.4, 3.6, 3.95)
    S.obj('Parsonage_Pfarrhaus', La + 'Parsonage', [('Brick_HardFired', pa), ('Glass_Clear', pg), ('Aluminium_Cornice_Riveted', pr)])
    # monolith: St. John of Capistrano (Prof. J. Henselmann) - granite on a chariot, transparent cross
    mo = Mesh(); wh = Mesh(smooth_deg=40); cr = Mesh()
    mx, my = -21.0, 30.0
    add_box(mo, mx - 0.9, mx + 0.9, my - 0.55, my + 0.55, 0.0, 0.45)
    add_box(mo, mx - 0.40, mx + 0.40, my - 0.32, my + 0.32, 0.45, 3.40)
    for dx in (-0.6, 0.6):
        wm = Mesh(smooth_deg=40)
        add_cylinder(wm, 0, 0, 0.42, -0.06, 0.06, 24)
        M = xf_translate(mx + dx, my, 0.42) @ np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1.0]])
        wh.extend(apply_xf(wm, M))
    add_box(cr, mx - 0.04, mx + 0.04, my - 0.04, my + 0.04, 3.40, 4.40)
    add_box(cr, mx - 0.04, mx + 0.04, my - 0.32, my + 0.32, 4.02, 4.10)
    S.obj('Monolith_St_Johann_von_Capistran (J. Henselmann)', La + 'Monolith', [('Granite_Grey', mo), ('Granite_Grey', wh), ('Glass_Clear', cr)])
    # neighbouring houses to the east (context massing)
    nh_w = Mesh(); nh_r = Mesh()
    for (x, y) in ((48, -24), (50, 0), (47, 24)):
        add_box(nh_w, x - 5, x + 5, y - 6, y + 6, -0.05, 6.0)
        a = (x - 5.5, y - 6.5, 6.0); b = (x + 5.5, y - 6.5, 6.0); c = (x + 5.5, y, 9.6); d = (x - 5.5, y, 9.6)
        nh_r.quad(a, b, c, d, (a[0], 0), (b[0], 0), (c[0], 7.4), (d[0], 7.4))
        a2 = (x + 5.5, y + 6.5, 6.0); b2 = (x - 5.5, y + 6.5, 6.0)
        nh_r.quad(a2, b2, d, c, (a2[0], 0), (b2[0], 0), (d[0], 7.4), (c[0], 7.4))
        nh_w.tri((x - 5, y + 6, 6.0), (x - 5, y, 9.55), (x - 5, y - 6, 6.0), (y + 6, 6), (y, 9.5), (y - 6, 6))
        nh_w.tri((x + 5, y - 6, 6.0), (x + 5, y, 9.55), (x + 5, y + 6, 6.0), (y - 6, 6), (y, 9.5), (y + 6, 6))
    S.obj('Neighbour_Houses_Context', La + 'Context', [('Render_White', nh_w), ('Roof_Tile_Dark', nh_r)])


# ------------------------------------------------------------- 11 reference curves, labels, views
def build_reference(S):
    L = '00_Reference::'
    S.curves += [
        dict(layer=L + 'Plan Geometry', name='Outer circle D32.00 (centre O)', kind='circle', c=(0, 0, 0), r=R_OUT),
        dict(layer=L + 'Plan Geometry', name='Inner circle D28.00 (centre C, 2.00 m west)', kind='circle', c=(C[0], C[1], 0), r=R_IN),
        dict(layer=L + 'Plan Geometry', name='Roof edge D41.00', kind='circle', c=(0, 0, 0), r=R_ROOF),
        dict(layer=L + 'Plan Geometry', name='Rod circle 22 x 5.35 m', kind='circle', c=(0, 0, 0), r=R_RODS),
        dict(layer=L + 'Plan Geometry', name='Dome D5.00', kind='circle', c=(0, 0, 0), r=R_DOME),
        dict(layer=L + 'Plan Geometry', name='Axis W-E', kind='line', a=(-35, 0, 0), b=(35, 0, 0)),
        dict(layer=L + 'Plan Geometry', name='Axis N-S', kind='line', a=(0, -25, 0), b=(0, 25, 0)),
    ]
    S.dots += [
        (L + 'Labels', '主入口 Glasportal (W)', (X_PORTAL - 1.5, 0, 1.5)),
        (L + 'Labels', '主祭壇 Opferaltar (Nagelfluh 2x2)', (1.4, 0, 1.8)),
        (L + 'Labels', '聖體龕 Tabernakel (F. Rickert)', (7.8, 0, 3.4)),
        (L + 'Labels', '洗禮堂 Taufkapelle', (13.95, 0, 1.6)),
        (L + 'Labels', '唱詩台 Sängerempore +3.00', (14.0, 0, 4.0)),
        (L + 'Labels', '管風琴 Orgel +6.00', (14.2, 0, 8.0)),
        (L + 'Labels', '迴廊 Galerie +10.25', (7.5, 13.2, 11.0)),
        (L + 'Labels', '穹頂 Plexiglaskuppel D5.00 +16.00', (0, 0, 16.3)),
        (L + 'Labels', '鐘牆 Glockenwand 13.5 m', (-29.2, -24.8, 14.0)),
        (L + 'Labels', '堂區大廳 Pfarrsaal', (-38, 22, 6.8)),
        (L + 'Labels', '神父宅 Pfarrhaus', (-57, -44, 4.3)),
        (L + 'Labels', '22 根拉桿 Pendelstützen + 地下配重', (R_RODS, 0, 6.0)),
    ]
    S.views += [
        dict(name='01 Exterior - South-West approach', cam=(-24, -44, 1.65), tgt=(0, 0, 7.0), lens=28),
        dict(name='02 Exterior - East (Steingitter band)', cam=(44, 12, 1.65), tgt=(0, 0, 6.5), lens=30),
        dict(name='03 Exterior - Glass portal & forecourt', cam=(-27.5, -9, 1.65), tgt=(-13, 1, 5.5), lens=24),
        dict(name='04 Exterior - Under the roof (circuitus)', cam=(-3.5, -19.4, 1.65), tgt=(12, -12.5, 5.5), lens=20),
        dict(name='05 Aerial - North-West', cam=(-60, 55, 45), tgt=(0, 0, 6), lens=35),
        dict(name='06 Interior - Nave to altar (east)', cam=(-11.6, 0, 1.6), tgt=(6, 0, 5.2), lens=17),
        dict(name='07 Interior - Altar to Oberberger window (west)', cam=(5.2, -2.9, 1.7), tgt=(-13, 0.5, 6.4), lens=17),
        dict(name='08 Interior - Looking up to the lantern', cam=(-3.0, -1.0, 1.6), tgt=(0, 0, 16), lens=14),
        dict(name='09 Interior - Gallery +10.25 (light slot)', cam=(7.6, -13.25, 11.9), tgt=(14.6, -1.5, 11.6), lens=16),
        dict(name='10 Interior - Baptistery through the grille', cam=(9.7, -1.7, 1.65), tgt=(13.9, 0, 1.1), lens=24),
    ]


def build_scene(tiles):
    S = Scene()
    define_materials(S, tiles)
    build_masonry(S)
    build_roof(S)
    build_ceiling(S)
    build_portal(S)
    build_floors(S)
    build_liturgy(S)
    build_pews(S)
    build_lighting(S)
    build_rods(S)
    build_site(S)
    build_reference(S)
    return S

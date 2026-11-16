"""Write the 1:1 (mm) layered DXF plan + an A3 1:100 sheet frame, from model.py."""
from __future__ import annotations

import math
import sys

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

import model as M
from geom import Mesh, Prism, rect

TSTYLE = "TW"
LAYERS = {
    "A-WALL": (7, "牆體 (剖切)"), "A-WALL-LOW": (8, "矮牆/欄牆"), "A-COLS": (7, "結構柱"),
    "A-DOOR": (3, "門/門弧"), "A-GLAZ": (4, "窗/玻璃"), "A-FURN": (8, "活動傢俱"),
    "A-CASE": (5, "固定櫃/系統櫃"), "A-PFIX": (6, "衛浴設備"), "A-KITC": (6, "廚具"),
    "A-EQPT": (30, "設備/管道間"), "A-PLNT": (82, "植栽"), "A-RAIL": (140, "欄杆"),
    "A-FLOR": (9, "地坪/鋪面"), "A-ANNO-TEXT": (7, "空間名稱/面積"), "A-ANNO-DIMS": (2, "尺寸標註"),
    "A-ANNO-SYMB": (7, "符號/指北"), "A-SHEET": (7, "圖框/圖說"),
    "A-SECT": (7, "剖面切線/填色"), "A-SECT-LEVL": (1, "剖面高程線"),
}
TAG2LAYER = {"FURN": "A-FURN", "CASE": "A-CASE", "PFIX": "A-PFIX", "KITC": "A-KITC", "EQPT": "A-EQPT",
             "PLNT": "A-PLNT", "GLAZ": "A-GLAZ", "DOOR": "A-DOOR"}

ROOM_DIMS = {
    "主臥室": "4,525 × 4,275", "更衣室": "3,350 × 1,750", "主衛浴": "3,350 × 2,675", "工作陽台": "2,750 × 1,500",
    "廚房": "3,000 × 3,250", "客衛": "1,300 × 2,450", "玄關": "2,550 × 3,050", "客廳": "5,000 × 5,300",
    "餐廳": "3,500 × 5,300", "次臥一": "4,450 × 3,325", "衛浴(次臥一)": "3,250 × 1,700", "次臥二": "4,450 × 3,225",
    "衛浴(次臥二)": "1,550 × 2,050", "景觀陽台": "9,600 × 1,800", "過道": "1,050 × 2,350",
}


def setup(doc):
    doc.units = units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2
    doc.header["$LUPREC"] = 0
    st = doc.styles.new(TSTYLE, dxfattribs={"font": "msjh.ttc"})
    st.set_extended_font_data(family="Microsoft JhengHei")
    for name, (color, desc) in LAYERS.items():
        lay = doc.layers.add(name, color=color)
        lay.description = desc
    doc.layers.get("A-WALL").dxf.lineweight = 50
    doc.layers.get("A-COLS").dxf.lineweight = 50
    doc.layers.get("A-SHEET").dxf.lineweight = 35
    ds = doc.dimstyles.new("TW100")
    ds.dxf.dimtxt = 200
    ds.dxf.dimasz = 120
    ds.dxf.dimblk = "ARCHTICK"
    ds.dxf.dimexe = 120
    ds.dxf.dimexo = 150
    ds.dxf.dimgap = 60
    ds.dxf.dimtad = 1
    ds.dxf.dimdec = 0
    ds.dxf.dimtxsty = TSTYLE
    ds.dxf.dimclrd = 2
    ds.dxf.dimclre = 2
    ds.dxf.dimclrt = 7
    ds.dxf.dimtih = 0
    ds.dxf.dimtoh = 0
    ds.dxf.dimtmove = 0
    ds.dxf.dimdsep = ord(".")


def poly_paths(g):
    polys = [g] if isinstance(g, Polygon) else list(getattr(g, "geoms", []))
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        yield p, [list(p.exterior.coords)] + [list(r.coords) for r in p.interiors]


def add_poly(msp, g, layer, hatch_rgb=None, hatch_aci=None, outline=True, lineweight=None):
    for p, rings in poly_paths(g):
        if outline:
            for r in rings:
                e = msp.add_lwpolyline([(x, y) for x, y in r[:-1]], close=True, dxfattribs={"layer": layer})
                if lineweight:
                    e.dxf.lineweight = lineweight
        if hatch_rgb or hatch_aci is not None:
            h = msp.add_hatch(color=hatch_aci if hatch_aci is not None else 7, dxfattribs={"layer": layer})
            if hatch_rgb:
                h.rgb = hatch_rgb
            for r in rings:
                h.paths.add_polyline_path([(x, y) for x, y in r[:-1]], is_closed=True)


def text(msp, s, x, y, h, layer="A-ANNO-TEXT", align=TextEntityAlignment.MIDDLE_CENTER, rot=0):
    t = msp.add_text(s, height=h, rotation=rot, dxfattribs={"style": TSTYLE, "layer": layer})
    t.set_placement((x, y), align=align)
    return t


# ------------------------------------------------------------------------------------------ walls + columns
def draw_structure(msp):
    cols = unary_union(list(M.COLUMNS.values()))
    cut, low, lvr = [], [], []
    for wid, (x0, y0, x1, y1, kind, h) in M.WALLS.items():
        r = rect(x0, y0, x1, y1)
        for o in M.openings_of(wid):
            r = r.difference(M.opening_rect(o))
        (cut if kind in ("ext", "int") else low if kind == "low" else lvr).append(r)
    walls = unary_union(cut).difference(cols)
    add_poly(msp, walls, "A-WALL", hatch_rgb=(70, 70, 70))
    add_poly(msp, cols, "A-COLS", hatch_rgb=(35, 35, 35))
    add_poly(msp, unary_union(low), "A-WALL-LOW")
    for g in lvr:
        add_poly(msp, g, "A-EQPT")
        x0, y0, x1, y1 = g.bounds
        x = x0 + 100
        while x < x1 - 50:
            msp.add_line((x, y0), (x + 60, y1), dxfattribs={"layer": "A-EQPT"})
            x += 120
    for name, g in M.SHAFTS.items():
        add_poly(msp, g, "A-EQPT")
        x0, y0, x1, y1 = g.bounds
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": "A-EQPT"})
        msp.add_line((x0, y1), (x1, y0), dxfattribs={"layer": "A-EQPT"})


# ------------------------------------------------------------------------------------------ openings
def wall_frame(o):
    """Return (axis, face_lo, face_hi) of the host wall."""
    x0, y0, x1, y1, *_ = M.WALLS[o["wall"]]
    ax = M.wall_axis(o["wall"])
    return (ax, y0, y1) if ax == "x" else (ax, x0, x1)


def P(ax, s, t):
    """Map (along-wall s, across-wall t) to world XY."""
    return (s, t) if ax == "x" else (t, s)


def lrect(msp, ax, s0, s1, t0, t1, layer):
    pts = [P(ax, s0, t0), P(ax, s1, t0), P(ax, s1, t1), P(ax, s0, t1)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})


def line(msp, a, b, layer, **kw):
    msp.add_line(a, b, dxfattribs={"layer": layer, **kw})


def ang(ax, ds, dt):
    x, y = P(ax, ds, dt)
    return math.degrees(math.atan2(y, x)) % 360


def swing_leaf(msp, ax, hinge_s, face_t, toward_s, swing, width):
    """Leaf drawn open at 90°, plus quarter arc from closed to open position."""
    s_in = hinge_s if toward_s > 0 else hinge_s - M.FRAME
    lrect(msp, ax, s_in, s_in + M.FRAME, face_t, face_t + swing * width, "A-DOOR")
    c = P(ax, hinge_s, face_t)
    a_closed = ang(ax, toward_s, 0)
    a_open = ang(ax, 0, swing)
    a0, a1 = (a_closed, a_open) if (a_open - a_closed) % 360 == 90 else (a_open, a_closed)
    msp.add_arc(c, width, a0, a1, dxfattribs={"layer": "A-DOOR"})


def draw_openings(msp):
    for o in M.OPENINGS:
        ax, t0, t1 = wall_frame(o)
        s0, s1, k = o["s0"], o["s1"], o["kind"]
        tm = (t0 + t1) / 2
        if k == "window":
            line(msp, P(ax, s0, t0), P(ax, s1, t0), "A-GLAZ")
            line(msp, P(ax, s0, t1), P(ax, s1, t1), "A-GLAZ")
            n = o.get("panels", 1)
            for i in range(n):
                a = s0 + (s1 - s0) * i / n - (40 if i else 0)
                b = s0 + (s1 - s0) * (i + 1) / n + (40 if i < n - 1 else 0)
                off = (-25 if i % 2 == 0 else 25) if n > 1 else 0
                lrect(msp, ax, a, b, tm + off - 12, tm + off + 12, "A-GLAZ")
            continue
        if k == "open":
            for t in (t0, t1):
                line(msp, P(ax, s0, t), P(ax, s1, t), "A-DOOR", linetype="DASHED", ltscale=8)
            continue
        if k == "slide4":
            line(msp, P(ax, s0, t0), P(ax, s1, t0), "A-GLAZ")
            line(msp, P(ax, s0, t1), P(ax, s1, t1), "A-GLAZ")
            L = s1 - s0
            for i in range(4):
                a = s0 + L * i / 4 - (40 if i else 0)
                b = s0 + L * (i + 1) / 4 + (40 if i < 3 else 0)
                off = -35 if i in (0, 3) else 35
                lrect(msp, ax, a, b, tm + off - 20, tm + off + 20, "A-GLAZ")
            continue
        # framed doors: jambs
        lrect(msp, ax, s0, s0 + M.FRAME, t0, t1, "A-DOOR")
        lrect(msp, ax, s1 - M.FRAME, s1, t0, t1, "A-DOOR")
        swing = o.get("swing", 1)
        face = t1 if swing > 0 else t0
        clear = s1 - s0 - 2 * M.FRAME
        if k == "door":
            if o["hinge"] == "s0":
                swing_leaf(msp, ax, s0 + M.FRAME, face, +1, swing, clear)
            else:
                swing_leaf(msp, ax, s1 - M.FRAME, face, -1, swing, clear)
        elif k == "double":
            main = o["main"]
            swing_leaf(msp, ax, s0 + M.FRAME, face, +1, swing, main)
            swing_leaf(msp, ax, s1 - M.FRAME, face, -1, swing, clear - main)
        elif k == "slide":
            tt = face + swing * 10
            lrect(msp, ax, s0 - 60, s1 + 60, tt, tt + swing * 40, "A-DOOR")
            mid = P(ax, (s0 + s1) / 2, tt + swing * 160)
            msp.add_lwpolyline([P(ax, s0 + 150, tt + swing * 160), P(ax, s1 - 150, tt + swing * 160)],
                               dxfattribs={"layer": "A-DOOR"})
            line(msp, P(ax, s1 - 150, tt + swing * 160), P(ax, s1 - 250, tt + swing * 210), "A-DOOR")
            line(msp, P(ax, s1 - 150, tt + swing * 160), P(ax, s1 - 250, tt + swing * 110), "A-DOOR")


# ------------------------------------------------------------------------------------------ furniture & casework
def draw_prims(msp, prims, layer):
    for p in prims:
        if not p.plan:
            continue
        if isinstance(p, Mesh):
            if p.plan_circle:
                msp.add_circle(p.plan_circle[:2], p.plan_circle[2], dxfattribs={"layer": layer})
            continue
        if not p.is_vertical_extrusion():
            # horizontal prisms (e.g. washer door): project their bounding footprint
            continue
        if p.circle:
            cx, cy = p.to_world2d(p.circle[0], p.circle[1])
            msp.add_circle((cx, cy), p.circle[2], dxfattribs={"layer": layer})
            continue
        add_poly(msp, p.footprint(), layer)


def draw_furniture(msp):
    for obj in M.furniture_objects():
        layer = TAG2LAYER.get(obj["tag"], "A-FURN")
        draw_prims(msp, [p.transformed(obj["M"]) for p in obj["local"]], layer)
        for a, b in obj["local_lines"]:
            from geom import transform2d
            line(msp, transform2d(obj["M"], *a), transform2d(obj["M"], *b), layer)
    for obj in M.casework():
        layer = TAG2LAYER.get(obj["tag"], "A-CASE")
        draw_prims(msp, obj["prims"], layer)
        for a, b in obj["lines"]:
            line(msp, a, b, layer)


def draw_rails(msp):
    for path in M.RAILS:
        g = LineString(path).buffer(25, cap_style=2, join_style=2)
        add_poly(msp, g, "A-RAIL")


def draw_floors(msp):
    for name, poly, lp, mat, outdoor in M.ROOMS:
        if mat in ("floor_tile",):
            h = msp.add_hatch(color=9, dxfattribs={"layer": "A-FLOR"})
            h.set_pattern_fill("NET", scale=100, color=9)
            for p, rings in poly_paths(poly):
                for r in rings:
                    h.paths.add_polyline_path([(x, y) for x, y in r[:-1]], is_closed=True)
        elif outdoor:
            h = msp.add_hatch(color=9, dxfattribs={"layer": "A-FLOR"})
            h.set_pattern_fill("LINE", scale=40, color=9, angle=0 if name != "景觀陽台" else 90)
            for p, rings in poly_paths(poly):
                for r in rings:
                    h.paths.add_polyline_path([(x, y) for x, y in r[:-1]], is_closed=True)


def draw_labels(msp):
    for name, poly, (x, y), mat, outdoor in M.ROOMS:
        a = poly.area / 1e6
        if a < 9 or len(name) > 4:          # small rooms: compact two-line tag
            text(msp, name, x, y + 120, 150 if a < 2 else 170 if len(name) > 4 else 240)
            text(msp, f"{a:.1f} m²／{a / 3.30579:.1f} 坪", x, y - 130, 120)
            continue
        text(msp, name, x, y + 230, 300)
        text(msp, f"{a:.1f} m²／約 {a / 3.30579:.1f} 坪", x, y - 120, 165)
        if name in ROOM_DIMS:
            text(msp, ROOM_DIMS[name], x, y - 380, 150)


# ------------------------------------------------------------------------------------------ dimensions
def chain(msp, pts, axis, at, feat, style="TW100"):
    for a, b in zip(pts, pts[1:]):
        if axis == "x":
            d = msp.add_linear_dim(base=(a, at), p1=(a, feat), p2=(b, feat), angle=0, dimstyle=style,
                                   dxfattribs={"layer": "A-ANNO-DIMS"})
        else:
            d = msp.add_linear_dim(base=(at, a), p1=(feat, a), p2=(feat, b), angle=90, dimstyle=style,
                                   dxfattribs={"layer": "A-ANNO-DIMS"})
        d.render()


def draw_dims(msp):
    top = [0, 1200, 2050, 3850, 4700, 5850, 6200, 12800, 13150, 14300, 16400, 18200, 19400]
    bot = [0, 1200, 1900, 4650, 5000, 7200, 8200, 9400, 9950, 11500, 12650, 14300, 15550, 16000, 18000, 18350, 19400]
    left = [0, 1000, 1600, 2800, 3200, 4600, 6100, 7500, 9700, 10750, 11950, 12700]
    right = [0, 1600, 3400, 5300, 6200, 7500, 8050, 10750, 11950, 12700]
    chain(msp, top, "x", 13350, 12000)
    chain(msp, [0, 19400], "x", 14050, 13350)
    chain(msp, bot, "x", -900, -50)
    chain(msp, [0, 19400], "x", -1600, -900)
    chain(msp, left, "y", -900, -50)
    chain(msp, [0, 12700], "y", -1600, -900)
    chain(msp, right, "y", 20300, 19450)
    chain(msp, [0, 12700], "y", 21000, 20300)
    # key interior widths
    chain(msp, [600, 5125], "x", 10400, 10600)
    chain(msp, [5650, 10650, 14150], "x", 10400, 10600)


# ------------------------------------------------------------------------------------------ sheet
def draw_sheet(msp):
    L = "A-SHEET"
    fx0, fy0, fx1, fy1 = -3500, -9300, 38500, 20400          # A3 landscape @ 1:100
    msp.add_lwpolyline([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)], close=True, dxfattribs={"layer": L})
    msp.add_lwpolyline([(fx0 + 500, fy0 + 500), (fx1 - 500, fy0 + 500), (fx1 - 500, fy1 - 500), (fx0 + 500, fy1 - 500)],
                       close=True, dxfattribs={"layer": L, "lineweight": 50})
    text(msp, M.PROJECT, -2300, 17900, 650, L, TextEntityAlignment.LEFT)
    text(msp, "B戶 平面配置圖（CAD 重繪）  1:100 @A3  單位 mm", -2300, 16900, 380, L, TextEntityAlignment.LEFT)
    # north arrow (source arrow points to plan-up, i.e. +Y)
    cx, cy = 21600, 17300
    msp.add_circle((cx, cy), 700, dxfattribs={"layer": "A-ANNO-SYMB"})
    msp.add_lwpolyline([(cx, cy + 650), (cx + 280, cy - 450), (cx, cy - 200), (cx - 280, cy - 450)], close=True,
                       dxfattribs={"layer": "A-ANNO-SYMB"})
    text(msp, "N", cx, cy + 1050, 380, "A-ANNO-SYMB")

    # area schedule
    x0, y = 23500, 18300
    text(msp, "面積表（淨面積，量至牆內面）", x0, y, 360, L, TextEntityAlignment.LEFT)
    y -= 650
    text(msp, "空間", x0, y, 230, L, TextEntityAlignment.LEFT)
    text(msp, "m²", x0 + 7600, y, 230, L, TextEntityAlignment.RIGHT)
    text(msp, "坪", x0 + 10200, y, 230, L, TextEntityAlignment.RIGHT)
    text(msp, "淨寬 × 淨深", x0 + 14200, y, 230, L, TextEntityAlignment.RIGHT)
    msp.add_line((x0, y - 220), (x0 + 14300, y - 220), dxfattribs={"layer": L})
    tin = tout = 0.0
    for name, poly, lp, mat, outdoor in M.ROOMS:
        y -= 520
        a = poly.area / 1e6
        if outdoor:
            tout += a
        else:
            tin += a
        text(msp, name + ("（戶外）" if outdoor else ""), x0, y, 220, L, TextEntityAlignment.LEFT)
        text(msp, f"{a:.2f}", x0 + 7600, y, 220, L, TextEntityAlignment.RIGHT)
        text(msp, f"{a / 3.30579:.2f}", x0 + 10200, y, 220, L, TextEntityAlignment.RIGHT)
        text(msp, ROOM_DIMS.get(name, "—"), x0 + 14200, y, 200, L, TextEntityAlignment.RIGHT)
    msp.add_line((x0, y - 260), (x0 + 14300, y - 260), dxfattribs={"layer": L})
    y -= 620
    text(msp, f"室內淨面積合計 {tin:.2f} m²（{tin / 3.30579:.2f} 坪）", x0, y, 240, L, TextEntityAlignment.LEFT)
    y -= 450
    text(msp, f"戶外（陽台/平台）合計 {tout:.2f} m²（{tout / 3.30579:.2f} 坪）", x0, y, 240, L, TextEntityAlignment.LEFT)

    notes = [
        "圖說：",
        "1. 本圖依建商公開行銷平面圖逐像素量測重繪，標註尺寸（19,400 × 12,700 及左右側尺寸鏈）優先，其餘依圖面比例換算並取 50mm 模數。",
        "2. 原圖「主要空間尺度」表之主臥／次臥面寬（3,600～3,800）與總寬 19,400 及客餐廳 8,600 互相矛盾，本圖依圖面實際比例（約 4,450～4,525）。",
        "3. 樓高（本層 FL 至上層 FL）3,500：樓板 150＋地坪 80，版底淨高 3,270。外牆 300、內隔間 150；室內門高 2,100、大門 2,400、客廳落地門 2,700。",
        "4. 傢俱與衛浴設備採市售常規尺寸，依原圖位置與方向配置。原圖主衛浴未繪馬桶、衛浴(次臥二)未繪淋浴，本圖照原圖不自行增設。",
        "5. 非建商正式施工圖；實際尺寸、結構及配置依建照核准圖說及現場丈量為準。",
    ]
    yy = -3300
    for n in notes:
        text(msp, n, -2300, yy, 230 if n != "圖說：" else 280, L, TextEntityAlignment.LEFT)
        yy -= 480

    # title block
    tx0, ty0, tx1, ty1 = 23500, -8800, 38000, -3600
    msp.add_lwpolyline([(tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1)], close=True, dxfattribs={"layer": L})
    rows = [("工程名稱", "德鑫泰極 住宅大樓 B戶（重繪）"), ("圖名", "B戶 標準層平面配置圖"),
            ("比例 / 單位", "1:100 @A3 ／ mm"), ("圖層", "A-WALL / A-COLS / A-DOOR / A-GLAZ / A-FURN …"),
            ("日期", "2026-11-16")]
    rh = (ty1 - ty0) / len(rows)
    for i, (k, v) in enumerate(rows):
        yy = ty1 - rh * (i + 0.5)
        if i:
            msp.add_line((tx0, ty1 - rh * i), (tx1, ty1 - rh * i), dxfattribs={"layer": L})
        text(msp, k, tx0 + 250, yy, 230, L, TextEntityAlignment.MIDDLE_LEFT)
        text(msp, v, tx0 + 3300, yy, 260, L, TextEntityAlignment.MIDDLE_LEFT)
    msp.add_line((tx0 + 3000, ty0), (tx0 + 3000, ty1), dxfattribs={"layer": L})


# ------------------------------------------------------------------------------------------ sections
SECTIONS = [  # name, cut axis, position, sheet origin (ox, oy), title
    ("A-A", "y", 8620, (0, -17800), "A-A 剖面（Y = 8,620，向北看）"),
    ("C-C", "y", 2650, (0, -25300), "C-C 剖面（Y = 2,650，向北看）"),
    ("B-B", "x", 12300, (0, -32800), "B-B 剖面（X = 12,300，向西看）"),
]


def draw_section_marks(msp):
    L = "A-ANNO-SYMB"
    for name, axis, at, _, _ in SECTIONS:
        tag = name[0]
        if axis == "y":
            for x0, x1, tx in ((-2600, -1900, -2250), (21300, 22000, 21650)):
                e = msp.add_lwpolyline([(x0, at), (x1, at)], dxfattribs={"layer": L})
                e.dxf.const_width = 60
                msp.add_lwpolyline([(tx - 180, at + 120), (tx + 180, at + 120), (tx, at + 520)], close=True,
                                   dxfattribs={"layer": L})
                text(msp, tag, tx, at - 330, 330, L)
        else:
            for y0, y1, ty in ((-2600, -1900, -2250), (14650, 15350, 15000)):
                e = msp.add_lwpolyline([(at, y0), (at, y1)], dxfattribs={"layer": L})
                e.dxf.const_width = 60
                msp.add_lwpolyline([(at - 120, ty - 180), (at - 120, ty + 180), (at - 520, ty)], close=True,
                                   dxfattribs={"layer": L})
                text(msp, tag, at + 330, ty, 330, L)


def draw_sections(msp):
    import numpy as np
    import trimesh
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge, polygonize

    import export_3d as E
    from geom import triangles

    L = "A-SHEET"
    fx0, fy0, fx1, fy1 = -3500, -40500, 38500, -10800     # second A3 sheet @ 1:100
    msp.add_lwpolyline([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)], close=True, dxfattribs={"layer": L})
    msp.add_lwpolyline([(fx0 + 500, fy0 + 500), (fx1 - 500, fy0 + 500), (fx1 - 500, fy1 - 500), (fx0 + 500, fy1 - 500)],
                       close=True, dxfattribs={"layer": L, "lineweight": 50})
    text(msp, "B戶 剖面圖（樓高 3,500）  1:100 @A3  單位 mm", -2300, -12300, 450, L, TextEntityAlignment.LEFT)

    objs = E.scene_objects(with_ceiling=True)
    meshes = []
    for obj in objs:
        parts = [triangles(p) for p in obj["prims"]]
        V = np.vstack([v for v, _ in parts])
        offs = np.cumsum([0] + [len(v) for v, _ in parts[:-1]])
        F = np.vstack([f + o for (_, f), o in zip(parts, offs)])
        meshes.append((obj, trimesh.Trimesh(V, F, process=False)))

    lay_of = {"FURN": "A-FURN", "CASE": "A-CASE", "PFIX": "A-PFIX", "KITC": "A-KITC", "EQPT": "A-EQPT",
              "PLNT": "A-PLNT", "GLAZ": "A-GLAZ", "DOOR": "A-DOOR", "RAIL": "A-RAIL"}
    for name, axis, at, (ox, oy), title in SECTIONS:
        normal = [0, 1, 0] if axis == "y" else [1, 0, 0]
        origin = [0, at, 0] if axis == "y" else [at, 0, 0]
        k = 0 if axis == "y" else 1
        width = 19400 if axis == "y" else 12700
        for obj, mesh in meshes:
            segs = trimesh.intersections.mesh_plane(mesh, normal, origin)
            if len(segs) == 0:
                continue
            q = np.round(np.asarray(segs)[:, :, [k, 2]] * 2) / 2          # snap to 0.5 mm so loops close
            q = q[np.any(q[:, 0] != q[:, 1], axis=1)]
            if len(q) == 0:
                continue
            lines = MultiLineString([((a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy)) for a, b in q])
            merged = linemerge(lines)
            structural = obj["tag"] in ("WALL", "COLS", "CLNG") or obj["name"] == "本層結構樓板"
            layer = "A-SECT" if structural or obj["tag"] == "FLOR" else lay_of.get(obj["tag"], "A-FURN")
            for ln in getattr(merged, "geoms", [merged]):
                msp.add_lwpolyline(list(ln.coords), dxfattribs={"layer": layer})
            if structural:
                polys = [p for p in polygonize(merged) if p.area > 100]
                if polys:
                    add_poly(msp, unary_union(polys), "A-SECT", hatch_rgb=(70, 70, 70) if obj["tag"] != "CLNG"
                             and obj["name"] != "本層結構樓板" else (125, 125, 125), outline=False)
        # levels
        for z, lab in ((0, "FL ±0"), (M.WALL_H, f"版底 +{M.WALL_H:,}"), (M.FLOOR_TO_FLOOR, f"上層 FL +{M.FLOOR_TO_FLOOR:,}")):
            msp.add_line((ox - 300, oy + z), (ox + width + 300, oy + z),
                         dxfattribs={"layer": "A-SECT-LEVL", "linetype": "DASHED", "ltscale": 6})
            dy = 170 if z == M.FLOOR_TO_FLOOR else -170 if z == M.WALL_H else 0
            text(msp, lab, ox + width + 450, oy + z + dy, 200, "A-SECT-LEVL", TextEntityAlignment.MIDDLE_LEFT)
        base = -(M.FINISH_T + M.SLAB_T)
        chain(msp, [oy + base, oy, oy + M.WALL_H, oy + M.FLOOR_TO_FLOOR], "y", ox - 900, ox - 100)
        chain(msp, [oy, oy + M.FLOOR_TO_FLOOR], "y", ox - 1700, ox - 900)
        text(msp, title + "  1:100（僅繪剖切線）", ox, oy - 1100, 330, L, TextEntityAlignment.LEFT)

    rows = [("上層 FL", f"+{M.FLOOR_TO_FLOOR:,}"), ("上層地坪 / 樓板", f"{M.FINISH_T} / {M.SLAB_T}"),
            ("版底（RC 淨高）", f"+{M.WALL_H:,}"), ("客廳落地拉門頂", "+2,700"), ("大門頂 / 窗頂", "+2,400"),
            ("室內門頂", "+2,100"), ("窗台", "+900 / 1,050 / 1,200 / 1,500"), ("欄杆頂（戶外地坪 -50 起算）", "+1,100"),
            ("本層 FL", "±0"), ("本層地坪 / 樓板底", f"-{M.FINISH_T} / -{M.FINISH_T + M.SLAB_T}")]
    x0, y = 23500, -13600
    text(msp, "樓高構成", x0, y, 360, L, TextEntityAlignment.LEFT)
    for k2, v2 in rows:
        y -= 560
        text(msp, k2, x0, y, 230, L, TextEntityAlignment.LEFT)
        text(msp, v2, x0 + 14000, y, 230, L, TextEntityAlignment.RIGHT)
    y -= 800
    for n in ["樓高依建築技術規則「樓層高度」定義：", "自室內地板面至其直上層地板面之高度。",
              "若另作天花吊頂，室內淨高 = 版底 - 吊頂深度", "（例：吊頂 300 → 淨高約 2,970）。"]:
        text(msp, n, x0, y, 220, L, TextEntityAlignment.LEFT)
        y -= 420


def build(path):
    doc = ezdxf.new("R2013", setup=True)
    setup(doc)
    msp = doc.modelspace()
    draw_floors(msp)
    draw_structure(msp)
    draw_openings(msp)
    draw_rails(msp)
    draw_furniture(msp)
    draw_labels(msp)
    draw_dims(msp)
    draw_section_marks(msp)
    draw_sheet(msp)
    draw_sections(msp)
    doc.saveas(path)
    return doc


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "../output/DexinTaiji_B_plan.dxf")

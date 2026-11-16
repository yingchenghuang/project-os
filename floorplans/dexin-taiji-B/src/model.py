"""德鑫泰極 B戶 標準層 — single source of truth for the CAD plan and the 3D model.

Coordinates in millimetres. Origin = south-west corner of the unit envelope.
X = east, Y = north, Z = up (Z = 0 is finished floor level).

How the numbers were derived (see README for the full audit):
  * Overall envelope 19,400 x 12,700 and the vertical dimension chain
    (1,800 / 4,500 / 3,300 / 3,100 left, 1,800 / 5,400 / 2,300 / 3,200 right) are honoured.
  * The source drawing was traced at pixel level and converted with
      X = (px - 124) * 19.556        (east-west)
      Y = (852 - py) * 20.902        (north-south, main body)
      Y = 10900 + (330.5 - py) * 19.149   (balcony band)
    then snapped to a 50 mm module.
  * Furniture uses real catalogue sizes placed at the traced position and orientation.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from geom import (X, Y, Z, Prism, box, circle_poly, cyl, cyl_axis, ellipse, elevation_prism, rect, ring, sphere,
                  stadium, tmat, xyprism)

PROJECT = "德鑫泰極 B戶 標準層 (5F–13F)"
FLOOR_TO_FLOOR = 3500  # 樓高：本層 FL 至上層 FL（建築技術規則「樓層高度」定義）
SLAB_T = 150           # RC slab
FINISH_T = 80          # screed + floor finish
WALL_H = FLOOR_TO_FLOOR - FINISH_T - SLAB_T   # 3,270 = finished floor to slab soffit (clear height)
WALL_BASE = -FINISH_T  # walls start below finish so floors tuck under them
EXT_T = 300
INT_T = 150
FRAME = 40             # door frame / jamb width

# --------------------------------------------------------------------------------------------- walls
# id: (x0, y0, x1, y1, kind, height)
WALLS = {
    # exterior north
    "EN1": (1200, 10750, 4700, 11050, "ext", WALL_H),
    "EN2": (5850, 10750, 13150, 11050, "ext", WALL_H),
    "EN3": (14300, 10750, 18200, 11050, "ext", WALL_H),
    # exterior west / east
    "EW1": (300, 1000, 600, 10750, "ext", WALL_H),
    "EE1": (18750, 3400, 19050, 10750, "ext", WALL_H),
    # exterior south (ragged façade)
    "ESK": (4800, 100, 8200, 400, "ext", WALL_H),         # kitchen south
    "EKW": (4650, 100, 4800, 2100, "ext", WALL_H),        # kitchen / work-balcony wall
    "ESE": (9400, 450, 12650, 750, "ext", WALL_H),        # entry wall
    "ESB": (15550, 1300, 18350, 1600, "ext", WALL_H),     # bedroom-2 south
    "H14": (600, 1600, 3700, 1750, "ext", WALL_H),        # master bath south (faces service yard)
    "LOW": (1900, 100, 2000, 1600, "low", 1100),          # parapet between AC ledge and work balcony
    "LVR": (14300, 650, 15400, 750, "louver", 2400),      # AC niche louvre
    # interior
    "I01": (5125, 5450, 5275, 10750, "int", WALL_H),      # master bedroom | living
    "I02": (4100, 5300, 5275, 5450, "int", WALL_H),       # master bedroom door wall
    "I03": (600, 6325, 3950, 6475, "int", WALL_H),        # master bedroom | walk-in closet
    "I04": (3950, 2250, 4100, 6475, "int", WALL_H),       # closet+bath | corridor/kitchen
    "I05": (600, 4425, 3950, 4575, "int", WALL_H),        # closet | master bath
    "I06": (3550, 1750, 3700, 2100, "int", WALL_H),
    "I07": (3550, 2100, 4800, 2250, "int", WALL_H),
    "I08": (4100, 3650, 9400, 3800, "int", WALL_H),       # kitchen + guest bath north
    "I10": (7800, 400, 7950, 3650, "int", WALL_H),        # kitchen | guest bath
    "I11": (9250, 1200, 9400, 3650, "int", WALL_H),       # guest bath | entry
    "I12": (12450, 750, 12600, 3100, "int", WALL_H),      # shoe cabinet | bath 2
    "I13": (12450, 3100, 14300, 3250, "int", WALL_H),     # bath 2 north
    "I14": (14150, 1050, 14300, 4500, "int", WALL_H),     # bath 2 | bedroom 2
    "I15": (14300, 1850, 15550, 2000, "int", WALL_H),     # AC niche north
    "I16": (15400, 650, 15550, 1850, "int", WALL_H),      # AC niche east
    "I17": (14300, 4350, 15350, 4500, "int", WALL_H),     # bedroom 2 door wall
    "I18": (15350, 4350, 15500, 7425, "int", WALL_H),     # vestibule | bath 1
    "I19": (14300, 6850, 15350, 7000, "int", WALL_H),     # bedroom 1 door wall
    "I20": (14150, 5850, 14300, 10750, "int", WALL_H),    # dining | bedroom 1
    "I21": (15500, 7275, 18750, 7425, "int", WALL_H),     # bath 1 north
    "I22": (15500, 5425, 18750, 5575, "int", WALL_H),     # bath 1 south
}

COLUMNS = {
    "C1": rect(0, 10750, 1200, 11950),
    "C2": rect(4700, 10750, 5850, 11950),
    "C3": rect(13150, 10750, 14300, 11950),
    "C4": rect(18200, 10750, 19400, 11950),
    "C5": rect(0, 0, 1200, 1000),
    "C6": rect(8200, 200, 9400, 1200),
    "C7": Polygon([(12650, 0), (14300, 0), (14300, 1050), (13200, 1050), (13200, 750), (12650, 750)]),
    "C8": rect(18350, 0, 19400, 1600),
    "C9": rect(18750, 1600, 19250, 3400),
}

# pipe / service shafts drawn with an "X" in the source
SHAFTS = {
    "管道間-客衛": rect(7950, 400, 8200, 1950),
    "管道間-衛浴2": rect(12600, 750, 13200, 1050),
}

# --------------------------------------------------------------------------------------------- openings
# kind: window | door | double | slide | slide4 | open
# s0/s1 are absolute X (horizontal walls) or Y (vertical walls)
# swing: +1 opens toward +Y (horizontal wall) / +X (vertical wall); hinge: 's0' or 's1'
OPENINGS = [
    dict(id="D1", wall="ESE", s0=9950, s1=11500, kind="double", head=2400, swing=+1, main=1000, label="大門 子母門"),
    dict(id="D2", wall="I02", s0=4150, s1=5050, kind="door", head=2100, hinge="s1", swing=+1, label="主臥門"),
    dict(id="D3", wall="I03", s0=2700, s1=3400, kind="open", head=2100, label="更衣室開口"),
    dict(id="D4", wall="I05", s0=2250, s1=3000, kind="door", head=2100, hinge="s0", swing=-1, label="主衛浴門"),
    dict(id="D5", wall="I08", s0=5750, s1=6500, kind="door", head=2100, hinge="s0", swing=-1, label="廚房門"),
    dict(id="D6", wall="EKW", s0=1250, s1=2050, kind="door", head=2100, hinge="s1", swing=-1, glass=True, label="工作陽台門"),
    dict(id="D7", wall="I11", s0=2600, s1=3350, kind="door", head=2100, hinge="s1", swing=-1, label="客衛門"),
    dict(id="D8", wall="I14", s0=2350, s1=3050, kind="door", head=2100, hinge="s1", swing=-1, label="衛浴(次臥二)門"),
    dict(id="D9", wall="I17", s0=14350, s1=15250, kind="door", head=2100, hinge="s0", swing=-1, label="次臥二門"),
    dict(id="D10", wall="I19", s0=14350, s1=15200, kind="door", head=2100, hinge="s0", swing=+1, label="次臥一門"),
    dict(id="D11", wall="I21", s0=16150, s1=16950, kind="slide", head=2100, swing=-1, label="衛浴(次臥一)拉門"),
    dict(id="D12", wall="EN2", s0=6200, s1=12800, kind="slide4", head=2700, label="客廳落地拉門"),
    dict(id="W1", wall="EN1", s0=2050, s1=3850, kind="window", sill=900, head=2400, panels=2, label="主臥北窗"),
    dict(id="W2", wall="EN3", s0=16400, s1=18200, kind="window", sill=900, head=2400, panels=2, label="次臥一北窗"),
    dict(id="W3", wall="EW1", s0=7500, s1=9700, kind="window", sill=1200, head=2400, panels=2, label="主臥西窗"),
    dict(id="W4", wall="EW1", s0=4600, s1=6100, kind="window", sill=900, head=2400, panels=2, label="更衣室西窗"),
    dict(id="W5", wall="EW1", s0=2800, s1=3200, kind="window", sill=1500, head=2100, panels=1, label="主衛浴高窗"),
    dict(id="W6", wall="ESK", s0=5000, s1=7200, kind="window", sill=1050, head=2100, panels=2, label="廚房南窗"),
    dict(id="W7", wall="ESB", s0=16000, s1=18000, kind="window", sill=900, head=2400, panels=2, label="次臥二南窗"),
    dict(id="W8", wall="EE1", s0=7500, s1=8050, kind="window", sill=900, head=2400, panels=1, label="次臥一東窗"),
    dict(id="W9", wall="EE1", s0=5650, s1=6200, kind="window", sill=1500, head=2100, panels=1, label="衛浴(次臥一)高窗"),
    dict(id="W10", wall="EE1", s0=3400, s1=5300, kind="window", sill=1200, head=2400, panels=2, label="次臥二東窗"),
]


def wall_axis(wid):
    x0, y0, x1, y1, *_ = WALLS[wid]
    return "x" if (x1 - x0) >= (y1 - y0) else "y"


def wall_rect(wid):
    x0, y0, x1, y1, *_ = WALLS[wid]
    return rect(x0, y0, x1, y1)


def openings_of(wid):
    return [o for o in OPENINGS if o["wall"] == wid]


def opening_zrange(o):
    if o["kind"] == "window":
        return o["sill"], o["head"]
    return 0, o["head"]


def opening_rect(o):
    x0, y0, x1, y1, *_ = WALLS[o["wall"]]
    if wall_axis(o["wall"]) == "x":
        return rect(o["s0"], y0, o["s1"], y1)
    return rect(x0, o["s0"], x1, o["s1"])


# --------------------------------------------------------------------------------------------- rooms
def U(*polys):
    return unary_union(polys)


ROOMS = [
    # name, polygon, label point, floor material, outdoor?
    ("主臥室", U(rect(600, 6475, 5125, 10750), rect(4100, 5450, 5125, 6475)), (4000, 9300), "floor_wood", False),
    ("更衣室", rect(600, 4575, 3950, 6325), (2250, 5300), "floor_wood", False),
    ("主衛浴", U(rect(600, 2250, 3950, 4425), rect(600, 1750, 3550, 2250)), (2750, 3050), "floor_tile", False),
    ("工作陽台", U(rect(1900, 100, 4650, 1600), rect(3700, 1600, 4650, 2100)), (3000, 1250), "floor_outdoor", True),
    ("設備平台", U(rect(600, 1000, 1900, 1600), rect(1200, 100, 1900, 1000)), (1250, 1300), "floor_outdoor", True),
    ("廚房", U(rect(4800, 400, 7800, 3650), rect(4100, 2250, 4800, 3650)), (6000, 2250), "floor_tile", False),
    ("客衛", rect(7950, 1200, 9250, 3650), (8720, 2250), "floor_tile", False),
    ("玄關", rect(9400, 750, 12450, 3800), (10700, 2700), "floor_stone", False),
    ("客廳", U(rect(5275, 3800, 10650, 10750), rect(4100, 3800, 5275, 5300)), (7800, 6700), "floor_wood", False),
    ("餐廳", U(rect(10650, 3800, 14150, 10750), rect(12450, 3250, 14150, 3800)), (12350, 5600), "floor_wood", False),
    ("過道", U(rect(14150, 4500, 15350, 5850), rect(14300, 5850, 15350, 6850)), (14820, 5650), "floor_wood", False),
    ("次臥一", U(rect(14300, 7425, 18750, 10750), rect(14300, 7000, 15350, 7425)), (15700, 9350), "floor_wood", False),
    ("衛浴(次臥一)", rect(15500, 5575, 18750, 7275), (16750, 6750), "floor_tile", False),
    ("次臥二", U(rect(14300, 2000, 18750, 4350), rect(15550, 1600, 18750, 2000), rect(15500, 4350, 18750, 5425)),
     (15600, 3300), "floor_wood", False),
    ("衛浴(次臥二)", rect(12600, 1050, 14150, 3100), (13560, 2230), "floor_tile", False),
    ("冷氣機位", rect(14300, 750, 15400, 1850), (14850, 1550), "floor_outdoor", True),
]

# landscape balcony: straight edge at Y=12450 with an arc bulging to Y=12700 at the unit axis X=9500
BALC_AXIS = 9500
ARC_X0, ARC_X1, ARC_EDGE, ARC_PEAK = 5450, 13550, 12450, 12700


def arc_points(n=24):
    chord = ARC_X1 - ARC_X0
    sag = ARC_PEAK - ARC_EDGE
    R = (chord ** 2 / 4 + sag ** 2) / (2 * sag)
    cy = ARC_PEAK - R
    a0 = math.atan2(ARC_EDGE - cy, ARC_X0 - BALC_AXIS)
    a1 = math.atan2(ARC_EDGE - cy, ARC_X1 - BALC_AXIS)
    return [(BALC_AXIS + R * math.cos(a0 + (a1 - a0) * i / n), cy + R * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


BALCONY_EDGE = [(3950, 11050), (3950, 12450), (5450, 12450)] + arc_points()[1:-1] + [(13550, 12450), (15200, 12450), (15200, 11050)]
BALCONY = Polygon(BALCONY_EDGE)
ROOMS.append(("景觀陽台", BALCONY, (9500, 12150), "floor_deck", True))

RAILS = [
    BALCONY_EDGE,
    [(1200, 50), (4650, 50)],                 # service yard + AC ledge
]

PLANTERS = [rect(3950, 11050, 4700, 12450), rect(4700, 11950, 5450, 12450),
            rect(14300, 11050, 15200, 12450), rect(13550, 11950, 14300, 12450)]


# --------------------------------------------------------------------------------------------- furniture library
# Each builder returns (prims, lines2d) in LOCAL coords: origin = footprint centre, local +Y = back side.

def f_bed(W, L):
    hb = 90
    p = [
        box(-W / 2 + 60, -L / 2 + 60, 0, W / 2 - 60, L / 2 - hb - 60, 120, "metal_dark", plan=False),
        box(-W / 2, -L / 2, 120, W / 2, L / 2 - hb, 330, "wood_walnut"),
        box(-W / 2 + 25, -L / 2 + 25, 330, W / 2 - 25, L / 2 - hb - 10, 580, "linen_white", plan=False),
        box(-W / 2 + 10, -L / 2 + 10, 580, W / 2 - 10, L / 2 - hb - 560, 620, "linen_beige"),
        box(-W / 2 + 60, L / 2 - hb - 500, 580, -30, L / 2 - hb - 70, 700, "linen_white"),
        box(30, L / 2 - hb - 500, 580, W / 2 - 60, L / 2 - hb - 70, 700, "linen_white"),
        box(-W / 2 - 20, L / 2 - hb, 0, W / 2 + 20, L / 2, 1150, "fabric_head"),
    ]
    return p, [((-W / 2 + 10, L / 2 - hb - 560), (W / 2 - 10, -L / 2 + 300))]


def f_nightstand(W=500, D=450, H=550):
    return [box(-W / 2, -D / 2, 0, W / 2, D / 2, H, "wood_walnut"),
            cyl(0, 0, 60, H, H + 280, "metal_dark", plan=False),
            cyl(0, 0, 170, H + 280, H + 520, "lamp_shade")], []


def f_bench(L, D, H=450):
    return [box(-L / 2, -D / 2, 0, L / 2, D / 2, H, "fabric_beige")], []


def f_sofa(L, D):
    arm, back = 200, 230
    p = [box(-L / 2 + 40, -D / 2 + 40, 0, L / 2 - 40, D / 2 - 40, 100, "metal_dark", plan=False),
         box(-L / 2, -D / 2, 100, L / 2, D / 2, 420, "fabric_sofa"),
         box(-L / 2, D / 2 - back, 420, L / 2, D / 2, 820, "fabric_sofa"),
         box(-L / 2, -D / 2, 420, -L / 2 + arm, D / 2 - back, 640, "fabric_sofa"),
         box(L / 2 - arm, -D / 2, 420, L / 2, D / 2 - back, 640, "fabric_sofa")]
    seat_w = (L - 2 * arm) / 3
    for i in range(3):
        x0 = -L / 2 + arm + i * seat_w
        p.append(box(x0 + 8, -D / 2 + 20, 420, x0 + seat_w - 8, D / 2 - back, 540, "fabric_light"))
        p.append(box(x0 + 8, D / 2 - back - 170, 540, x0 + seat_w - 8, D / 2 - back, 800, "fabric_light", plan=False))
    p.append(box(-L / 2 + arm + 40, D / 2 - back - 330, 540, -L / 2 + arm + 440, D / 2 - back - 170, 900, "fabric_beige"))
    p.append(box(L / 2 - arm - 440, D / 2 - back - 330, 540, L / 2 - arm - 40, D / 2 - back - 170, 900, "fabric_beige"))
    return p, []


def f_armchair(W=850, D=850):
    arm, back = 160, 200
    return [box(-W / 2 + 40, -D / 2 + 40, 0, W / 2 - 40, D / 2 - 40, 100, "metal_dark", plan=False),
            box(-W / 2, -D / 2, 100, W / 2, D / 2, 400, "fabric_beige"),
            box(-W / 2, D / 2 - back, 400, W / 2, D / 2, 780, "fabric_beige"),
            box(-W / 2, -D / 2, 400, -W / 2 + arm, D / 2 - back, 600, "fabric_beige"),
            box(W / 2 - arm, -D / 2, 400, W / 2, D / 2 - back, 600, "fabric_beige"),
            box(-W / 2 + arm + 10, -D / 2 + 20, 400, W / 2 - arm - 10, D / 2 - back, 500, "fabric_light")], []


def f_coffee_table(W, L, H=400):
    return [box(-W / 2, -L / 2, H - 40, W / 2, L / 2, H, "stone_marble"),
            box(-W / 2 + 80, -L / 2 + 80, 0, W / 2 - 80, L / 2 - 80, H - 40, "metal_dark", plan=False)], []


def f_side_table(r=320, H=550):
    return [cyl(0, 0, r, H - 30, H, "wood_oak"), cyl(0, 0, 35, 20, H - 30, "metal_dark", plan=False),
            cyl(0, 0, r * 0.6, 0, 20, "metal_dark", plan=False),
            cyl(0, 0, 70, H, H + 300, "metal_dark", plan=False), cyl(0, 0, 200, H + 300, H + 560, "lamp_shade")], \
        [((-r, 0), (r, 0)), ((0, -r), (0, r))]


def f_ottoman(L, W, H=420):
    return [xyprism(stadium(0, 0, L, W, "x"), 0, H, "fabric_beige")], [((0, -W / 2), (0, W / 2))]


def f_rug(W, L):
    return [box(-W / 2, -L / 2, 0, W / 2, L / 2, 10, "rug")], []


def f_dining_table(W, L, H=750):
    p = [box(-W / 2, -L / 2, H - 40, W / 2, L / 2, H, "wood_oak")]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (W / 2 - 100), sy * (L / 2 - 120)
            p.append(box(cx - 40, cy - 40, 0, cx + 40, cy + 40, H - 40, "wood_oak", plan=False))
    return p, []


def f_chair(W=480, D=520):
    p = [box(-W / 2, -D / 2, 430, W / 2, D / 2 - 40, 480, "fabric_chair"),
         box(-W / 2, D / 2 - 60, 430, W / 2, D / 2, 880, "wood_oak")]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * (W / 2 - 30), sy * (D / 2 - 35)
            p.append(box(cx - 20, cy - 20, 0, cx + 20, cy + 20, 430, "wood_oak", plan=False))
    return p, []


def f_tv_console(L, D, H=450, tv_w=1450, tv_h=840, tv_z=950):
    return [box(-L / 2, -D / 2, 120, L / 2, D / 2, H, "wood_walnut"),
            box(-L / 2 + 50, -D / 2 + 50, 0, L / 2 - 50, D / 2 - 30, 120, "metal_dark", plan=False),
            box(-tv_w / 2, D / 2 - 50, tv_z, tv_w / 2, D / 2 - 10, tv_z + tv_h, "tv_black")], []


def f_wardrobe(L, D, H=2400):
    return [box(-L / 2, -D / 2, 0, L / 2, D / 2, H, "wood_white")], \
        [((-L / 2, -D / 2 + 30), (L / 2, -D / 2 + 30)), ((-L / 2 + 40, 0), (L / 2 - 40, 0))] + \
        [((x, -D / 2 + 90), (x + 60, D / 2 - 90)) for x in _ticks(L)]


def _ticks(L, step=150):
    n = int((L - 200) // step)
    return [-L / 2 + 100 + i * step for i in range(n)]


def f_open_closet(L, D, H=2200):
    """Walk-in closet bay: side panels, shelf, base, hanging rod (see-through in 3D)."""
    t = 25
    rod = cyl_axis((-L / 2 + t, 0, H - 300), (L - 2 * t, 0, 0), 15, "metal_dark", plan=False)
    return [box(-L / 2, -D / 2, 0, -L / 2 + t, D / 2, H, "wood_oak"),
            box(L / 2 - t, -D / 2, 0, L / 2, D / 2, H, "wood_oak"),
            box(-L / 2 + t, -D / 2, H - 25, L / 2 - t, D / 2, H, "wood_oak", plan=False),
            box(-L / 2 + t, -D / 2, 0, L / 2 - t, D / 2, 350, "wood_oak", plan=False),
            box(-L / 2 + t, D / 2 - 20, 350, L / 2 - t, D / 2, H - 25, "wood_oak", plan=False),
            rod], \
        [((-L / 2, -D / 2), (L / 2, -D / 2)), ((-L / 2, D / 2), (L / 2, D / 2)), ((-L / 2 + t, 0), (L / 2 - t, 0))] + \
        [((x, -D / 2 + 60), (x, D / 2 - 60)) for x in _ticks(L, 110)]


def f_desk(L=1200, D=600, H=750):
    return [box(-L / 2, -D / 2, H - 30, L / 2, D / 2, H, "wood_oak"),
            box(-L / 2, -D / 2 + 50, 0, -L / 2 + 30, D / 2, H - 30, "wood_oak", plan=False),
            box(L / 2 - 30, -D / 2 + 50, 0, L / 2, D / 2, H - 30, "wood_oak", plan=False)], []


def f_toilet():
    bowl = ellipse(0, -60, 190, 250)
    return [box(-120, -120, 0, 120, 250, 380, "porcelain", plan=False),
            xyprism(ring(bowl, 35), 380, 420, "porcelain"),
            xyprism(bowl.buffer(-35), 300, 380, "water", plan=False),
            box(-210, 190, 380, 210, 350, 780, "porcelain")], []


def f_vanity(L, D=550, basins=(0.0,), H=850):
    p = [box(-L / 2, -D / 2, 250, L / 2, D / 2, H - 30, "wood_oak"),
         box(-L / 2, -D / 2, H - 30, L / 2, D / 2, H, "stone_quartz"),
         box(-L / 2, D / 2 - 15, 1150, L / 2, D / 2, 2050, "mirror", plan=False)]
    for bx in basins:
        ov = ellipse(bx, -20, 220, 170)
        p += [xyprism(ring(ov, 12), H, H + 140, "porcelain"), xyprism(ov.buffer(-12), H, H + 15, "porcelain", plan=False),
              cyl(bx, D / 2 - 70, 18, H, H + 300, "steel", plan=False)]
    return p, []


def f_bathtub(L=1500, W=780, H=600):
    st = stadium(0, 0, L, W, "y")
    return [xyprism(ring(st, 70), 0, H, "porcelain"), xyprism(st.buffer(-70), 0, 120, "porcelain", plan=False)], \
        [((0, L / 2 - 220), (0, L / 2 - 180))]


def f_washer():
    return [box(-300, -300, 0, 300, 300, 850, "appliance_white"),
            cyl_axis((0, -300, 420), (0, -20, 0), 180, "glass_black")], [((-220, -300), (220, -300))]


def f_laundry_sink(L=600, D=550):
    return [box(-L / 2, -D / 2, 0, L / 2, D / 2, 850, "steel"),
            box(-L / 2 + 60, -D / 2 + 60, 850, L / 2 - 60, D / 2 - 90, 852, "metal_dark"),
            cyl(0, D / 2 - 50, 18, 850, 1150, "steel", plan=False)], []


def f_ac_outdoor():
    return [box(-400, -150, 0, 400, 150, 650, "appliance_white"),
            cyl_axis((-150, -150, 325), (0, -10, 0), 200, "metal_dark")], []


def f_tree(pot_r=300, pot_h=500, crown_r=550, crown_z=1800, base_z=0):
    p = []
    if pot_h > 0:
        p += [cyl(0, 0, pot_r, base_z, base_z + pot_h, "terracotta"),
              cyl(0, 0, pot_r - 30, base_z + pot_h - 30, base_z + pot_h, "soil", plan=False)]
    p += [cyl(0, 0, 45, base_z + pot_h, base_z + crown_z - crown_r * 0.6, "trunk", plan=False),
          sphere(0, 0, base_z + crown_z, crown_r, "plant")]
    return p, []


def f_shrub(r=220, z=450):
    return [sphere(0, 0, z + r * 0.7, r, "plant")], []


def f_round_table(r=400, H=720):
    return [cyl(0, 0, r, H - 30, H, "wood_oak"), cyl(0, 0, 40, 20, H - 30, "metal_dark", plan=False),
            cyl(0, 0, 250, 0, 20, "metal_dark", plan=False)], []


FURN = {
    "bed": f_bed, "nightstand": f_nightstand, "bench": f_bench, "sofa": f_sofa, "armchair": f_armchair,
    "coffee_table": f_coffee_table, "side_table": f_side_table, "ottoman": f_ottoman, "rug": f_rug,
    "dining_table": f_dining_table, "chair": f_chair, "tv_console": f_tv_console, "wardrobe": f_wardrobe,
    "open_closet": f_open_closet, "desk": f_desk, "toilet": f_toilet, "vanity": f_vanity, "bathtub": f_bathtub,
    "washer": f_washer, "laundry_sink": f_laundry_sink, "ac_outdoor": f_ac_outdoor, "tree": f_tree, "shrub": f_shrub,
    "round_table": f_round_table,
}

# rot: degrees CCW. Local +Y (back) points to: 0 -> north, 90 -> west, 180 -> south, -90 -> east.
FURNITURE = [
    # ---- master bedroom
    ("主臥床 King", "FURN", "bed", dict(W=2000, L=2150), 1675, 8600, 90),
    ("主臥床頭櫃-北", "FURN", "nightstand", {}, 825, 9900, 90),
    ("主臥床頭櫃-南", "FURN", "nightstand", {}, 825, 7300, 90),
    ("主臥床尾椅", "FURN", "bench", dict(L=1700, D=450), 3025, 8600, 90),
    ("主臥地毯", "FURN", "rug", dict(W=1050, L=3400), 3450, 8600, 0),
    ("主臥電視櫃", "CASE", "tv_console", dict(L=2400, D=430), 4910, 8600, -90),
    # ---- walk-in closet
    ("更衣室吊櫃-北", "CASE", "open_closet", dict(L=1600, D=500), 1900, 6075, 0),
    ("更衣室吊櫃-西", "CASE", "open_closet", dict(L=1250, D=500), 850, 5200, 90),
    ("更衣室吊櫃-東", "CASE", "open_closet", dict(L=1750, D=550), 3675, 5450, -90),
    # ---- living
    ("客廳地毯", "FURN", "rug", dict(W=3550, L=4200), 8075, 7950, 0),
    ("客廳三人沙發", "FURN", "sofa", dict(L=3100, D=1000), 9640, 7910, -90),
    ("客廳單椅", "FURN", "armchair", {}, 8950, 5900, -135),
    ("客廳茶几", "FURN", "coffee_table", dict(W=900, L=1400), 7870, 8070, 0),
    ("客廳腳凳", "FURN", "ottoman", dict(L=1300, W=650), 7450, 9900, 0),
    ("客廳邊几", "FURN", "side_table", {}, 9550, 10000, 0),
    # ---- dining
    ("餐桌", "FURN", "dining_table", dict(W=1050, L=2250), 12320, 7960, 0),
    ("餐椅-西1", "FURN", "chair", {}, 11560, 8700, 90),
    ("餐椅-西2", "FURN", "chair", {}, 11560, 7960, 90),
    ("餐椅-西3", "FURN", "chair", {}, 11560, 7240, 90),
    ("餐椅-東1", "FURN", "chair", {}, 13090, 8700, -90),
    ("餐椅-東2", "FURN", "chair", {}, 13090, 7960, -90),
    ("餐椅-東3", "FURN", "chair", {}, 13090, 7240, -90),
    ("餐椅-北", "FURN", "chair", {}, 12320, 9370, 0),
    ("餐椅-南", "FURN", "chair", {}, 12320, 6560, 180),
    # ---- bedroom 1
    ("次臥一床 Queen+", "FURN", "bed", dict(W=1850, L=2100), 17700, 9000, -90),
    ("次臥一床頭櫃-北", "FURN", "nightstand", {}, 18500, 10200, -90),
    ("次臥一床頭櫃-南", "FURN", "nightstand", {}, 18500, 7800, -90),
    ("次臥一衣櫃", "CASE", "wardrobe", dict(L=1650, D=600), 14600, 8925, 90),
    ("次臥一書桌", "FURN", "desk", dict(L=1200, D=600), 14950, 10450, 0),
    ("次臥一書椅", "FURN", "chair", {}, 14950, 9950, 180),
    # ---- bedroom 2
    ("次臥二床 Queen+", "FURN", "bed", dict(W=1850, L=2100), 17700, 3135, -90),
    ("次臥二床頭櫃-北", "FURN", "nightstand", {}, 18500, 4330, -90),
    ("次臥二床頭櫃-南", "FURN", "nightstand", {}, 18500, 1940, -90),
    ("次臥二衣櫃", "CASE", "wardrobe", dict(L=2550, D=600), 16775, 5125, 0),
    ("次臥二收納櫃", "CASE", "wardrobe", dict(L=700, D=600), 18400, 5125, 0),
    # ---- bathrooms
    ("主衛浴獨立浴缸", "PFIX", "bathtub", {}, 1250, 2600, 0),
    ("主衛浴雙槽檯面", "PFIX", "vanity", dict(L=1650, basins=(-400.0, 400.0)), 2725, 2025, 180),
    ("客衛馬桶", "PFIX", "toilet", {}, 8300, 2990, 90),
    ("客衛洗手檯", "PFIX", "vanity", dict(L=750), 8625, 1475, 180),
    ("衛浴(次臥一)洗手檯", "PFIX", "vanity", dict(L=900), 15775, 6800, 90),
    ("衛浴(次臥一)馬桶", "PFIX", "toilet", {}, 16850, 5925, 180),
    ("衛浴(次臥二)洗手檯", "PFIX", "vanity", dict(L=650), 12875, 1775, 90),
    ("衛浴(次臥二)馬桶", "PFIX", "toilet", {}, 13740, 1400, 180),
    # ---- service
    ("洗衣機", "EQPT", "washer", {}, 3350, 400, 180),
    ("洗衣槽", "EQPT", "laundry_sink", {}, 4150, 375, 180),
    ("冷氣室外機", "EQPT", "ac_outdoor", {}, 14850, 1150, 180),
    # ---- landscape balcony
    ("陽台休閒椅", "FURN", "armchair", {}, 7200, 11730, 45),
    ("陽台圓桌", "FURN", "round_table", {}, 8300, 11680, 0),
    ("陽台喬木-西", "PLNT", "tree", {}, 5900, 12150, 0),
    ("陽台喬木-東", "PLNT", "tree", {}, 13150, 12150, 0),
    ("陽台喬木-東花台", "PLNT", "tree", dict(pot_h=0, crown_r=650, crown_z=1500, base_z=400), 14750, 11550, 0),
] + [(f"花台灌木-{i + 1}", "PLNT", "shrub", {}, x, y, 0) for i, (x, y) in enumerate(
    [(4150, 12200), (4450, 12200), (4900, 12200), (5250, 12200), (4300, 11500),
     (13750, 12200), (14050, 12200), (14550, 12200), (14950, 12200)])]


# --------------------------------------------------------------------------------------------- fixed casework (world coords)
def casework():
    """Built-ins that are not instanced furniture: kitchen, TV wall, cabinets, glass partitions."""
    objs = []

    def add(name, tag, prims, lines=()):
        objs.append(dict(name=name, tag=tag, prims=prims, lines=list(lines)))

    # kitchen — L-shaped run + fridge + pantry
    def counter(x0, y0, x1, y1, front):
        fx0, fy0, fx1, fy1 = x0, y0, x1, y1
        if front == "N":
            fy1 -= 60
        elif front == "W":
            fx0 += 60
        return [box(fx0, fy0, 0, fx1, fy1, 100, "metal_dark", plan=False),
                box(x0, y0, 100, x1, y1, 820, "wood_white", plan=False),
                box(x0, y0, 820, x1, y1, 850, "stone_quartz")]

    add("廚具-南側檯面", "KITC", counter(4800, 400, 7200, 1050, "N"))
    add("廚具-東側檯面", "KITC", counter(7200, 400, 7800, 2900, "W"))
    add("IH爐", "KITC", [box(5050, 520, 850, 5750, 980, 856, "glass_black"),
                         cyl(5230, 750, 110, 856, 857, "metal_dark"), cyl(5570, 750, 110, 856, 857, "metal_dark")])
    add("水槽", "KITC", [box(6450, 560, 850, 7150, 1000, 853, "steel"), box(6500, 610, 845, 7100, 950, 851, "metal_dark", plan=False),
                        cyl(6800, 500, 20, 850, 1150, "steel", plan=False)])
    add("洗碗機", "KITC", [box(7190, 1100, 100, 7210, 1700, 820, "steel", plan=False)])
    add("冰箱", "KITC", [box(7100, 2950, 0, 7800, 3650, 1850, "steel")], [((7100, 3300), (7800, 3300))])
    add("電器高櫃", "CASE", [box(4100, 2250, 0, 4800, 3650, 2400, "wood_white")],
        [((4130, 2250), (4130, 3650)), ((4100, 2950), (4800, 2950))])

    # living TV feature wall + floating console
    add("客廳電視牆-北櫃", "CASE", [box(5275, 9800, 0, 5650, 10750, 2600, "wood_walnut")], [((5275, 9800), (5650, 10750))])
    add("客廳電視牆-南櫃", "CASE", [box(5275, 5450, 0, 5650, 6050, 2600, "wood_walnut")], [((5275, 5450), (5650, 6050))])
    add("客廳電視牆-石材背板", "CASE", [box(5275, 6050, 0, 5400, 9800, 2600, "stone_marble")])
    add("客廳電視 75吋", "FURN", [box(5400, 7060, 1000, 5460, 8740, 1960, "tv_black")])
    add("客廳懸浮矮櫃", "CASE", [box(5400, 6900, 300, 5850, 9150, 650, "wood_walnut")])

    # entry & hall storage
    add("玄關鞋櫃", "CASE", [box(11950, 750, 0, 12450, 3600, 2400, "wood_white")],
        [((11950, 750), (12450, 2150)), ((12450, 750), (11950, 2150)), ((11950, 2150), (12450, 2150)),
         ((11950, 2150), (12450, 3600)), ((12450, 2150), (11950, 3600))])
    add("餐廳收納櫃", "CASE", [box(12600, 3250, 0, 14150, 3600, 2400, "wood_white")],
        [((12600, 3250), (14150, 3600)), ((14150, 3250), (12600, 3600))])
    add("玄關收納櫃", "CASE", [box(9400, 3300, 0, 10050, 3650, 2100, "wood_white")],
        [((9400, 3300), (10050, 3650)), ((10050, 3300), (9400, 3650))])

    # bathrooms — storage, showers, glass
    add("主衛浴收納高櫃", "CASE", [box(3650, 2250, 0, 3950, 4425, 2400, "wood_white")],
        [((3650, 2250), (3950, 4425)), ((3950, 2250), (3650, 4425))])
    add("主衛浴淋浴間", "PFIX", [box(600, 3410, 0, 1740, 4425, 30, "tile_dark", plan=False),
                             cyl(700, 3900, 120, 2150, 2170, "steel", plan=False)],
        [((600, 3410), (1740, 4425)), ((1740, 3410), (600, 4425))])
    add("主衛浴淋浴拉門", "GLAZ", [box(600, 3400, 0, 1750, 3410, 2000, "glass"), box(1740, 3410, 0, 1750, 4425, 2000, "glass")])
    add("衛浴(次臥一)淋浴間", "PFIX", [box(17310, 5575, 0, 18750, 7275, 30, "tile_dark", plan=False),
                                 cyl(18650, 6425, 120, 2150, 2170, "steel", plan=False)],
        [((17310, 7275), (18750, 5575))])
    add("衛浴(次臥一)淋浴隔屏", "GLAZ", [box(17300, 5575, 0, 17310, 7275, 2000, "glass")])
    add("衛浴(次臥一)收納櫃", "CASE", [box(15500, 5800, 0, 15950, 6350, 900, "wood_oak")])
    add("客衛吊櫃", "CASE", [box(7950, 3300, 1800, 9250, 3650, 2400, "wood_white")],
        [((7950, 3300), (9250, 3650)), ((9250, 3300), (7950, 3650))])
    add("衛浴(次臥二)收納櫃", "CASE", [box(12600, 2350, 0, 13150, 3100, 2100, "wood_white")])

    # landscape balcony planters
    for i, pl in enumerate(PLANTERS):
        add(f"陽台花台-{i + 1}", "PLNT", [xyprism(ring(pl, 80), 0, 450, "concrete_light"),
                                         xyprism(pl.buffer(-80, join_style=2), 0, 400, "soil", plan=False)])
    return objs


def furniture_objects():
    objs = []
    for name, tag, kind, params, cx, cy, rot in FURNITURE:
        prims, lines = FURN[kind](**params)
        M = tmat(cx, cy, 0, rot)
        objs.append(dict(name=name, tag=tag, kind=kind, params=params, M=M, rot=rot, pos=(cx, cy),
                         local=prims, local_lines=lines))
    return objs

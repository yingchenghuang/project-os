"""Build the 3D scene from model.py and export:
   * SketchUp Ruby builder (.rb)  — native groups, components, tags, materials, scenes
   * COLLADA (.dae)               — File > Import in SketchUp (any edition), Rhino, 3ds Max…
   * glTF binary (.glb)           — web viewer / Blender / Twinmotion
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

import model as M
from geom import Mesh, Prism, Z, box, cyl, elevation_prism, rect, triangles, xyprism

MATERIALS = {  # name: (rgb, alpha, 中文)
    "wall_ext": ((226, 223, 216), 1.0, "外牆"), "wall_int": ((243, 241, 236), 1.0, "內牆"),
    "column": ((168, 168, 166), 1.0, "結構柱"), "slab": ((150, 150, 150), 1.0, "結構樓板"),
    "floor_wood": ((178, 140, 100), 1.0, "木地板"), "floor_tile": ((214, 212, 206), 1.0, "磁磚"),
    "floor_stone": ((196, 190, 180), 1.0, "石材"), "floor_outdoor": ((170, 164, 154), 1.0, "戶外磚"),
    "floor_deck": ((150, 112, 80), 1.0, "戶外木平台"),
    "glass": ((175, 210, 228), 0.28, "玻璃"), "alu": ((64, 66, 70), 1.0, "鋁框"),
    "door_wood": ((206, 190, 168), 1.0, "室內門"), "door_entry": ((92, 66, 48), 1.0, "大門"),
    "door_frame": ((235, 232, 226), 1.0, "門框"),
    "wood_walnut": ((112, 78, 54), 1.0, "胡桃木"), "wood_oak": ((196, 160, 116), 1.0, "橡木"),
    "wood_white": ((236, 234, 229), 1.0, "白色櫃體"), "stone_marble": ((233, 231, 227), 1.0, "大理石"),
    "stone_quartz": ((222, 221, 218), 1.0, "石英石"),
    "fabric_sofa": ((120, 122, 126), 1.0, "沙發布"), "fabric_light": ((176, 176, 172), 1.0, "淺色布"),
    "fabric_beige": ((206, 192, 168), 1.0, "米色布"), "fabric_chair": ((150, 132, 112), 1.0, "椅面"),
    "fabric_head": ((168, 156, 140), 1.0, "床頭布"),
    "linen_white": ((246, 246, 243), 1.0, "白床單"), "linen_beige": ((214, 204, 184), 1.0, "被套"),
    "rug": ((214, 204, 186), 1.0, "地毯"), "tv_black": ((22, 22, 25), 1.0, "電視"),
    "metal_dark": ((48, 48, 52), 1.0, "黑鐵件"), "steel": ((184, 186, 190), 1.0, "不鏽鋼"),
    "porcelain": ((250, 250, 250), 1.0, "陶瓷"), "water": ((190, 215, 225), 1.0, "水"),
    "mirror": ((205, 220, 226), 1.0, "鏡面"), "appliance_white": ((238, 238, 236), 1.0, "家電白"),
    "glass_black": ((24, 24, 26), 1.0, "黑玻璃"), "lamp_shade": ((246, 238, 220), 1.0, "燈罩"),
    "terracotta": ((172, 104, 72), 1.0, "陶盆"), "plant": ((86, 128, 72), 1.0, "植栽"),
    "trunk": ((98, 72, 52), 1.0, "樹幹"), "soil": ((92, 72, 54), 1.0, "土壤"),
    "louver": ((92, 94, 98), 1.0, "百葉"), "concrete_light": ((196, 194, 188), 1.0, "清水模"),
    "tile_dark": ((150, 150, 148), 1.0, "淋浴地磚"), "ceiling": ((250, 250, 250), 1.0, "天花板"),
    "slab_finish": ((205, 200, 192), 1.0, "上層地坪"),
}

TAGS = {  # key: SketchUp tag / DXF layer name
    "WALL": "A-WALL 牆體", "COLS": "A-COLS 結構柱", "FLOR": "A-FLOR 地坪", "DOOR": "A-DOOR 門",
    "GLAZ": "A-GLAZ 窗與玻璃", "RAIL": "A-RAIL 欄杆", "FURN": "A-FURN 傢俱", "CASE": "A-CASE 系統櫃",
    "PFIX": "A-PFIX 衛浴設備", "KITC": "A-KITC 廚具", "EQPT": "A-EQPT 設備", "PLNT": "A-PLNT 植栽",
    "CLNG": "A-SLAB-UP 上層樓板 FL+3500(預設隱藏)",
}


# ------------------------------------------------------------------------------------------ scene assembly
def axis_box(ax, s0, s1, t0, t1, z0, z1, mat, plan=True):
    if ax == "x":
        return box(s0, t0, z0, s1, t1, z1, mat, plan)
    return box(t0, s0, z0, t1, s1, z1, mat, plan)


def axis_elev(ax, poly_sz, t0, thick, mat):
    """Elevation polygon (s absolute along wall, z) extruded across the wall from t0 by thick."""
    if ax == "x":
        return elevation_prism(poly_sz, (0, t0, 0), (1, 0, 0), (0, thick, 0), mat)
    return elevation_prism(poly_sz, (t0, 0, 0), (0, 1, 0), (thick, 0, 0), mat)


def walls():
    objs = []
    mat_of = {"ext": "wall_ext", "int": "wall_int", "low": "wall_ext", "louver": "louver"}
    for wid, (x0, y0, x1, y1, kind, h) in M.WALLS.items():
        ax = M.wall_axis(wid)
        s0, s1, t0, t1 = (x0, x1, y0, y1) if ax == "x" else (y0, y1, x0, x1)
        elev = rect(s0, M.WALL_BASE, s1, h)
        for o in M.openings_of(wid):
            z0, z1 = M.opening_zrange(o)
            elev = elev.difference(rect(o["s0"], M.WALL_BASE if z0 == 0 else z0, o["s1"], z1))
        parts = [elev] if elev.geom_type == "Polygon" else list(elev.geoms)
        prims = [axis_elev(ax, p, t0, t1 - t0, mat_of[kind]) for p in parts]
        label = {"ext": "外牆", "int": "隔間牆", "low": "矮牆", "louver": "冷氣百葉"}[kind]
        objs.append(dict(name=f"{label} {wid}", tag="WALL" if kind != "louver" else "EQPT", prims=prims))
    for cid, poly in M.COLUMNS.items():
        objs.append(dict(name=f"結構柱 {cid}", tag="COLS", prims=[xyprism(poly, M.WALL_BASE, M.WALL_H, "column")]))
    for name, poly in M.SHAFTS.items():
        objs.append(dict(name=name, tag="WALL", prims=[xyprism(poly, M.WALL_BASE, M.WALL_H, "wall_int")]))
    return objs


def floors():
    objs = []
    every = [p for _, p, *_ in M.ROOMS] + [M.wall_rect(w) for w in M.WALLS] + list(M.COLUMNS.values()) + list(M.SHAFTS.values())
    slab = unary_union(every).buffer(0)
    parts = [slab] if slab.geom_type == "Polygon" else list(slab.geoms)
    objs.append(dict(name="本層結構樓板", tag="FLOR", prims=[xyprism(p, -(M.FINISH_T + M.SLAB_T), -M.FINISH_T, "slab", plan=False) for p in parts]))
    for name, poly, lp, mat, outdoor in M.ROOMS:
        top = -50 if outdoor else 0
        parts = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
        objs.append(dict(name=f"地坪-{name}", tag="FLOR", prims=[xyprism(p, -80, top, mat, plan=False) for p in parts]))
    return objs


def ceiling():
    """Upper floor slab (soffit = clear height, top finish = FL + FLOOR_TO_FLOOR). Hidden by default."""
    every = [p for _, p, *_ in M.ROOMS] + [M.wall_rect(w) for w in M.WALLS] + list(M.COLUMNS.values()) + list(M.SHAFTS.values())
    slab = unary_union(every).buffer(0)
    parts = [slab] if slab.geom_type == "Polygon" else list(slab.geoms)
    z0 = M.WALL_H
    prims = [xyprism(p, z0, z0 + M.SLAB_T, "slab", plan=False) for p in parts]
    prims += [xyprism(p, z0 + M.SLAB_T, M.FLOOR_TO_FLOOR, "slab_finish", plan=False) for p in parts]
    return [dict(name="上層樓板 (版底+3,270／上層FL+3,500)", tag="CLNG", prims=prims)]


def openings():
    objs = []
    F = M.FRAME
    for o in M.OPENINGS:
        x0, y0, x1, y1, *_ = M.WALLS[o["wall"]]
        ax = M.wall_axis(o["wall"])
        t0, t1 = (y0, y1) if ax == "x" else (x0, x1)
        tm = (t0 + t1) / 2
        s0, s1, k = o["s0"], o["s1"], o["kind"]
        prims = []
        if k == "window":
            sill, head, n = o["sill"], o["head"], o.get("panels", 1)
            fr = Polygon(rect(s0, sill, s1, head).exterior.coords, [rect(s0 + 60, sill + 60, s1 - 60, head - 60).exterior.coords])
            prims.append(axis_elev(ax, fr, tm - 40, 80, "alu"))
            for i in range(1, n):
                sm = s0 + (s1 - s0) * i / n
                prims.append(axis_box(ax, sm - 30, sm + 30, tm - 40, tm + 40, sill + 60, head - 60, "alu"))
            prims.append(axis_box(ax, s0 + 60, s1 - 60, tm - 5, tm + 5, sill + 60, head - 60, "glass"))
            objs.append(dict(name=f"{o['id']} {o['label']}", tag="GLAZ", prims=prims))
            continue
        head = o["head"]
        if k == "slide4":
            prims += [axis_box(ax, s0, s0 + 60, tm - 70, tm + 70, 0, head, "alu"),
                      axis_box(ax, s1 - 60, s1, tm - 70, tm + 70, 0, head, "alu"),
                      axis_box(ax, s0, s1, tm - 70, tm + 70, head - 60, head, "alu"),
                      axis_box(ax, s0, s1, tm - 70, tm + 70, 0, 20, "alu")]
            L = s1 - s0 - 120
            for i in range(4):
                a = s0 + 60 + L * i / 4 - (40 if i else 0)
                b = s0 + 60 + L * (i + 1) / 4 + (40 if i < 3 else 0)
                off = -35 if i in (0, 3) else 35
                fr = Polygon(rect(a, 20, b, head - 60).exterior.coords, [rect(a + 50, 70, b - 50, head - 110).exterior.coords])
                prims.append(axis_elev(ax, fr, tm + off - 20, 40, "alu"))
                prims.append(axis_box(ax, a + 50, b - 50, tm + off - 5, tm + off + 5, 70, head - 110, "glass"))
            objs.append(dict(name=f"{o['id']} {o['label']}", tag="GLAZ", prims=prims))
            continue
        if k == "open":
            continue
        # frame
        prims += [axis_box(ax, s0, s0 + F, t0 - 10, t1 + 10, 0, head, "door_frame"),
                  axis_box(ax, s1 - F, s1, t0 - 10, t1 + 10, 0, head, "door_frame"),
                  axis_box(ax, s0, s1, t0 - 10, t1 + 10, head - F, head, "door_frame")]
        swing = o.get("swing", 1)
        face = t1 if swing > 0 else t0
        clear = s1 - s0 - 2 * F
        leaf_top = head - F - 5

        def leaf(hinge_s, toward, width, mat, glass=False):
            sa = hinge_s if toward > 0 else hinge_s - 40
            ta, tb = sorted((face, face + swing * width))
            if not glass:
                return [axis_box(ax, sa, sa + 40, ta, tb, 10, leaf_top, mat)]
            return [axis_box(ax, sa, sa + 40, ta, ta + 60, 10, leaf_top, "alu"),
                    axis_box(ax, sa, sa + 40, tb - 60, tb, 10, leaf_top, "alu"),
                    axis_box(ax, sa, sa + 40, ta + 60, tb - 60, 10, 110, "alu"),
                    axis_box(ax, sa, sa + 40, ta + 60, tb - 60, leaf_top - 60, leaf_top, "alu"),
                    axis_box(ax, sa + 15, sa + 25, ta + 60, tb - 60, 110, leaf_top - 60, "glass")]

        if k == "door":
            mat = "door_wood"
            if o["hinge"] == "s0":
                prims += leaf(s0 + F, +1, clear, mat, o.get("glass", False))
            else:
                prims += leaf(s1 - F, -1, clear, mat, o.get("glass", False))
        elif k == "double":
            prims += leaf(s0 + F, +1, o["main"], "door_entry") + leaf(s1 - F, -1, clear - o["main"], "door_entry")
        elif k == "slide":
            tt = face + swing * 10
            ta, tb = sorted((tt, tt + swing * 40))
            prims.append(axis_box(ax, s0 - 60, s1 + 60, ta, tb, 10, head, "door_wood"))
        objs.append(dict(name=f"{o['id']} {o['label']}", tag="DOOR", prims=prims))
    return objs


def rails():
    objs = []
    for i, path in enumerate(M.RAILS):
        prims = []
        z0 = -50
        for a, b in zip(path, path[1:]):
            a, b = np.array(a, float), np.array(b, float)
            L = float(np.linalg.norm(b - a))
            d = (b - a) / L
            n = np.array([-d[1], d[0]])
            along = (d[0], d[1], 0)
            o1 = (a[0] - n[0] * 10, a[1] - n[1] * 10, 0)
            prims.append(elevation_prism(rect(0, z0 + 100, L, z0 + 1000), o1, along, (n[0] * 20, n[1] * 20, 0), "glass"))
            o2 = (a[0] - n[0] * 30, a[1] - n[1] * 30, 0)
            prims.append(elevation_prism(rect(0, z0 + 1040, L, z0 + 1100), o2, along, (n[0] * 60, n[1] * 60, 0), "metal_dark"))
        for p in path[1:-1] if i == 0 else path:
            prims.append(cyl(p[0], p[1], 25, z0, z0 + 1040, "metal_dark", seg=12))
        objs.append(dict(name=["景觀陽台玻璃欄杆", "工作陽台欄杆"][i], tag="RAIL", prims=prims))
    return objs


def furniture():
    out = []
    for f in M.furniture_objects():
        key = f["kind"] + "|" + json.dumps(f["params"], sort_keys=True)
        out.append(dict(name=f["name"], tag=f["tag"], def_key=key, kind=f["kind"], local=f["local"], M=f["M"],
                        pos=(f["pos"][0], f["pos"][1], 0.0), rot=f["rot"],
                        prims=[p.transformed(f["M"]) for p in f["local"]]))
    return out


def casework():
    return [dict(name=c["name"], tag=c["tag"], prims=c["prims"]) for c in M.casework()]


def scene_objects(with_ceiling=False):
    objs = walls() + floors() + openings() + rails() + casework() + furniture()
    if with_ceiling:
        objs += ceiling()
    return objs


# ------------------------------------------------------------------------------------------ COLLADA
def write_dae(objs, path):
    import collada
    from collada import asset, geometry, material, scene, source

    c = collada.Collada()
    c.assetInfo.upaxis = asset.UP_AXIS.Z_UP
    c.assetInfo.unitmeter = 1.0
    c.assetInfo.unitname = "meter"
    mats = {}
    for name, (rgb, alpha, zh) in MATERIALS.items():
        col = tuple(v / 255 for v in rgb) + (1.0,)
        kw = dict(diffuse=col, double_sided=alpha < 1)
        if alpha < 1:
            kw.update(transparent=(1.0, 1.0, 1.0, 1.0), transparency=alpha, opaque_mode=material.OPAQUE_MODE.A_ONE)
        eff = material.Effect(f"{name}-fx", [], "lambert", **kw)
        mat = material.Material(f"{name}-mat", name, eff)
        c.effects.append(eff)
        c.materials.append(mat)
        mats[name] = mat
    tag_nodes = {k: scene.Node(f"tag_{k}", children=[]) for k in TAGS}
    for k, nd in tag_nodes.items():
        nd.name = TAGS[k]
    gi = 0
    for oi, obj in enumerate(objs):
        by_mat = {}
        for p in obj["prims"]:
            V, F = triangles(p)
            by_mat.setdefault(p.mat, []).append((V, F))
        geom_nodes = []
        for mat_name, chunks in by_mat.items():
            V = np.vstack([v for v, _ in chunks])
            offs = np.cumsum([0] + [len(v) for v, _ in chunks[:-1]])
            Fs = np.vstack([f + o for (_, f), o in zip(chunks, offs)])
            tri = V[Fs]
            N = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            ln = np.linalg.norm(N, axis=1)
            keep = ln > 1e-9
            Fs, N = Fs[keep], N[keep] / ln[keep][:, None]
            gid = f"g{gi}"
            gi += 1
            vs = source.FloatSource(gid + "-v", (V / 1000.0).astype(np.float32).ravel(), ("X", "Y", "Z"))
            ns = source.FloatSource(gid + "-n", N.astype(np.float32).ravel(), ("X", "Y", "Z"))
            g = geometry.Geometry(c, gid, f"{obj['name']}-{mat_name}", [vs, ns])
            il = source.InputList()
            il.addInput(0, "VERTEX", "#" + gid + "-v")
            il.addInput(1, "NORMAL", "#" + gid + "-n")
            idx = np.empty((len(Fs), 6), dtype=np.int32)
            idx[:, 0::2] = Fs
            idx[:, 1::2] = np.arange(len(Fs))[:, None]
            g.primitives.append(g.createTriangleSet(idx.ravel(), il, "m0"))
            c.geometries.append(g)
            geom_nodes.append(scene.GeometryNode(g, [scene.MaterialNode("m0", mats[mat_name], inputs=[])]))
        nd = scene.Node(f"obj{oi}", children=geom_nodes)
        nd.name = obj["name"]
        tag_nodes[obj["tag"]].children.append(nd)
    root = scene.Node("DexinTaiji_B", children=[n for n in tag_nodes.values() if n.children])
    root.name = "德鑫泰極B戶"
    sc = scene.Scene("scene", [root])
    c.scenes.append(sc)
    c.scene = sc
    c.write(str(path))


# ------------------------------------------------------------------------------------------ glTF
def write_glb(objs, path):
    import trimesh
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals

    sc = trimesh.Scene()
    pbr = {}
    for name, (rgb, alpha, zh) in MATERIALS.items():
        pbr[name] = PBRMaterial(name=name, baseColorFactor=[*(v / 255 for v in rgb), alpha], metallicFactor=0.0,
                                roughnessFactor=0.85 if alpha == 1 else 0.1,
                                alphaMode="BLEND" if alpha < 1 else "OPAQUE", doubleSided=alpha < 1)
    for oi, obj in enumerate(objs):
        by_mat = {}
        for p in obj["prims"]:
            V, F = triangles(p)
            by_mat.setdefault(p.mat, []).append((V, F))
        for mat_name, chunks in by_mat.items():
            V = np.vstack([v for v, _ in chunks]) / 1000.0
            offs = np.cumsum([0] + [len(v) for v, _ in chunks[:-1]])
            F = np.vstack([f + o for (_, f), o in zip(chunks, offs)])
            m = trimesh.Trimesh(V, F, process=False, visual=TextureVisuals(material=pbr[mat_name]))
            sc.add_geometry(m, node_name=f"{obj['tag']}|{oi}|{obj['name']}|{mat_name}",
                            geom_name=f"{oi}-{mat_name}")
    sc.export(str(path), file_type="glb")


# ------------------------------------------------------------------------------------------ SketchUp Ruby
def r1(v):
    return round(float(v), 1)


def prim_json(p):
    if isinstance(p, Mesh):
        return {"t": "mesh", "m": p.mat, "pts": [[r1(a) for a in v] for v in p.verts], "polys": p.faces}
    base = {"m": p.mat, "o": [r1(a) for a in p.o], "u": [round(float(a), 6) for a in p.u],
            "v": [round(float(a), 6) for a in p.v], "e": [r1(a) for a in p.e]}
    if p.circle:
        base.update(t="circle", c=[r1(p.circle[0]), r1(p.circle[1])], r=r1(p.circle[2]),
                    seg=24 if p.circle[2] > 60 else 12)
        return base
    base.update(t="prism", outer=[[r1(a), r1(b)] for a, b in list(p.poly.exterior.coords)[:-1]],
                holes=[[[r1(a), r1(b)] for a, b in list(r.coords)[:-1]] for r in p.poly.interiors])
    return base


RUBY = r'''# encoding: UTF-8
# =====================================================================================
#  德鑫泰極 B戶 標準層 — SketchUp 3D 建模腳本（由 model.py 自動產生，請勿手改數據區）
#  使用方式：SketchUp 2017 以上 → 延伸程式(Extensions) → Developer → Ruby Console
#            輸入： load 'C:/路徑/DexinTaiji_B_sketchup.rb'   (Mac: load '/Users/…/DexinTaiji_B_sketchup.rb')
#  產出：單位 mm；群組 / 元件 / 標籤(Tags) / 材質 / 場景（鳥瞰、平面俯視、客廳視角）
# =====================================================================================
require 'json'

module DexinTaijiB
  DATA = JSON.parse(<<'__JSON__')
%%JSON%%
__JSON__

  def self.v3(a)
    Geom::Vector3d.new(a[0].mm, a[1].mm, a[2].mm)
  end

  def self.p3(a)
    Geom::Point3d.new(a[0].mm, a[1].mm, a[2].mm)
  end

  def self.lp(pr, s, t)
    o = pr['o']; u = pr['u']; v = pr['v']
    Geom::Point3d.new((o[0] + s * u[0] + t * v[0]).mm, (o[1] + s * u[1] + t * v[1]).mm, (o[2] + s * u[2] + t * v[2]).mm)
  end

  def self.build_prim(ents, pr, mats)
    g = ents.add_group
    ge = g.entities
    if pr['t'] == 'mesh'
      pts = pr['pts'].map { |a| p3(a) }
      mesh = Geom::PolygonMesh.new(pts.size, pr['polys'].size)
      pr['polys'].each { |f| mesh.add_polygon(f.map { |i| pts[i] }) }
      ge.add_faces_from_mesh(mesh, Geom::PolygonMesh::AUTO_SOFTEN | Geom::PolygonMesh::SMOOTH_SOFT_EDGES)
      g.material = mats[pr['m']]
      return g
    end
    e = v3(pr['e'])
    face = nil
    if pr['t'] == 'circle'
      edges = ge.add_circle(lp(pr, pr['c'][0], pr['c'][1]), e, pr['r'].mm, pr['seg'])
      face = ge.add_face(edges)
    else
      face = ge.add_face(pr['outer'].map { |q| lp(pr, q[0], q[1]) })
      (pr['holes'] || []).each do |h|
        hf = ge.add_face(h.map { |q| lp(pr, q[0], q[1]) })
        hf.erase! if hf && hf.valid? && hf != face
      end
    end
    if face && face.valid?
      face.reverse! if face.normal.dot(e) < 0
      face.pushpull(e.length)
    else
      @skipped += 1
    end
    g.material = mats[pr['m']]
    g
  end

  def self.camera(eye, target, up, persp = true, fov = 45)
    c = Sketchup::Camera.new(eye.map { |a| a.mm }, target.map { |a| a.mm }, up)
    c.perspective = persp
    c.fov = fov if persp
    c
  end

  def self.build
    model = Sketchup.active_model
    @skipped = 0
    model.start_operation('德鑫泰極 B戶 3D 建模', true)
    begin
      uo = model.options['UnitsOptions']
      uo['LengthFormat'] = 0
      uo['LengthUnit'] = 2
      uo['LengthPrecision'] = 0
      mats = {}
      DATA['materials'].each do |name, m|
        mat = model.materials[name] || model.materials.add(name)
        mat.color = Sketchup::Color.new(*m['rgb'])
        mat.alpha = m['alpha']
        mats[name] = mat
      end
      tags = {}
      DATA['tags'].each { |k, n| tags[k] = model.layers[n] || model.layers.add(n) }
      root = model.active_entities.add_group
      root.name = DATA['name']
      defs = {}
      DATA['definitions'].each do |key, d|
        cd = model.definitions.add(d['name'])
        d['prims'].each { |pr| build_prim(cd.entities, pr, mats) }
        defs[key] = cd
      end
      DATA['objects'].each do |o|
        if o['def']
          tr = Geom::Transformation.new(p3(o['pos'])) * Geom::Transformation.rotation(ORIGIN, Z_AXIS, o['rot'].degrees)
          inst = root.entities.add_instance(defs[o['def']], tr)
          inst.name = o['name']
          inst.layer = tags[o['tag']]
        else
          g = root.entities.add_group
          g.name = o['name']
          g.layer = tags[o['tag']]
          o['prims'].each { |pr| build_prim(g.entities, pr, mats) }
        end
      end
      tags['CLNG'].visible = false if tags['CLNG']
      pages = model.pages
      view = model.active_view
      cx = 9700; cy = 6350
      [['鳥瞰 (東南)', camera([cx + 14000, cy - 17000, 21000], [cx, cy, 0], Z_AXIS)],
       ['鳥瞰 (西北)', camera([cx - 15000, cy + 17000, 20000], [cx, cy, 0], Z_AXIS)],
       ['平面俯視', camera([cx, cy, 40000], [cx, cy, 0], Y_AXIS, false)],
       ['客廳往陽台', camera([7600, 4600, 1550], [9300, 11500, 1300], Z_AXIS, true, 60)]].each do |name, cam|
        view.camera = cam
        pg = pages[name] || pages.add(name)
        pg.update
      end
      pages.selected_page = pages['鳥瞰 (東南)']
      model.commit_operation
      view.zoom_extents if pages.size == 0
      UI.messagebox("德鑫泰極 B戶 3D 模型完成。\n物件 #{DATA['objects'].size} 組，元件定義 #{defs.size} 種" +
                    (@skipped > 0 ? "，略過 #{@skipped} 個無效面" : '') + '。')
    rescue StandardError => e
      model.abort_operation
      UI.messagebox("建模失敗：#{e.message}")
      raise
    end
  end
end

DexinTaijiB.build
'''


def write_rb(objs, path):
    defs, out = {}, []
    for o in objs:
        if "def_key" in o:
            key = o["def_key"]
            if key not in defs:
                defs[key] = {"name": f"{o['kind']}", "prims": [prim_json(p) for p in o["local"]]}
            out.append({"name": o["name"], "tag": o["tag"], "def": key, "pos": [r1(a) for a in o["pos"]], "rot": o["rot"]})
        else:
            out.append({"name": o["name"], "tag": o["tag"], "prims": [prim_json(p) for p in o["prims"]]})
    # readable definition names
    names = {"bed": "床", "nightstand": "床頭櫃", "bench": "床尾椅", "sofa": "三人沙發", "armchair": "單人椅",
             "coffee_table": "茶几", "side_table": "邊几", "ottoman": "腳凳", "rug": "地毯", "dining_table": "餐桌",
             "chair": "餐椅", "tv_console": "電視櫃", "wardrobe": "衣櫃", "open_closet": "開放吊衣櫃", "desk": "書桌",
             "toilet": "馬桶", "vanity": "洗手檯", "bathtub": "獨立浴缸", "washer": "洗衣機", "laundry_sink": "洗衣槽",
             "ac_outdoor": "冷氣室外機", "tree": "喬木盆栽", "shrub": "灌木", "round_table": "圓桌"}
    for i, (k, d) in enumerate(defs.items()):
        kind = k.split("|")[0]
        d["name"] = f"{names.get(kind, kind)}_{i + 1:02d}"
    data = {"name": "德鑫泰極 B戶 標準層", "materials": {k: {"rgb": list(v[0]), "alpha": v[1]} for k, v in MATERIALS.items()},
            "tags": TAGS, "definitions": defs, "objects": out}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    Path(path).write_text(RUBY.replace("%%JSON%%", js), encoding="utf-8")


# ------------------------------------------------------------------------------------------ OBJ + MTL
def _safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_()" else "_" for ch in s)


def write_obj(objs, path):
    """Wavefront OBJ in metres + MTL. One `o` per object (prefixed with its layer code), `usemtl` per material."""
    path = Path(path)
    mtl = path.with_suffix(".mtl")
    lines = [f"# 德鑫泰極 B戶 標準層 — units: metres, Z-up (Blender/Rhino: import with 'Z up')",
             f"mtllib {mtl.name}"]
    base = 1
    for obj in objs:
        by_mat = {}
        for p in obj["prims"]:
            V, F = triangles(p)
            by_mat.setdefault(p.mat, []).append((V, F))
        lines.append(f"o {TAGS[obj['tag']].split()[0]}__{_safe(obj['name'])}")
        for mat_name, chunks in by_mat.items():
            lines.append(f"usemtl {mat_name}")
            for V, F in chunks:
                lines += [f"v {x / 1000:.4f} {y / 1000:.4f} {z / 1000:.4f}" for x, y, z in V]
                lines += [f"f {a + base} {b + base} {c + base}" for a, b, c in F]
                base += len(V)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    m = []
    for name, (rgb, alpha, zh) in MATERIALS.items():
        r, g, b = (v / 255 for v in rgb)
        m += [f"newmtl {name}", f"# {zh}", f"Kd {r:.4f} {g:.4f} {b:.4f}", f"Ka {r * .2:.4f} {g * .2:.4f} {b * .2:.4f}",
              "Ks 0.0500 0.0500 0.0500", f"d {alpha:.2f}", "illum 2", ""]
    mtl.write_text("\n".join(m), encoding="utf-8")


# ------------------------------------------------------------------------------------------ 3D DXF
def write_dxf3d(objs, path):
    """3D CAD model: one POLYFACE mesh per object+material (opens in AutoCAD, Rhino, SketchUp Pro, Revit)."""
    import ezdxf
    from ezdxf import colors, units

    doc = ezdxf.new("R2013", setup=True)
    doc.units = units.MM
    doc.header["$INSUNITS"] = 4
    aci = {"WALL": 7, "COLS": 8, "FLOR": 9, "DOOR": 3, "GLAZ": 4, "RAIL": 140, "FURN": 30, "CASE": 5,
           "PFIX": 6, "KITC": 6, "EQPT": 30, "PLNT": 82, "CLNG": 9}
    for k, name in TAGS.items():
        code = name.split()[0]
        lay = doc.layers.add(code, color=aci.get(k, 7))
        lay.description = name
        if k == "CLNG":
            lay.off()
    msp = doc.modelspace()
    for obj in objs:
        layer = TAGS[obj["tag"]].split()[0]
        by_mat = {}
        for p in obj["prims"]:
            V, F = triangles(p)
            by_mat.setdefault(p.mat, []).append((V, F))
        for mat_name, chunks in by_mat.items():
            pf = msp.add_polyface(dxfattribs={"layer": layer})
            pf.rgb = MATERIALS[mat_name][0]
            faces = []
            for V, F in chunks:
                faces += [[tuple(map(float, V[i])) for i in tri] for tri in F]
            pf.append_faces(faces, dxfattribs={"layer": layer})
            pf.optimize()
    doc.saveas(str(path))


if __name__ == "__main__":
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "../output")
    objs = scene_objects(with_ceiling=True)        # upper slab included as its own (hidden) layer/group
    write_rb(objs, outdir / "DexinTaiji_B_sketchup.rb")
    write_dae(objs, outdir / "DexinTaiji_B_3D.dae")
    write_glb(objs, outdir / "DexinTaiji_B_3D.glb")
    write_obj(objs, outdir / "DexinTaiji_B_3D_m.obj")
    write_dxf3d(objs, outdir / "DexinTaiji_B_3D.dxf")
    ntri = sum(len(triangles(p)[1]) for o in objs for p in o["prims"])
    print("objects", len(objs), "prims", sum(len(o["prims"]) for o in objs), "triangles", ntri)

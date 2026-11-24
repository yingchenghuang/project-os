"""Writers: Rhino .3dm (rhino3dm), COLLADA .dae (SketchUp import), Wavefront
.obj/.mtl and binary glTF .glb (previews / web)."""
import io
import json
import math
import os
import struct
import xml.sax.saxutils as sx

import numpy as np
from PIL import Image


# ------------------------------------------------------------------ prepare
class Prepared:
    def __init__(self, S):
        self.S = S
        self.obj_parts = []      # (obj, [(mat, arrays)])
        self.def_parts = {}      # name -> [(mat, arrays)]
        for o in S.objects:
            parts = []
            for mat, me in o['parts']:
                a = me.finalize()
                if a is not None:
                    parts.append((mat, self._scale(mat, a)))
            if parts:
                self.obj_parts.append((o, parts))
        for name, d in S.defs.items():
            parts = []
            for mat, me in d['parts']:
                a = me.finalize()
                if a is not None:
                    parts.append((mat, self._scale(mat, a)))
            self.def_parts[name] = parts

    def _scale(self, mat, a):
        tile = self.S.materials[mat].get('tile', (1.0, 1.0))
        a = dict(a)
        a['T'] = a['T'] / np.array(tile, float)
        return a

    def stats(self):
        tri = sum(len(a['F']) for _, ps in self.obj_parts for _, a in ps)
        dtri = {n: sum(len(a['F']) for _, a in ps) for n, ps in self.def_parts.items()}
        itri = sum(dtri[i['defname']] for i in self.S.instances)
        return dict(objects=len(self.obj_parts), object_triangles=tri, definitions=len(self.def_parts),
                    instances=len(self.S.instances), instanced_triangles=itri, lights=len(self.S.lights),
                    materials=len(self.S.materials))


def _layer_color(path):
    h = abs(hash(path.split('::')[0])) % 360
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h / 360, 0.45, 0.75)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


# ------------------------------------------------------------------ 3dm
def write_3dm(P, path, texdir_rel='textures'):
    import rhino3dm as r
    S = P.S
    f = r.File3dm()
    f.Settings.ModelUnitSystem = r.UnitSystem.Meters
    f.Settings.ModelAbsoluteTolerance = 0.001
    f.ApplicationName = 'capistran-3d generator (rhino3dm)'
    outdir = os.path.dirname(os.path.abspath(path))

    # layers
    layer_index = {}

    def layer(pathname):
        if pathname in layer_index:
            return layer_index[pathname]
        parts = pathname.split('::')
        parent_id = None
        for i in range(len(parts)):
            p = '::'.join(parts[:i + 1])
            if p not in layer_index:
                L = r.Layer()
                L.Name = parts[i]
                L.Color = _layer_color(p)
                if parent_id is not None:
                    L.ParentLayerId = parent_id
                if 'Counterweights' in p or 'optional' in p:
                    L.Visible = False
                idx = f.Layers.Add(L)
                layer_index[p] = idx
            parent_id = f.Layers[layer_index[p]].Id
        return layer_index[pathname]

    # materials
    mat_index = {}

    def texref(fn):
        t = r.Texture()
        t.FileName = texdir_rel + '/' + fn   # relative to the .3dm (keep the textures folder beside it)
        return t

    for name, m in S.materials.items():
        M = r.Material()
        M.Name = name
        c = m.get('color', (200, 200, 200))
        M.DiffuseColor = (c[0], c[1], c[2], 255)
        M.AmbientColor = (0, 0, 0, 255)
        refl = m.get('refl', 0.0)
        gloss = m.get('gloss', 0.2)
        M.Reflectivity = float(refl)
        M.ReflectionGlossiness = float(gloss)
        M.Shine = float(255 * gloss)
        M.SpecularColor = (255, 255, 255, 255) if not m.get('metal') else (c[0], c[1], c[2], 255)
        M.ReflectionColor = (255, 255, 255, 255) if not m.get('metal') else (c[0], c[1], c[2], 255)
        M.FresnelReflections = not m.get('metal', False)
        if 'transp' in m:
            M.Transparency = float(m['transp'])
            M.IndexOfRefraction = float(m.get('ior', 1.5))
            M.TransparentColor = (255, 255, 255, 255)
        if 'emit' in m:
            e = m['emit']
            M.EmissionColor = (e[0], e[1], e[2], 255)
        if 'tex' in m:
            M.SetBitmapTexture(texref(m['tex']))
            if m.get('alpha'):
                M.SetTransparencyTexture(texref(m['tex']))
        if 'bump' in m:
            M.SetBumpTexture(texref(m['bump']))
        mat_index[name] = f.Materials.Add(M)

    def attrs(name, layer_path, mat):
        a = r.ObjectAttributes()
        a.Name = name
        a.LayerIndex = layer(layer_path)
        if mat is not None:
            a.MaterialSource = r.ObjectMaterialSource.MaterialFromObject
            a.MaterialIndex = mat_index[mat]
        return a

    def rmesh(arr):
        m = r.Mesh()
        Pv, N, T, F = arr['P'], arr['N'], arr['T'], arr['F']
        for p in Pv:
            m.Vertices.Add(float(p[0]), float(p[1]), float(p[2]))
        for n in N:
            m.Normals.Add(float(n[0]), float(n[1]), float(n[2]))
        tc = m.TextureCoordinates
        for t in T:
            tc.__add__(float(t[0]), float(t[1]))
        for a, b, c in F:
            m.Faces.AddFace(int(a), int(b), int(c))
        return m

    for o, parts in P.obj_parts:
        for mat, arr in parts:
            nm = o['name'] if len(parts) == 1 else f"{o['name']} [{mat}]"
            f.Objects.AddMesh(rmesh(arr), attrs(nm, o['layer'], mat))

    # blocks
    def_index = {}
    for name, parts in P.def_parts.items():
        geoms, atts = [], []
        for mat, arr in parts:
            geoms.append(rmesh(arr))
            a = r.ObjectAttributes()
            a.Name = f'{name} [{mat}]'
            a.LayerIndex = layer('00_Reference::Block Definitions')
            a.MaterialSource = r.ObjectMaterialSource.MaterialFromObject
            a.MaterialIndex = mat_index[mat]
            atts.append(a)
        idx = f.InstanceDefinitions.Add(name, f'{name} (St. Johann von Capistran)', '', '', r.Point3d(0, 0, 0), tuple(geoms), tuple(atts))
        def_index[name] = idx
    for inst in S.instances:
        M = inst['M']
        X = r.Transform(1.0)
        for i in range(4):
            for j in range(4):
                setattr(X, f'M{i}{j}', float(M[i, j]))
        idef = f.InstanceDefinitions[def_index[inst['defname']]]
        ref = r.InstanceReference(idef.Id, X)
        f.Objects.AddInstanceObject(ref, attrs(inst['name'], inst['layer'], None))

    # lights
    for L in S.lights:
        li = r.Light()
        li.Name = L['name']
        kind = L['kind']
        li.LightStyle = {'spot': r.LightStyle.WorldSpot, 'point': r.LightStyle.WorldPoint, 'linear': r.LightStyle.WorldLinear}[kind]
        li.Location = r.Point3d(*map(float, L['pos']))
        if kind == 'spot':
            if 'target' in L:
                d = np.array(L['target'], float) - np.array(L['pos'], float)
            else:
                d = np.array(L['dir'], float)
            d = d / np.linalg.norm(d)
            li.Direction = r.Vector3d(*map(float, d * 2.0))
            li.SpotAngleRadians = math.radians(L.get('spot_deg', 45) / 2)
            li.HotSpot = float(L.get('hotspot', 0.5))
        elif kind == 'linear':
            v = L['vec']
            li.Length = r.Vector3d(*map(float, v))
            li.Direction = r.Vector3d(0, 0, -1)
            li.Width = r.Vector3d(0, 0, 0.02)
        else:
            li.Direction = r.Vector3d(0, 0, -1)
        c = L['color']
        li.Diffuse = (c[0], c[1], c[2], 255)
        li.Intensity = min(1.0, L.get('watts', 40) / 100.0)
        li.PowerWatts = float(L.get('watts', 40))
        li.IsEnabled = not L.get('off', False)
        a = r.ObjectAttributes(); a.Name = L['name']; a.LayerIndex = layer(L['layer'])
        f.Objects.Add(li, a)

    # reference curves & labels
    for c in S.curves:
        a = r.ObjectAttributes(); a.Name = c['name']; a.LayerIndex = layer(c['layer'])
        if c['kind'] == 'circle':
            f.Objects.AddCircle(r.Circle(r.Point3d(*c['c']), c['r']), a)
        else:
            f.Objects.AddLine(r.Point3d(*c['a']), r.Point3d(*c['b']), a)
    for lay, text, pt in S.dots:
        a = r.ObjectAttributes(); a.Name = text; a.LayerIndex = layer(lay)
        f.Objects.AddTextDot(text, r.Point3d(*pt), a)

    # named views
    for v in S.views:
        vi = r.ViewInfo()
        vi.Name = v['name']
        vp = r.ViewportInfo()
        cam = np.array(v['cam'], float); tgt = np.array(v['tgt'], float)
        d = tgt - cam
        vp.SetCameraLocation(r.Point3d(*map(float, cam)))
        vp.SetCameraDirection(r.Vector3d(*map(float, d)))
        vp.SetCameraUp(r.Vector3d(0, 0, 1))
        try:
            vp.SetScreenPort(0, 1600, 0, 900, 0, 1)
        except Exception:
            pass
        vp.ChangeToPerspectiveProjection(float(np.linalg.norm(d)), True, float(v['lens']))
        try:
            vp.TargetPoint = r.Point3d(*map(float, tgt))
        except Exception:
            pass
        vi.Viewport = vp
        f.NamedViews.Add(vi)

    # sun & sky: Munich, Parkstadt Bogenhausen
    rs = f.Settings.RenderSettings
    sun = rs.Sun
    sun.EnableOn = True
    sun.ManualControlOn = False
    sun.Latitude = 48.1478
    sun.Longitude = 11.6339
    sun.TimeZone = 1.0
    sun.DaylightSavingOn = True
    sun.DaylightSavingMinutes = 60
    sun.Year, sun.Month, sun.Day = 2026, 6, 21
    sun.Hours = 17.5
    sun.North = 90.0
    sun.Intensity = 1.0
    try:
        rs.Skylight.Enabled = True
        rs.Skylight.ShadowIntensity = 1.0
        rs.LinearWorkflow.PreProcessGammaOn = True
        rs.LinearWorkflow.PostProcessGammaOn = True
        rs.GroundPlane.Enabled = False
    except Exception:
        pass
    rs.BackgroundColorTop = (150, 186, 224, 255)
    rs.BackgroundColorBottom = (226, 236, 244, 255)
    f.Write(path, 8)


# ------------------------------------------------------------------ DAE
def _fmt(arr, prec=5):
    return ' '.join(f'{x:.{prec}f}'.rstrip('0').rstrip('.') if x != 0 else '0' for x in np.asarray(arr).ravel())


def _ids(name):
    s = ''.join(ch if ch.isalnum() else '_' for ch in name)
    return s


def write_dae(P, path, texdir_rel='textures'):
    S = P.S
    out = io.StringIO()
    w = out.write
    w('<?xml version="1.0" encoding="utf-8"?>\n')
    w('<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">\n')
    w('<asset><contributor><authoring_tool>capistran-3d generator</authoring_tool></contributor>'
      '<created>2026-11-24T00:00:00</created><modified>2026-11-24T00:00:00</modified>'
      '<unit meter="1" name="meter"/><up_axis>Z_UP</up_axis></asset>\n')
    # images
    texs = sorted({m[k] for m in S.materials.values() for k in ('tex',) if k in m})
    w('<library_images>\n')
    for t in texs:
        w(f'<image id="img_{_ids(t)}" name="{_ids(t)}"><init_from>{texdir_rel}/{t}</init_from></image>\n')
    w('</library_images>\n')
    # effects / materials
    w('<library_effects>\n')
    for name, m in S.materials.items():
        mid = _ids(name)
        w(f'<effect id="fx_{mid}"><profile_COMMON>')
        if 'tex' in m:
            t = _ids(m['tex'])
            w(f'<newparam sid="surf_{t}"><surface type="2D"><init_from>img_{t}</init_from></surface></newparam>'
              f'<newparam sid="samp_{t}"><sampler2D><source>surf_{t}</source></sampler2D></newparam>')
        w('<technique sid="COMMON"><lambert>')
        if 'emit' in m:
            e = m['emit']
            w(f'<emission><color>{e[0]/255:.4f} {e[1]/255:.4f} {e[2]/255:.4f} 1</color></emission>')
        if 'tex' in m:
            w(f'<diffuse><texture texture="samp_{_ids(m["tex"])}" texcoord="UVSET0"/></diffuse>')
        else:
            c = m.get('color', (200, 200, 200))
            w(f'<diffuse><color>{c[0]/255:.4f} {c[1]/255:.4f} {c[2]/255:.4f} 1</color></diffuse>')
        if 'transp' in m:
            a = 1.0 - m['transp']
            w(f'<transparent opaque="A_ONE"><color>1 1 1 {a:.3f}</color></transparent><transparency><float>1</float></transparency>')
        elif m.get('alpha'):
            w(f'<transparent opaque="A_ONE"><texture texture="samp_{_ids(m["tex"])}" texcoord="UVSET0"/></transparent>')
        w('</lambert></technique></profile_COMMON>'
          '<extra><technique profile="GOOGLEEARTH"><double_sided>1</double_sided></technique></extra></effect>\n')
    w('</library_effects>\n<library_materials>\n')
    for name in S.materials:
        mid = _ids(name)
        w(f'<material id="mat_{mid}" name="{sx.escape(name)}"><instance_effect url="#fx_{mid}"/></material>\n')
    w('</library_materials>\n<library_geometries>\n')

    def geometry(gid, parts):
        w(f'<geometry id="{gid}" name="{gid}"><mesh>')
        Pv = np.vstack([a['P'] for _, a in parts]); N = np.vstack([a['N'] for _, a in parts]); T = np.vstack([a['T'] for _, a in parts])
        w(f'<source id="{gid}_p"><float_array id="{gid}_pa" count="{Pv.size}">{_fmt(Pv, 4)}</float_array>'
          f'<technique_common><accessor source="#{gid}_pa" count="{len(Pv)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>')
        w(f'<source id="{gid}_n"><float_array id="{gid}_na" count="{N.size}">{_fmt(N, 4)}</float_array>'
          f'<technique_common><accessor source="#{gid}_na" count="{len(N)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>')
        w(f'<source id="{gid}_t"><float_array id="{gid}_ta" count="{T.size}">{_fmt(T, 4)}</float_array>'
          f'<technique_common><accessor source="#{gid}_ta" count="{len(T)}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common></source>')
        w(f'<vertices id="{gid}_v"><input semantic="POSITION" source="#{gid}_p"/><input semantic="NORMAL" source="#{gid}_n"/></vertices>')
        off = 0
        for mat, a in parts:
            F = a['F'] + off
            off += len(a['P'])
            idx = np.repeat(F.ravel(), 2)
            w(f'<triangles material="{_ids(mat)}" count="{len(F)}"><input semantic="VERTEX" source="#{gid}_v" offset="0"/>'
              f'<input semantic="TEXCOORD" source="#{gid}_t" offset="1" set="0"/><p>{" ".join(map(str, idx))}</p></triangles>')
        w('</mesh></geometry>\n')

    gids = []
    for i, (o, parts) in enumerate(P.obj_parts):
        gid = f'g{i:03d}_{_ids(o["name"])[:40]}'
        geometry(gid, parts); gids.append(gid)
    dgids = {}
    for name, parts in P.def_parts.items():
        gid = f'def_{_ids(name)}'
        geometry(gid, parts); dgids[name] = gid
    w('</library_geometries>\n')

    def inst_geom(gid, parts):
        mats = sorted({m for m, _ in parts})
        s = f'<instance_geometry url="#{gid}"><bind_material><technique_common>'
        for m in mats:
            s += f'<instance_material symbol="{_ids(m)}" target="#mat_{_ids(m)}"><bind_vertex_input semantic="UVSET0" input_semantic="TEXCOORD" input_set="0"/></instance_material>'
        return s + '</technique_common></bind_material></instance_geometry>'

    # component definitions
    w('<library_nodes>\n')
    for name, parts in P.def_parts.items():
        w(f'<node id="comp_{_ids(name)}" name="{sx.escape(name)}">{inst_geom(dgids[name], parts)}</node>\n')
    w('</library_nodes>\n')
    # scene tree by layer path
    tree = {}
    for (o, parts), gid in zip(P.obj_parts, gids):
        tree.setdefault(o['layer'], []).append(('g', o['name'], gid, parts))
    for inst in S.instances:
        tree.setdefault(inst['layer'], []).append(('i', inst['name'], inst['defname'], inst['M']))
    w('<library_visual_scenes><visual_scene id="Scene" name="St_Johann_von_Capistran">\n')
    w('<node id="Capistran" name="St. Johann von Capistran (Sep Ruf 1960)">')
    groups = {}
    for lp in sorted(tree):
        top = lp.split('::')[0]
        groups.setdefault(top, []).append(lp)
    nid = 0
    for top, lps in groups.items():
        w(f'<node id="n{nid}" name="{sx.escape(top)}">'); nid += 1
        for lp in lps:
            sub = lp.split('::', 1)[1] if '::' in lp else lp
            w(f'<node id="n{nid}" name="{sx.escape(sub)}">'); nid += 1
            for item in tree[lp]:
                if item[0] == 'g':
                    _, nm, gid, parts = item
                    w(f'<node id="n{nid}" name="{sx.escape(nm)}">{inst_geom(gid, parts)}</node>'); nid += 1
                else:
                    _, nm, dn, M = item
                    w(f'<node id="n{nid}" name="{sx.escape(nm)}"><matrix>{_fmt(M, 6)}</matrix><instance_node url="#comp_{_ids(dn)}"/></node>'); nid += 1
            w('</node>')
        w('</node>\n')
    w('</node>\n</visual_scene></library_visual_scenes>\n<scene><instance_visual_scene url="#Scene"/></scene>\n</COLLADA>\n')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(out.getvalue())


# ------------------------------------------------------------------ OBJ
def write_obj(P, path, texdir_rel='textures'):
    S = P.S
    base = os.path.splitext(os.path.basename(path))[0]
    with open(os.path.splitext(path)[0] + '.mtl', 'w') as fm:
        for name, m in S.materials.items():
            c = m.get('color', (200, 200, 200))
            fm.write(f'newmtl {_ids(name)}\nKd {c[0]/255:.4f} {c[1]/255:.4f} {c[2]/255:.4f}\nKa 0 0 0\n')
            fm.write(f'Ks {m.get("refl", 0.04):.3f} {m.get("refl", 0.04):.3f} {m.get("refl", 0.04):.3f}\nNs {10 + 300 * m.get("gloss", 0.2):.1f}\n')
            if 'transp' in m:
                fm.write(f'd {1 - m["transp"]:.3f}\nNi {m.get("ior", 1.5):.2f}\nillum 4\n')
            else:
                fm.write('d 1\nillum 2\n')
            if 'emit' in m:
                e = m['emit']; fm.write(f'Ke {e[0]/255:.3f} {e[1]/255:.3f} {e[2]/255:.3f}\n')
            if 'tex' in m:
                fm.write(f'map_Kd {texdir_rel}/{m["tex"]}\n')
                if m.get('alpha'):
                    fm.write(f'map_d {texdir_rel}/{m["tex"]}\n')
            if 'bump' in m:
                fm.write(f'map_bump -bm 0.02 {texdir_rel}/{m["bump"]}\n')
            fm.write('\n')
    vo = 1
    with open(path, 'w') as fo:
        fo.write(f'# St. Johann von Capistran, Munich (Sep Ruf 1958-60) - metres, Z up\nmtllib {base}.mtl\n')

        def dump(name, parts, M=None):
            nonlocal vo
            fo.write(f'o {_ids(name)}\n')
            for mat, a in parts:
                Pv, N = a['P'], a['N']
                if M is not None:
                    Pv = (np.c_[Pv, np.ones(len(Pv))] @ M.T)[:, :3]
                    R = M[:3, :3]
                    N = N @ np.linalg.inv(R)
                    N = N / np.maximum(1e-9, np.linalg.norm(N, axis=1))[:, None]
                fo.write(f'usemtl {_ids(mat)}\n')
                fo.write(''.join(f'v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n' for p in Pv))
                fo.write(''.join(f'vt {t[0]:.4f} {t[1]:.4f}\n' for t in a['T']))
                fo.write(''.join(f'vn {n[0]:.3f} {n[1]:.3f} {n[2]:.3f}\n' for n in N))
                F = a['F'] + vo
                fo.write(''.join(f'f {i}/{i}/{i} {j}/{j}/{j} {k}/{k}/{k}\n' for i, j, k in F))
                vo += len(Pv)
        for o, parts in P.obj_parts:
            dump(o['name'], parts)
        for inst in S.instances:
            dump(inst['name'], P.def_parts[inst['defname']], inst['M'])


# ------------------------------------------------------------------ GLB
def write_glb(P, path, texdir, max_tex=1024, include_lights=True, skip_layers=()):
    S = P.S
    bin_chunks = []
    bufviews, accessors, meshes, nodes, materials, textures, images, samplers = [], [], [], [], [], [], [], []
    offset = 0

    def add_view(data, target=None):
        nonlocal offset
        pad = (-len(data)) % 4
        data = data + b'\x00' * pad
        bv = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(data) - pad}
        if target:
            bv['target'] = target
        bufviews.append(bv)
        bin_chunks.append(data)
        offset += len(data)
        return len(bufviews) - 1

    def add_acc(arr, comp, typ, target, minmax=False):
        bv = add_view(arr.tobytes(), target)
        acc = {'bufferView': bv, 'componentType': comp, 'count': int(arr.shape[0]), 'type': typ}
        if minmax:
            acc['min'] = arr.min(axis=0).tolist(); acc['max'] = arr.max(axis=0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    tex_index = {}

    def texture(fn, alpha):
        if fn in tex_index:
            return tex_index[fn]
        im = Image.open(os.path.join(texdir, fn))
        im.thumbnail((max_tex, max_tex))
        b = io.BytesIO()
        if alpha:
            im.save(b, 'PNG', optimize=True); mime = 'image/png'
        else:
            im.convert('RGB').save(b, 'JPEG', quality=84); mime = 'image/jpeg'
        bv = add_view(b.getvalue())
        images.append({'bufferView': bv, 'mimeType': mime})
        textures.append({'source': len(images) - 1, 'sampler': 0})
        tex_index[fn] = len(textures) - 1
        return tex_index[fn]

    samplers.append({'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497})
    mat_index = {}
    for name, m in S.materials.items():
        c = m.get('color', (200, 200, 200))
        pbr = {'metallicFactor': 0.9 if m.get('metal') else 0.0,
               'roughnessFactor': float(max(0.08, 1.0 - m.get('gloss', 0.15) * (1.0 if m.get('refl', 0) > 0.05 else 0.4)))}
        mat = {'name': name, 'pbrMetallicRoughness': pbr, 'doubleSided': True}
        if 'tex' in m:
            pbr['baseColorTexture'] = {'index': texture(m['tex'], m.get('alpha', False))}
            pbr['baseColorFactor'] = [1, 1, 1, 1 - m.get('transp', 0.0) * 0.85]
        else:
            pbr['baseColorFactor'] = [c[0] / 255, c[1] / 255, c[2] / 255, 1 - m.get('transp', 0.0) * 0.85]
        if m.get('alpha'):
            mat['alphaMode'] = 'MASK'; mat['alphaCutoff'] = 0.5
        elif 'transp' in m:
            mat['alphaMode'] = 'BLEND'
        if 'emit' in m:
            e = m['emit']
            mat['emissiveFactor'] = [e[0] / 255, e[1] / 255, e[2] / 255]
            mat.setdefault('extensions', {})['KHR_materials_emissive_strength'] = {'emissiveStrength': 6.0}
        materials.append(mat)
        mat_index[name] = len(materials) - 1

    def add_mesh(name, parts):
        prims = []
        for mat, a in parts:
            Pv = a['P'].astype(np.float32)
            # glTF is Y-up: (x, y, z) -> (x, z, -y)
            Pg = np.c_[Pv[:, 0], Pv[:, 2], -Pv[:, 1]].astype(np.float32)
            N = a['N'].astype(np.float32); Ng = np.c_[N[:, 0], N[:, 2], -N[:, 1]].astype(np.float32)
            T = a['T'].astype(np.float32).copy(); T[:, 1] = 1.0 - T[:, 1]
            F = a['F'].astype(np.uint32).ravel()
            prim = {'attributes': {'POSITION': add_acc(Pg, 5126, 'VEC3', 34962, True),
                                   'NORMAL': add_acc(Ng, 5126, 'VEC3', 34962),
                                   'TEXCOORD_0': add_acc(T, 5126, 'VEC2', 34962)},
                    'indices': add_acc(F.reshape(-1, 1), 5125, 'SCALAR', 34963),
                    'material': mat_index[mat]}
            accessors[prim['indices']]['type'] = 'SCALAR'
            prims.append(prim)
        meshes.append({'name': name, 'primitives': prims})
        return len(meshes) - 1

    Zup = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1.0]])  # z-up -> y-up
    root_children = []
    for o, parts in P.obj_parts:
        if any(o['layer'].startswith(s) for s in skip_layers):
            continue
        nodes.append({'name': o['name'], 'mesh': add_mesh(o['name'], parts), 'extras': {'layer': o['layer']}})
        root_children.append(len(nodes) - 1)
    def_mesh = {}
    for inst in S.instances:
        if any(inst['layer'].startswith(s) for s in skip_layers):
            continue
        dn = inst['defname']
        if dn not in def_mesh:
            def_mesh[dn] = add_mesh(dn, P.def_parts[dn])
        M = Zup @ inst['M'] @ np.linalg.inv(Zup)
        nodes.append({'name': inst['name'], 'mesh': def_mesh[dn], 'matrix': M.T.ravel().tolist(), 'extras': {'layer': inst['layer']}})
        root_children.append(len(nodes) - 1)
    ext_used = ['KHR_materials_emissive_strength']
    lights = []
    if include_lights:
        for L in S.lights:
            if L.get('off'):
                continue
            c = [v / 255 for v in L['color']]
            W = L.get('watts', 40)
            pos = np.array(L['pos'], float)
            if L['kind'] == 'linear':
                pos = pos + 0.5 * np.array(L['vec'])
                lt = {'type': 'point', 'color': c, 'intensity': W * 0.9}
            elif L['kind'] == 'point':
                lt = {'type': 'point', 'color': c, 'intensity': W * 1.0}
            else:
                ang = math.radians(L.get('spot_deg', 45) / 2)
                lt = {'type': 'spot', 'color': c, 'intensity': W * 3.0, 'spot': {'outerConeAngle': ang, 'innerConeAngle': ang * L.get('hotspot', 0.5)}}
            lt['name'] = L['name']
            lights.append(lt)
            if 'target' in L:
                d = np.array(L['target'], float) - pos
            else:
                d = np.array(L.get('dir', (0, 0, -1)), float)
            d /= np.linalg.norm(d)
            dg = np.array([d[0], d[2], -d[1]])
            # rotation taking -Z (glTF light dir) to dg
            f0 = np.array([0, 0, -1.0])
            v = np.cross(f0, dg); s = np.linalg.norm(v); cth = np.dot(f0, dg)
            if s < 1e-8:
                q = [0, 0, 0, 1] if cth > 0 else [1, 0, 0, 0]
            else:
                ax = v / s; ang = math.atan2(s, cth)
                q = list(ax * math.sin(ang / 2)) + [math.cos(ang / 2)]
            nodes.append({'name': L['name'], 'translation': [pos[0], pos[2], -pos[1]], 'rotation': q,
                          'extensions': {'KHR_lights_punctual': {'light': len(lights) - 1}}, 'extras': {'layer': L['layer']}})
            root_children.append(len(nodes) - 1)
        ext_used.append('KHR_lights_punctual')
    nodes.append({'name': 'St_Johann_von_Capistran', 'children': root_children})
    gltf = {'asset': {'version': '2.0', 'generator': 'capistran-3d'},
            'scene': 0, 'scenes': [{'nodes': [len(nodes) - 1]}], 'nodes': nodes, 'meshes': meshes,
            'materials': materials, 'textures': textures, 'images': images, 'samplers': samplers,
            'accessors': accessors, 'bufferViews': bufviews, 'buffers': [{'byteLength': offset}],
            'extensionsUsed': ext_used}
    if lights:
        gltf['extensions'] = {'KHR_lights_punctual': {'lights': lights}}
    js = json.dumps(gltf, separators=(',', ':')).encode()
    js += b' ' * ((-len(js)) % 4)
    binb = b''.join(bin_chunks)
    total = 12 + 8 + len(js) + 8 + len(binb)
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<III', 0x46546C67, 2, total))
        fh.write(struct.pack('<II', len(js), 0x4E4F534A)); fh.write(js)
        fh.write(struct.pack('<II', len(binb), 0x004E4942)); fh.write(binb)

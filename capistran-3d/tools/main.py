"""Generate the St. Johann von Capistran model package.

usage: python3 tools/main.py [--retex] [--no-obj]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import textures  # noqa: E402
from build import build_scene  # noqa: E402
from exporters import Prepared, write_3dm, write_dae, write_obj, write_glb  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'output')
TEX = os.path.join(OUT, 'textures')
NAME = 'St_Johann_von_Capistran_Muenchen'

TILES = {
    'brick': (2.25, 2.106), 'brick_unjointed': (2.25, 2.106), 'brick_screen': (1.5, 1.944),
    'clinker': (1.476, 1.736), 'wood_slat': (0.12, 2.4), 'wood_bench': (1.0, 1.0), 'wood_dark': (1.0, 1.0),
    'alu': (2.4, 0.6), 'nagelfluh': (1.0, 1.0), 'concrete': (2.0, 2.0), 'hex': (1.44, 0.831384387633061),
    'grasspaver': (1.2, 1.2), 'lawn': (4.0, 4.0), 'asphalt': (4.0, 4.0), 'honeycomb': (0.8, 0.8),
    'bark': (0.6, 1.2), 'foliage': (2.0, 2.0),
}


def main():
    t0 = time.time()
    if '--retex' in sys.argv or not os.path.exists(os.path.join(TEX, 'brick_hardfired.png')):
        textures.generate_all(TEX)
    S = build_scene(TILES)
    print(f'scene built {time.time() - t0:.1f}s')
    P = Prepared(S)
    st = P.stats()
    print(json.dumps(st, indent=1), f'{time.time() - t0:.1f}s')
    write_3dm(P, os.path.join(OUT, NAME + '.3dm'))
    print(f'3dm {time.time() - t0:.1f}s')
    write_dae(P, os.path.join(OUT, NAME + '_SketchUp.dae'))
    print(f'dae {time.time() - t0:.1f}s')
    write_glb(P, os.path.join(OUT, NAME + '.glb'), TEX)
    print(f'glb {time.time() - t0:.1f}s')
    if '--no-obj' not in sys.argv:
        write_obj(P, os.path.join(OUT, NAME + '.obj'))
        print(f'obj {time.time() - t0:.1f}s')
    with open(os.path.join(OUT, 'model_stats.json'), 'w') as fh:
        json.dump(st, fh, indent=1)
    with open(os.path.join(OUT, 'lights_schedule.csv'), 'w', encoding='utf-8') as fh:
        fh.write('name,layer,type,x,y,z,dir_or_target,color_rgb,watts,spot_deg,enabled\n')
        for L in S.lights:
            d = L.get('target', L.get('dir', L.get('vec', '')))
            fh.write(f'{L["name"]},{L["layer"]},{L["kind"]},{L["pos"][0]:.3f},{L["pos"][1]:.3f},{L["pos"][2]:.3f},'
                     f'"{tuple(round(v, 3) for v in d) if d != "" else ""}","{L["color"]}",{L.get("watts", "")},{L.get("spot_deg", "")},{not L.get("off", False)}\n')
    with open(os.path.join(OUT, 'named_views.json'), 'w', encoding='utf-8') as fh:
        json.dump(S.views, fh, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()

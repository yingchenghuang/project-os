"""Procedural, tileable textures for St. Johann von Capistran (Sep Ruf, 1960).

Every texture is generated from numpy noise so the whole package is
self-contained and license-free. Each entry records the real-world size
(in metres) one tile represents; the exporters scale UVs accordingly.
"""
import os
import numpy as np
from PIL import Image, ImageFilter

RNG = np.random.default_rng(1960)


# ---------------------------------------------------------------- helpers
def _tile_noise(h, w, scale, rng, octaves=4, persistence=0.5):
    """Tileable value noise (bilinear, wrap-around) in [0,1]."""
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh = max(2, int(scale * (2 ** o)))
        gw = max(2, int(scale * (2 ** o) * w / h))
        g = rng.random((gh, gw))
        ys = np.linspace(0, gh, h, endpoint=False)
        xs = np.linspace(0, gw, w, endpoint=False)
        y0 = np.floor(ys).astype(int); x0 = np.floor(xs).astype(int)
        fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
        fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
        y1 = (y0 + 1) % gh; x1 = (x0 + 1) % gw
        a = g[y0][:, x0]; b = g[y0][:, x1]; c = g[y1][:, x0]; d = g[y1][:, x1]
        out += amp * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)
        tot += amp
        amp *= persistence
    return out / tot


def _save(img, path):
    img = np.clip(img, 0, 255).astype(np.uint8)
    Image.fromarray(img).save(path, optimize=True)


def _bump_from_height(height):
    h = (height - height.min()) / max(1e-6, (height.max() - height.min()))
    return np.stack([h * 255] * 3, -1)


# ---------------------------------------------------------------- brick
BRICK_PALETTE = np.array([
    [128, 50, 44], [112, 42, 40], [140, 58, 46], [96, 38, 40], [84, 34, 40],
    [150, 72, 52], [70, 34, 40], [120, 52, 46], [104, 46, 44], [58, 30, 36],
    [134, 64, 50], [92, 44, 46], [76, 40, 46], [118, 44, 50],
], float)


def brick_wall(path, bump_path, px_per_m=900, unjointed=False, rng=RNG):
    """Hard-fired Munich facing brick, NF 240x115x71 + 10 mm joints.

    Tile = 9 stretchers x 26 courses -> 2.25 m x 2.10 m (exactly periodic).
    """
    bl, bh, j = 0.240, 0.071, 0.010
    nx, ny = 9, 26
    tw, th = nx * (bl + j), ny * (bh + j)
    W, H = int(tw * px_per_m), int(th * px_per_m)
    yy, xx = np.mgrid[0:H, 0:W]
    ym = yy / px_per_m; xm = xx / px_per_m
    course = np.floor(ym / (bh + j)).astype(int)
    off = np.where(course % 2 == 0, 0.0, (bl + j) / 2)
    xs = (xm + off) % tw
    col = np.floor(xs / (bl + j)).astype(int)
    lx = xs - col * (bl + j); ly = ym - course * (bh + j)
    mortar = (lx > bl) | (ly > bh)
    bid = (course * 31 + col * 17) % 9973
    lut = rng.integers(0, len(BRICK_PALETTE), 9973)
    base = BRICK_PALETTE[lut[bid]]
    tone = (rng.random(9973) * 0.25 + 0.88)[bid][..., None]
    n1 = _tile_noise(H, W, 6, rng)[..., None]
    n2 = _tile_noise(H, W, 40, rng, octaves=3)[..., None]
    img = base * tone * (0.82 + 0.3 * n1) * (0.9 + 0.2 * n2)
    # sintered dark heads on some bricks (Kohlebrand)
    burn = (rng.random(9973) < 0.18)[bid]
    edge = np.minimum(lx, np.maximum(0, bl - lx)) / bl
    burnmask = burn & (edge < 0.18) & ~mortar
    img[burnmask] *= 0.62
    height = np.where(mortar, 0.0, 1.0) * (0.85 + 0.15 * n2[..., 0])
    if unjointed:
        # absorber panels: open (dark) head joints, no mortar
        img[mortar] = np.array([30, 22, 22]) * (0.8 + 0.4 * n1[mortar])
        height = np.where(mortar, -0.5, height)
    else:
        mcol = np.array([92, 88, 84]) * (0.85 + 0.3 * n2)
        img = np.where(mortar[..., None], mcol, img)
    # chamfer shading
    sh = np.clip(np.minimum(lx, bl - lx) / 0.004, 0, 1) * np.clip(np.minimum(ly, bh - ly) / 0.004, 0, 1)
    img = np.where(mortar[..., None], img, img * (0.8 + 0.2 * sh[..., None]))
    _save(img, path)
    _save(_bump_from_height(height + 0.1 * sh), bump_path)
    return (tw, th)


def brick_screen(path, px_per_m=700, rng=RNG):
    """Steingitter: perforated brick lattice with see-through slots (RGBA)."""
    cell_w, cell_h = 0.25, 0.162  # brick + slot, two courses
    nx, ny = 6, 12
    tw, th = nx * cell_w, ny * cell_h
    W, H = int(tw * px_per_m), int(th * px_per_m)
    yy, xx = np.mgrid[0:H, 0:W]
    ym = yy / px_per_m; xm = xx / px_per_m
    row = np.floor(ym / cell_h).astype(int)
    xs = (xm + np.where(row % 2 == 0, 0, cell_w / 2)) % tw
    col = np.floor(xs / cell_w).astype(int)
    lx = xs - col * cell_w; ly = ym - row * cell_h
    hole = (lx > 0.16) & (lx < 0.235) & (ly > 0.012) & (ly < 0.150)
    # brick courses inside the solid part
    cy = ly % 0.081
    joint = (cy > 0.071) | (lx < 0.006)
    bid = (row * 13 + col * 7 + (ly > 0.081)) % 997
    lut = rng.integers(0, len(BRICK_PALETTE), 997)
    base = BRICK_PALETTE[lut[bid]] * (0.85 + 0.3 * _tile_noise(H, W, 8, rng)[..., None])
    base = np.where(joint[..., None], np.array([104, 98, 92]), base)
    alpha = np.where(hole, 0, 255)
    img = np.dstack([base, alpha])
    _save(img, path)
    return (tw, th)


def clinker_floor(path, bump_path, px_per_m=700, rng=RNG):
    """Warm-red clinker pavers 240x118, laid in running bond."""
    bl, bw, j = 0.240, 0.118, 0.006
    nx, ny = 6, 14
    tw, th = nx * (bl + j), ny * (bw + j)
    W, H = int(tw * px_per_m), int(th * px_per_m)
    yy, xx = np.mgrid[0:H, 0:W]
    ym = yy / px_per_m; xm = xx / px_per_m
    row = np.floor(ym / (bw + j)).astype(int)
    xs = (xm + np.where(row % 2 == 0, 0, (bl + j) / 2)) % tw
    col = np.floor(xs / (bl + j)).astype(int)
    lx = xs - col * (bl + j); ly = ym - row * (bw + j)
    joint = (lx > bl) | (ly > bw)
    pal = np.array([[150, 62, 44], [138, 56, 42], [162, 74, 52], [126, 52, 42], [144, 66, 50], [118, 48, 40]], float)
    bid = (row * 29 + col * 11) % 4999
    base = pal[rng.integers(0, len(pal), 4999)[bid]]
    n = _tile_noise(H, W, 10, rng)[..., None]
    wear = _tile_noise(H, W, 3, rng)[..., None]
    img = base * (0.85 + 0.25 * n) * (0.9 + 0.15 * wear)
    img = np.where(joint[..., None], np.array([92, 86, 80]), img)
    _save(img, path)
    _save(_bump_from_height(np.where(joint, 0, 1.0) + 0.05 * n[..., 0]), bump_path)
    return (tw, th)


# ---------------------------------------------------------------- wood
def wood(path, px=(512, 2048), size=(0.12, 2.4), tint=(214, 176, 128), dark=False, rng=RNG):
    """Long-grain wood (u across, v along the grain)."""
    W, H = px
    yy, xx = np.mgrid[0:H, 0:W]
    n = _tile_noise(H, W, 3, rng, octaves=5)
    rings = np.sin((xx / W * 14 + n * 6) * np.pi) * 0.5 + 0.5
    fine = _tile_noise(H, W, 80, rng, octaves=2)
    t = np.array(tint, float)
    img = t * (0.78 + 0.16 * rings[..., None] + 0.1 * fine[..., None])
    if dark:
        img *= 0.42
    _save(img, path)
    return size


def slat_soffit(path, n_slats=8, dark=True, rng=RNG):
    """Radial slat soffit: stripes across u (mapped by angle)."""
    W, H = 1024, 512
    yy, xx = np.mgrid[0:H, 0:W]
    per = W / n_slats
    lx = (xx % per) / per
    gap = lx > 0.72
    n = _tile_noise(H, W, 4, rng)
    base = np.array([92, 66, 46] if dark else [200, 160, 112], float)
    img = base * (0.8 + 0.35 * n[..., None])
    img = np.where(gap[..., None], np.array([16, 12, 10]), img)
    _save(img, path)


def copper_roof(path, bump_path, rng=RNG):
    """Aged copper with standing seams (u = angular, stripes radial)."""
    W, H = 1024, 1024
    yy, xx = np.mgrid[0:H, 0:W]
    per = W / 8
    lx = (xx % per) / per
    seam = np.abs(lx - 0.5) < 0.025
    n = _tile_noise(H, W, 5, rng, octaves=5)
    pat = _tile_noise(H, W, 18, rng, octaves=3)
    brown = np.array([96, 62, 44]); green = np.array([88, 132, 112])
    mix = np.clip((pat - 0.55) * 3, 0, 1)[..., None] * 0.55
    img = (brown * (1 - mix) + green * mix) * (0.75 + 0.45 * n[..., None])
    img = np.where(seam[..., None], img * 1.25, img)
    _save(img, path)
    _save(_bump_from_height(np.where(seam, 1.0, 0.0) + 0.1 * n), bump_path)


def alu_fascia(path, bump_path, rng=RNG):
    """Riveted aluminium cornice (Aluminiumgesims), panels 1.2 m."""
    W, H = 2048, 512   # 2.4 m x 0.6 m
    yy, xx = np.mgrid[0:H, 0:W]
    xm = xx / W * 2.4; ym = yy / H * 0.6
    brushed = _tile_noise(H, W, 2, rng)[..., None] * 0.1 + _tile_noise(H, W, 200, rng, 1)[..., None] * 0.05
    img = np.array([178, 182, 186]) * (0.9 + brushed)
    joint = (np.abs((xm % 1.2) - 0.6) > 0.597)
    rv = np.zeros_like(xm, bool)
    for yr in (0.05, 0.55):
        d = np.hypot(((xm + 0.05) % 0.2) - 0.1, ym - yr)
        rv |= d < 0.008
    img = np.where(joint[..., None], np.array([60, 62, 64]), img)
    img = np.where(rv[..., None], img * 0.75, img)
    _save(img, path)
    _save(_bump_from_height(rv * 1.0 - joint * 1.0), bump_path)
    return (2.4, 0.6)


# ---------------------------------------------------------------- stone
def nagelfluh(path, bump_path, rng=RNG):
    """Nagelfluh conglomerate (altar block): pebbles in calcareous matrix."""
    W = H = 1024  # 1 m
    img = np.zeros((H, W, 3)) + np.array([196, 186, 166])
    height = np.zeros((H, W))
    n = _tile_noise(H, W, 12, rng)
    img *= (0.85 + 0.25 * n)[..., None]
    yy, xx = np.mgrid[0:H, 0:W]
    pebble_cols = np.array([[150, 146, 140], [120, 112, 104], [176, 168, 150], [96, 92, 90],
                            [168, 140, 110], [200, 196, 186], [130, 120, 96], [80, 76, 74]], float)
    for _ in range(900):
        cx, cy = rng.random() * W, rng.random() * H
        r = rng.choice([6, 9, 12, 16, 22, 30, 40], p=[.25, .22, .18, .14, .1, .07, .04]) * (0.7 + rng.random() * 0.6)
        ex = 0.6 + rng.random() * 0.4; ang = rng.random() * np.pi
        for ox in (-W, 0, W):
            for oy in (-H, 0, H):
                x0, x1 = int(max(0, cx + ox - r - 2)), int(min(W, cx + ox + r + 2))
                y0, y1 = int(max(0, cy + oy - r - 2)), int(min(H, cy + oy + r + 2))
                if x0 >= x1 or y0 >= y1:
                    continue
                dx = xx[y0:y1, x0:x1] - (cx + ox); dy = yy[y0:y1, x0:x1] - (cy + oy)
                u = dx * np.cos(ang) + dy * np.sin(ang); v = (-dx * np.sin(ang) + dy * np.cos(ang)) / ex
                d = np.sqrt(u * u + v * v) / r
                m = d < 1
                c = pebble_cols[rng.integers(len(pebble_cols))] * (0.85 + rng.random() * 0.3)
                shade = (1.08 - 0.25 * d)[..., None]
                img[y0:y1, x0:x1][m] = (c * shade)[m]
                height[y0:y1, x0:x1][m] = np.maximum(height[y0:y1, x0:x1][m], np.sqrt(np.clip(1 - d[m] ** 2, 0, 1)))
    _save(img, path)
    _save(_bump_from_height(height + 0.15 * n), bump_path)
    return (1.0, 1.0)


def concrete_board(path, bump_path, rng=RNG):
    """Board-formed concrete (Glockenwand)."""
    W, H = 1024, 1024  # 2 m
    yy, xx = np.mgrid[0:H, 0:W]
    n = _tile_noise(H, W, 6, rng, octaves=5)
    board = np.floor(yy / (H / 14)).astype(int)
    shade = (rng.random(14) * 0.12 + 0.94)[board]
    grain = _tile_noise(H, W, 30, rng, 2) * 0.08
    img = np.array([150, 148, 142]) * (shade * (0.85 + 0.25 * n) + grain)[..., None]
    seam = (yy % (H / 14)) < 2
    img = np.where(seam[..., None], img * 0.7, img)
    _save(img, path)
    _save(_bump_from_height(n * 0.3 - seam * 1.0), bump_path)
    return (2.0, 2.0)


def hex_pavers(path, bump_path, rng=RNG):
    """Beige concrete hexagon pavers (present-day circuitus)."""
    s = 0.12  # circumradius in m
    tw, th = 3 * s * 4, np.sqrt(3) * s * 4
    W = 1200; H = int(W * th / tw)
    yy, xx = np.mgrid[0:H, 0:W]
    xm = xx / W * tw; ym = yy / H * th
    best = np.full(xm.shape, 9.0); idx = np.zeros(xm.shape, int)
    k = 0
    for i in range(-1, 9):
        for jj in range(-1, 9):
            cx = i * 1.5 * s
            cy = jj * np.sqrt(3) * s + (np.sqrt(3) / 2 * s if i % 2 else 0)
            for ox in (-tw, 0, tw):
                for oy in (-th, 0, th):
                    d = np.hypot(xm - cx - ox, ym - cy - oy)
                    m = d < best
                    best[m] = d[m]; idx[m] = ((i % 8) * 8 + (jj % 4))
            k += 1
    # edge detection on idx
    e = np.zeros_like(best, bool)
    e[:-2, :] |= idx[:-2, :] != idx[2:, :]
    e[:, :-2] |= idx[:, :-2] != idx[:, 2:]
    tone = (rng.random(64) * 0.14 + 0.93)[idx]
    n = _tile_noise(H, W, 14, rng)
    img = np.array([196, 186, 168]) * (tone * (0.85 + 0.25 * n))[..., None]
    img = np.where(e[..., None], np.array([110, 104, 94]), img)
    _save(img, path)
    _save(_bump_from_height((~e) * 1.0 + 0.1 * n), bump_path)
    return (tw, th)


def grass_pavers(path, rng=RNG):
    """Rasengittersteine: concrete grid with grass (foreground in photos)."""
    W, H = 1024, 1024  # 1.2 x 1.2 m
    yy, xx = np.mgrid[0:H, 0:W]
    xm = xx / W * 1.2; ym = yy / H * 1.2
    cx = xm % 0.2; cy = ym % 0.2
    grass = (cx > 0.03) & (cx < 0.17) & (cy > 0.03) & (cy < 0.17)
    n = _tile_noise(H, W, 40, rng, 3)
    g = np.array([70, 112, 46]) * (0.7 + 0.6 * n)[..., None]
    c = np.array([150, 146, 138]) * (0.85 + 0.2 * _tile_noise(H, W, 8, rng))[..., None]
    _save(np.where(grass[..., None], g, c), path)
    return (1.2, 1.2)


def lawn(path, rng=RNG):
    W = H = 1024  # 4 m
    n1 = _tile_noise(H, W, 4, rng)
    n2 = _tile_noise(H, W, 120, rng, 2)
    img = np.array([74, 116, 48]) * (0.7 + 0.35 * n1 + 0.25 * n2)[..., None]
    img[..., 0] += 20 * (n1 - 0.5)
    _save(img, path)
    return (4.0, 4.0)


def asphalt(path, rng=RNG):
    W = H = 1024
    n = _tile_noise(H, W, 160, rng, 2); m = _tile_noise(H, W, 5, rng)
    img = np.array([70, 70, 72]) * (0.8 + 0.3 * n + 0.15 * m)[..., None]
    _save(img, path)
    return (4.0, 4.0)


def bronze_relief(path, bump_path, rng=RNG):
    """Abstract bronze door relief (after H. Kirchner's 6 panels)."""
    W, H = 512, 1024  # one leaf 1.3 x 3.6 m -> mapped 0..1
    yy, xx = np.mgrid[0:H, 0:W]
    height = _tile_noise(H, W, 4, rng, 5) * 0.4
    for panel in range(3):
        y0 = H * (0.08 + panel * 0.3)
        for _ in range(7):  # stick-figure-like strokes
            x0 = W * (0.2 + rng.random() * 0.6); ya = y0 + rng.random() * H * 0.22
            ang = rng.random() * np.pi; L = 40 + rng.random() * 90
            for t in np.linspace(0, 1, 40):
                px = x0 + np.cos(ang) * L * t; py = ya + np.sin(ang) * L * t
                d = np.hypot(xx - px, yy - py)
                height = np.maximum(height, np.clip(1 - d / 9, 0, 1))
        frame = (np.abs(yy - (y0 - H * 0.03)) < 4)
        height[frame] = 0.9
    patina = _tile_noise(H, W, 10, rng)
    base = np.array([58, 48, 36]) * (0.7 + 0.5 * height)[..., None]
    green = np.array([70, 96, 80])
    img = base + (green - base) * (np.clip(patina - 0.6, 0, 1) * 1.2)[..., None] * (1 - height[..., None])
    _save(img, path)
    _save(_bump_from_height(height), bump_path)


def stained_glass(path, rng=RNG):
    """Abstraction of J. Oberberger's 'Wurzel Jesse' window: dense coloured
    leaded panes below, branching tree, radiant white Madonna zone above."""
    W, H = 512, 1536  # 4 m x 12 m bay -> UV 0..1
    yy, xx = np.mgrid[0:H, 0:W]
    pts = rng.random((900, 2)) * [W, H]
    # Voronoi via coarse grid search
    gx, gy = 16, 48
    cell = np.zeros((H, W), int); best = np.full((H, W), 1e9)
    for i, (px, py) in enumerate(pts):
        x0, x1 = int(max(0, px - 60)), int(min(W, px + 60)); y0, y1 = int(max(0, py - 60)), int(min(H, py + 60))
        d = (xx[y0:y1, x0:x1] - px) ** 2 + (yy[y0:y1, x0:x1] - py) ** 2
        sub = best[y0:y1, x0:x1]; m = d < sub
        sub[m] = d[m]; cell[y0:y1, x0:x1][m] = i
    lead = np.zeros((H, W), bool)
    lead[:-1, :] |= cell[:-1, :] != cell[1:, :]
    lead[:, :-1] |= cell[:, :-1] != cell[:, 1:]
    lead = np.array(Image.fromarray(lead.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))) > 0
    hgt = 1 - pts[:, 1] / H  # 1 at top
    pal_low = np.array([[30, 50, 140], [140, 24, 30], [190, 140, 30], [20, 90, 70], [90, 30, 110], [40, 90, 170]], float)
    cols = pal_low[rng.integers(0, len(pal_low), len(pts))]
    white = np.array([238, 236, 226], float)
    tw = np.clip((hgt - 0.55) / 0.3, 0, 1)[:, None]
    # tree trunk & branches -> golden
    xc = np.abs(pts[:, 0] - W / 2)
    branch = (xc < 26 + 140 * np.clip(hgt - 0.15, 0, 1) * (np.sin(hgt * 30) > 0.3)) & (hgt < 0.75)
    cols[branch] = [214, 168, 60]
    cols = cols * (1 - tw) + white * tw
    # Christ on throne at the very top, small golden halo
    img = cols[cell] * (0.85 + 0.3 * rng.random(len(pts)))[cell][..., None]
    halo = np.hypot(xx - W / 2, yy - H * 0.08) < 45
    img[halo] = [236, 200, 90]
    img[lead] = [28, 28, 30]
    # mullion grid of the panel frames
    img[(xx % (W // 4)) < 3] = [40, 40, 44]
    img[(yy % (H // 12)) < 3] = [40, 40, 44]
    _save(img, path)


def honeycomb_wall(path, rng=RNG):
    """Betonwabenstein wall with cast glass (parish hall east face)."""
    W, H = 512, 512  # 0.8 m
    yy, xx = np.mgrid[0:H, 0:W]
    cx = (xx % 128) - 64; cy = (yy % 128) - 64
    d = np.maximum(np.abs(cx) * 0.866 + np.abs(cy) * 0.5, np.abs(cy))
    glass = d < 50
    img = np.where(glass[..., None], np.array([150, 176, 170]), np.array([170, 166, 158]))
    img = img * (0.85 + 0.3 * _tile_noise(H, W, 8, rng))[..., None]
    _save(img, path)
    return (0.8, 0.8)


def bark(path, rng=RNG):
    W, H = 256, 512
    n = _tile_noise(H, W, 6, rng, 5)
    yy, xx = np.mgrid[0:H, 0:W]
    ridges = (np.sin(xx / W * 40 + n * 8) * 0.5 + 0.5)
    img = np.array([88, 76, 64]) * (0.6 + 0.5 * ridges * n)[..., None]
    _save(img, path)
    return (0.6, 1.2)


def foliage(path, rng=RNG):
    W = H = 512
    n = _tile_noise(H, W, 30, rng, 4)
    m = _tile_noise(H, W, 4, rng)
    img = np.array([58, 96, 40]) * (0.55 + 0.7 * n * (0.7 + 0.5 * m))[..., None]
    _save(img, path)
    return (2.0, 2.0)


def frosted(path, rng=RNG):
    """Plexiglas dome: milky with faint radial ribs."""
    W, H = 512, 512
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.array([240, 242, 244]) * (0.95 + 0.05 * _tile_noise(H, W, 4, rng))[..., None]
    _save(img, path)


def generate_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    p = lambda n: os.path.join(outdir, n)
    tiles = {}
    tiles['brick'] = brick_wall(p('brick_hardfired.png'), p('brick_hardfired_bump.png'))
    tiles['brick_unjointed'] = brick_wall(p('brick_unjointed.png'), p('brick_unjointed_bump.png'), unjointed=True)
    tiles['brick_screen'] = brick_screen(p('brick_screen_alpha.png'))
    tiles['clinker'] = clinker_floor(p('clinker_floor.png'), p('clinker_floor_bump.png'))
    tiles['wood_slat'] = wood(p('wood_spruce_slat.png'), tint=(190, 142, 98))
    tiles['wood_bench'] = wood(p('wood_ash_bench.png'), px=(1024, 1024), size=(1.0, 1.0), tint=(222, 192, 146))
    tiles['wood_dark'] = wood(p('wood_dark_stain.png'), px=(1024, 1024), size=(1.0, 1.0), tint=(150, 110, 80), dark=True)
    slat_soffit(p('soffit_slats_dark.png'))
    slat_soffit(p('ceiling_backing.png'), n_slats=8, dark=True)
    copper_roof(p('copper_roof.png'), p('copper_roof_bump.png'))
    tiles['alu'] = alu_fascia(p('alu_fascia.png'), p('alu_fascia_bump.png'))
    tiles['nagelfluh'] = nagelfluh(p('nagelfluh.png'), p('nagelfluh_bump.png'))
    tiles['concrete'] = concrete_board(p('concrete_board.png'), p('concrete_board_bump.png'))
    tiles['hex'] = hex_pavers(p('hex_pavers.png'), p('hex_pavers_bump.png'))
    tiles['grasspaver'] = grass_pavers(p('grass_pavers.png'))
    tiles['lawn'] = lawn(p('lawn.png'))
    tiles['asphalt'] = asphalt(p('asphalt.png'))
    bronze_relief(p('bronze_door_relief.png'), p('bronze_door_relief_bump.png'))
    stained_glass(p('stained_glass_oberberger.png'))
    tiles['honeycomb'] = honeycomb_wall(p('honeycomb_concrete_glass.png'))
    tiles['bark'] = bark(p('bark.png'))
    tiles['foliage'] = foliage(p('foliage.png'))
    frosted(p('plexiglas_frosted.png'))
    return tiles


if __name__ == '__main__':
    import sys, json
    t = generate_all(sys.argv[1])
    print(json.dumps(t, indent=1))

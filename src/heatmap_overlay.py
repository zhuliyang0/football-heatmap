# -*- coding: utf-8 -*-
"""把 KDE 热力图渲染成与经纬度对齐（正北朝上）的贴图，供卫星底图叠加。"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM
from heatmap_kde import clean_to_pitch, kde_grid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
STOPS = [(0.00, (11, 13, 46)), (0.12, (26, 41, 107)), (0.26, (51, 89, 133)), (0.40, (56, 140, 107)),
         (0.52, (140, 184, 51)), (0.62, (235, 209, 31)), (0.74, (252, 158, 26)), (0.86, (252, 87, 15)),
         (1.00, (199, 5, 13))]


def turbo_rgb(t):
    t = np.clip(t, 0.0, 1.0)
    out = np.zeros(t.shape + (3,), dtype=float)
    for (t0, c0), (t1, c1) in zip(STOPS[:-1], STOPS[1:]):
        m = (t >= t0) & (t <= t1)
        if not m.any():
            continue
        k = (t[m] - t0) / max(t1 - t0, 1e-9)
        for i in range(3):
            out[m, i] = c0[i] + (c1[i] - c0[i]) * k
    out[t > STOPS[-1][0]] = STOPS[-1][1]
    return out


def bilinear(grid, gx, gy):
    """在 KDE 网格上做双线性采样，gx/gy 为网格下标（可为小数）。"""
    nx, ny = grid.shape
    gx = np.clip(gx, 0, nx - 1.001)
    gy = np.clip(gy, 0, ny - 1.001)
    x0 = np.floor(gx).astype(int)
    y0 = np.floor(gy).astype(int)
    fx = gx - x0
    fy = gy - y0
    g00 = grid[x0, y0]
    g10 = grid[x0 + 1, y0]
    g01 = grid[x0, y0 + 1]
    g11 = grid[x0 + 1, y0 + 1]
    return (g00 * (1 - fx) * (1 - fy) + g10 * fx * (1 - fy) + g01 * (1 - fx) * fy + g11 * fx * fy)


def build(stem=STEM, px_per_m: float = 6.0, sigma_m: float = 4.0):
    from heatmap_kde import clean_to_pitch
    trk, laps, fld, u0, w0, v_kmh, dt, scale, offs = load_all(stem)
    W, H = fld.bounds
    cfg = fc.match_window_config(ROOT / 'data' / 'raw', stem)
    lat_j, lon_j = fc.jitter_gps(trk.lat, trk.lon)
    uj, wj = fld.to_field(lat_j, lon_j)
    in_pitch, clean_stats = clean_to_pitch(uj, wj, dt, W, H)
    # 地理贴图必须用真实坐标（不换边镜像），否则叠加到卫星图上的位置是错的
    inside = in_pitch & fc.match_mask(trk.tsec, cfg)
    res = kde_grid(uj, wj, dt, W, H, inside, sigma_m=sigma_m, cell_m=1.0)

    corners = np.array([[c[0], c[1]] for c in fld.corners])
    # 注：热力网格使用进攻方向归一化坐标；叠加贴图按场地几何绘制，因此下半场镜像只影响统计不影响几何
    lat_min, lat_max = float(corners[:, 0].min()), float(corners[:, 0].max())
    lon_min, lon_max = float(corners[:, 1].min()), float(corners[:, 1].max())
    pad_m = 2.0
    dlat = pad_m / fc.M_PER_DEG_LAT
    dlon = pad_m / (fc.M_PER_DEG_LON * np.cos(np.radians(float(corners[:, 0].mean()))))
    lat_min, lat_max = lat_min - dlat, lat_max + dlat
    lon_min, lon_max = lon_min - dlon, lon_max + dlon
    height_m = (lat_max - lat_min) * fc.M_PER_DEG_LAT
    width_m = (lon_max - lon_min) * fc.M_PER_DEG_LON * np.cos(np.radians(float(corners[:, 0].mean())))
    nx, ny = int(round(width_m * px_per_m)), int(round(height_m * px_per_m))
    lons = np.linspace(lon_min, lon_max, nx)
    lats = np.linspace(lat_max, lat_min, ny)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    ug, wg = fld.to_field(lat_grid.ravel(), lon_grid.ravel())
    density = bilinear(res.grid, ug / res.cell_m, wg / res.cell_m).reshape(ny, nx)
    scale_max = float(np.percentile(res.grid, 99.5))
    tnorm = np.clip(density / max(scale_max, 1e-9), 0.0, 1.0)
    rgb = turbo_rgb(tnorm)
    # 低密度区完全透明：把噪声级的密度裁掉，只显示真实停留区域（与官方热图一致）
    lo = 0.14
    alpha = np.clip((tnorm - lo) / (1.0 - lo), 0.0, 1.0) ** 0.8 * 255.0
    rgba = np.dstack([rgb, alpha]).astype(np.uint8)
    img = Image.fromarray(rgba, mode='RGBA')

    draw = ImageDraw.Draw(img)
    def to_px(pts):
        latv = np.array([p[0] for p in pts])
        lonv = np.array([p[1] for p in pts])
        x = (lonv - lon_min) / (lon_max - lon_min) * (nx - 1)
        y = (lat_max - latv) / (lat_max - lat_min) * (ny - 1)
        return list(zip(x.tolist(), y.tolist()))

    def field_line(p0, p1, color=(255, 255, 255, 210), width=2):
        lats_pts = np.linspace(p0[0], p1[0], 24)
        lons_pts = np.linspace(p0[1], p1[1], 24)
        uv = fld.to_field(lats_pts, lons_pts)
        latlon = []
        for i in range(len(lats_pts)):
            latlon.append((lats_pts[i], lons_pts[i]))
        draw.line(to_px(latlon), fill=color, width=width)

    amp = 0.35
    def corner_at(fx_, fy_):
        return fc.Field.to_field(fld, 0, 0)
    def fl_to_latlon(xf, yf):
        cx, cy, ex, ey, fxx, fyy = fld._c
        dx = (xf - fld.long_side_m / 2.0)
        dy = (yf - fld.short_side_m / 2.0)
        X = cx + dx * fxx + dy * ex
        Y = cy + dx * fyy + dy * ey
        return (fld.lat0 + Y / fc.M_PER_DEG_LAT, fld.lon0 + X / (fc.M_PER_DEG_LON * np.cos(np.radians(fld.lat0))))

    def fdraw(p0, p1, width=2):
        n = 20
        pts = [fl_to_latlon(p0[0] + (p1[0] - p0[0]) * t / n, p0[1] + (p1[1] - p0[1]) * t / n) for t in range(n + 1)]
        draw.line(to_px(pts), fill=(255, 255, 255, 235), width=width)

    fdraw((0, 0), (W, 0), 3)
    fdraw((W, 0), (W, H), 3)
    fdraw((W, H), (0, H), 3)
    fdraw((0, H), (0, 0), 3)
    fdraw((W / 2, 0), (W / 2, H), 2)
    fdraw((0, H / 2 - 20.15), (16.5, H / 2 - 20.15), 2)
    fdraw((16.5, H / 2 - 20.15), (16.5, H / 2 + 20.15), 2)
    fdraw((16.5, H / 2 + 20.15), (0, H / 2 + 20.15), 2)
    fdraw((W, H / 2 - 20.15), (W - 16.5, H / 2 - 20.15), 2)
    fdraw((W - 16.5, H / 2 - 20.15), (W - 16.5, H / 2 + 20.15), 2)
    fdraw((W - 16.5, H / 2 + 20.15), (W, H / 2 + 20.15), 2)
    fdraw((0, H / 2 - 9.16), (5.5, H / 2 - 9.16), 2)
    fdraw((5.5, H / 2 - 9.16), (5.5, H / 2 + 9.16), 2)
    fdraw((5.5, H / 2 + 9.16), (0, H / 2 + 9.16), 2)
    fdraw((W, H / 2 - 9.16), (W - 5.5, H / 2 - 9.16), 2)
    fdraw((W - 5.5, H / 2 - 9.16), (W - 5.5, H / 2 + 9.16), 2)
    fdraw((W - 5.5, H / 2 + 9.16), (W, H / 2 + 9.16), 2)

    out_png = OUT / 'heat_overlay.png'
    img.save(out_png)
    meta = {
        'bounds': [[lat_min, lon_min], [lat_max, lon_max]],
        'png': out_png.name,
        'px': [nx, ny], 'px_per_m': px_per_m,
        'sigma_m': sigma_m, 'cell_m': res.cell_m,
        'scale_max_s_per_m2': scale_max,
        'kept_minutes': round(res.stats['total_s'] / 60.0, 1),
        'dropped_minutes': clean_stats['minutes_dropped'],
    }
    (OUT / 'heat_overlay.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[叠加贴图]', out_png.name, nx, 'x', ny, 'px |', round(width_m, 1), 'x', round(height_m, 1), 'm |',
          '保留', meta['kept_minutes'], 'min | 剔场外', meta['dropped_minutes'], 'min')
    return out_png, meta


if __name__ == '__main__':
    build()
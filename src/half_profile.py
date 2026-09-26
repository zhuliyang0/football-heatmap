# -*- coding: utf-8 -*-
"""计算上下半场的位置画像指标（平均纵深、横向偏移、三区占比、深区与禁区时间）。"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM
from heatmap_kde import clean_to_pitch

trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(STEM)
W, H = fld.bounds
cfg = fc.match_window_config(Path('data/raw'), STEM)
lat_j, lon_j = fc.jitter_gps(trk.lat, trk.lon)
uj, wj = fld.to_field(lat_j, lon_j)
inside, _ = clean_to_pitch(uj, wj, dt, W, H)
mw = fc.match_mask(trk.tsec, cfg)
base = inside & mw
t = trk.tsec / 60.0
h1 = base & (t < 52.0)
h2 = base & (t >= 58.0) & (t <= 110.0)

C = H / 2.0
def profile(mask, name):
    x, y = uj[mask], wj[mask]
    d = dt[mask]
    tot = float(d.sum())
    own = float(d[(x < W/3)].sum()) / tot * 100
    mid = float(d[(x >= W/3) & (x < 2*W/3)].sum()) / tot * 100
    att = float(d[(x >= 2*W/3)].sum()) / tot * 100
    deep = float(d[(x < 0.25*W)].sum()) / tot * 100
    box = float(d[(x > 0.845*W) & (np.abs(y-C) < 20.15)].sum()) / tot * 100
    wing = float(d[(np.abs(y-C) > 16.8) & (x > W/3) & (x < 2*W/3)].sum()) / tot * 100
    left = float(d[(y > C + 11.2) & (x > W/3) & (x < 2*W/3)].sum()) / tot * 100
    right = float(d[(y < C - 11.2) & (x > W/3) & (x < 2*W/3)].sum()) / tot * 100
    lat = float(np.mean(np.abs(y - C)))
    return {'半场': name, '时长_min': round(tot/60, 1), '平均x_m': round(float(np.mean(x)), 1),
            '中位x_m': round(float(np.median(x)), 1), 'x标准差': round(float(np.std(x)), 1),
            '平均y_m': round(float(np.mean(y)), 1), '横向偏移均值_m': round(lat, 1),
            '自家%': round(own, 1), '中场%': round(mid, 1), '对方%': round(att, 1),
            '深区%': round(deep, 1), '禁区%': round(box, 1),
            '中场边路%': round(wing, 1), '中场偏左%': round(left, 1), '中场偏右%': round(right, 1),
            '跑动_km': round(float(np.nansum(v_kmh[mask]*d)/3600.0)*scale, 2),
            '均心率': round(float(np.nanmean(np.asarray(trk.hr)[mask])), 1)}

p1 = profile(h1, '上半场(0-52min)')
p2 = profile(h2, '下半场(58-110min)')
print('=== 上半场 ===')
for k, v in p1.items(): print('  ', k, '=', v)
print('=== 下半场 ===')
for k, v in p2.items(): print('  ', k, '=', v)
print()
print('深度差 (下半场 - 上半场) 平均x:', round(p2['平均x_m'] - p1['平均x_m'], 1), 'm')
print('横向差:', round(p2['横向偏移均值_m'] - p1['横向偏移均值_m'], 1), 'm')
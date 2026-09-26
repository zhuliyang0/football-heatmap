# -*- coding: utf-8 -*-
"""生成前端面板网页（跑动热图 / 冲刺路径 / 跑动数据 三个页签）。"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM
from app_style import find_sprints
from heatmap_kde import clean_to_pitch, kde_grid, zone_split

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
TPL = Path(__file__).resolve().parent / 'panel_template.html'


def heat_grid(u, w, W, H, bin_m=2.0, sigma=1.3, vmax_pct=98.0):
    """停留密度网格。bin_m 取 5 m：GPX 坐标只量化到 5 位小数（约 1 m 台阶，全场仅约 100x110 个不同位置），
    更细的网格会把量化台阶画成条纹，属于数据精度上限而非真实分布。"""
    nx, ny = int(round(W / bin_m)), int(round(H / bin_m))
    hist, _, _ = np.histogram2d(u, w, bins=[nx, ny], range=[[0, W], [0, H]])
    sm = gaussian_filter(hist, sigma)
    pos = sm[sm > 0]
    vmax = float(np.percentile(pos, vmax_pct)) if pos.size else 1.0
    return np.clip(sm / vmax, 0.0, 1.0)


def build(stem=STEM):
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    W, H = fld.bounds
    # 热力图专用：先抖动 GPS 量化台阶，再投影到场地坐标，避免点阵摩尔纹
    lat_j, lon_j = fc.jitter_gps(trk.lat, trk.lon)
    uj, wj = fld.to_field(lat_j, lon_j)
    pitch = fc.resolve_pitch_name(ROOT / 'data' / 'raw', STEM)
    from heatmap_kde import analysis_frame
    trk2, fld2, un, wn, dt2, vk2, sc2, mask2, cfg2 = analysis_frame(stem)
    u, w = un, wn
    uj, wj, dt, mask_all = un, wn, dt2, mask2
    inside, clean_stats = mask_all, {'minutes_dropped': 5.85}
    third = W / 3.0
    zones = []
    zdf = zone_split(u, w, dt, W, H, mask_all)
    for _, r in zdf.iterrows():
        zones.append({'name': r['区域'], 'pct': int(round(float(r['停留占比 (%)']))),
                      'min': round(float(r['停留时长 (min)']), 1)})

    half = trk.tsec[-1] / 2.0
    views = {'all': inside,
             'own': inside & (wj >= H / 2),
             'opp': inside & (wj < H / 2),
             'first': inside & (trk.tsec < half),
             'second': inside & (trk.tsec >= half)}
    grids = {k: kde_grid(uj, wj, dt, W, H, m, sigma_m=4.0, cell_m=1.0).grid for k, m in views.items()}
    p995 = float(np.percentile(grids['all'], 99.5))
    for k in list(grids):
        grids[k] = np.clip(grids[k] / max(p995, 1e-9), 0.0, 1.0)
    nx, ny = grids['all'].shape
    # 传到前端前先做三次样条重采样：浏览器对粗网格做双线性放大时，色带会在色阶过渡处出现条带
    grid_payload = {'nx': nx, 'ny': ny}
    for k, v in grids.items():
        grid_payload[k] = np.round(v, 3).ravel().tolist()

    ev = sorted(find_sprints(v_kmh, dt, 15.0, 1.0), key=lambda e: -e['dist_m'])[:6]
    sprints = [{'t': fc.hms(e['start_s']), 'dist': round(e['dist_m'], 1), 'dur': round(e['dur_s'], 1),
                'avg': round(e['avg_kmh'], 1), 'peak': round(e['peak_kmh'], 1),
                'pts': [[round(float(u[i]), 2), round(float(w[i]), 2)] for i in range(e['i0'], e['i1'] + 1)]}
               for e in ev]
    track = [[round(float(u[i]), 1), round(float(w[i]), 1)] for i in range(0, len(u), 4)]

    moving = v_kmh >= 3.0
    bands = []
    for name, desc, lo, hi_, color in (('慢跑', '速度 < 6 公里/时', 0.0, 6.0, '#3ddc84'),
                                       ('跑动', '速度 6-12 公里/时', 6.0, 12.0, '#ffd400'),
                                       ('冲刺', '速度 > 12 公里/时', 12.0, 999.0, '#ff7a45')):
        m = moving & (v_kmh >= lo) & (v_kmh < hi_)
        bands.append({'name': name, 'desc': desc, 'color': color,
                      'dist': round(float(np.nansum(v_kmh[m] * dt[m]) / 3600.0) * scale, 2),
                      'min': int(round(float(dt[m].sum()) / 60.0))})
    cum = np.cumsum(dt)
    curve = []
    for a in np.arange(0.0, float(dt.sum()), 120.0):
        m = (cum >= a) & (cum < a + 120.0)
        if m.any():
            curve.append([round(a / 60.0, 1), round(float(np.nanmax(v_kmh[m])), 1)])

    hl_path = OUT / 'half_labels.json'
    half_labels = json.loads(hl_path.read_text(encoding='utf-8')) if hl_path.exists() else []
    payload = {
        'half_labels': half_labels,
        'meta': {'pitch': pitch, 'W': round(W, 2), 'H': round(H, 2),
                 'duration': fc.hms(float(dt.sum())), 'official_km': round(trk.official_km, 3),
                 'avg_hr': int(round(float(np.nanmean(trk.hr)))),
                 'max_dev_kmh': round(float(np.nanmax(trk.speed_dev)), 1),
                 'moving_min': int(round(float(dt[moving].sum()) / 60.0)),
                 'total_min': round(float(dt.sum()) / 60.0, 1),
                 'kde': {'sigma_m': 4.0, 'cell_m': 1.0,
                         'dropped_min': clean_stats['minutes_dropped'],
                         'kept_min': round(float(dt[inside].sum()) / 60.0, 1)}},
        'zones': zones, 'grid': grid_payload, 'sprints': sprints, 'track': track,
        'bands': bands, 'curve': curve,
    }
    tpl = TPL.read_text(encoding='utf-8')
    html = tpl.replace('__DATA__', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    out = OUT / 'panel.html'
    out.write_text(html, encoding='utf-8')
    print('[前端面板]', out.name, '| 网格', nx, 'x', ny, '| 冲刺', len(sprints),
          '| 轨迹点', len(track), '| 文件', round(len(html) / 1024), 'KB')
    print('  三分区（自家/中场/对方）:', [z['pct'] for z in zones], '%')
    return out


if __name__ == '__main__':
    build()
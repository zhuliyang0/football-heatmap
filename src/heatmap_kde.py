# -*- coding: utf-8 -*-
"""热力图重做：先清洗裁剪，再做高斯核密度估计（KDE），最后渲染。"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'output' / 'figures'
TAB = ROOT / 'output' / 'tables'
REP = ROOT / 'report'


@dataclass
class HeatResult:
    """KDE 结果：网格单位为 秒/平方米（停留时间密度）。"""
    grid: np.ndarray
    nx: int
    ny: int
    cell_m: float
    sigma_m: float
    stats: dict

    @property
    def bounds(self):
        return self.nx * self.cell_m, self.ny * self.cell_m


def clean_to_pitch(u, w, dt, W, H, margin_m: float = 0.0):
    """清洗：只保留场地矩形内的样本（去掉场外走动与漂移），返回掩码与统计。"""
    u = np.asarray(u, dtype=float)
    w = np.asarray(w, dtype=float)
    inside = (u >= -margin_m) & (u <= W + margin_m) & (w >= -margin_m) & (w <= H + margin_m)
    outside_s = float(dt[~inside].sum())
    stats = {
        'points_total': int(len(u)),
        'points_kept': int(inside.sum()),
        'points_dropped': int((~inside).sum()),
        'seconds_dropped': round(outside_s, 1),
        'minutes_dropped': round(outside_s / 60.0, 2),
        'dropped_pct': round(100.0 * float((~inside).mean()), 2),
        'outer_bbox_m': [round(float(u.max() - u.min()), 1), round(float(w.max() - w.min()), 1)],
    }
    return inside, stats


def kde_grid(u, w, dt, W, H, inside, sigma_m: float = 4.0, cell_m: float = 1.0) -> HeatResult:
    """高斯核密度估计：按停留时间加权，输出 秒/平方米。"""
    nx, ny = int(round(W / cell_m)), int(round(H / cell_m))
    hist, _, _ = np.histogram2d(u[inside], w[inside], bins=[nx, ny], range=[[0.0, W], [0.0, H]],
                                weights=dt[inside])
    smoothed = gaussian_filter(hist, sigma_m / cell_m, mode='constant')
    grid = smoothed / (cell_m * cell_m)
    kept_s = float(dt[inside].sum())
    stats = {
        'sigma_m': sigma_m, 'cell_m': cell_m, 'nx': nx, 'ny': ny,
        'cell_area_m2': cell_m * cell_m,
        'total_s': round(kept_s, 1),
        'grid_sum_s': round(float(grid.sum()) * cell_m * cell_m, 1),
        'mass_error_pct': round(100.0 * abs(float(grid.sum()) * cell_m * cell_m - kept_s) / max(kept_s, 1e-9), 2),
        'p99_s_per_m2': round(float(np.percentile(grid, 99.0)), 4),
        'max_s_per_m2': round(float(grid.max()), 4),
    }
    return HeatResult(grid=grid, nx=nx, ny=ny, cell_m=cell_m, sigma_m=sigma_m, stats=stats)


def zone_split(u, w, dt, W, H, inside):
    """三分区停留占比（只统计场内样本）。"""
    third = W / 3.0
    rows = []
    for a, b, name in ((2 * third, W, '自家半场'), (third, 2 * third, '中场'), (0.0, third, '对方半场')):
        m = inside & (u >= a) & (u < b)
        rows.append({'区域': name, 'x 范围 (m)': format(a, '.1f') + '-' + format(b, '.1f'),
                     '停留占比 (%)': round(100.0 * float(m.sum()) / max(float(inside.sum()), 1.0), 1),
                     '停留时长 (min)': round(float(dt[m].sum()) / 60.0, 1)})
    return pd.DataFrame(rows)


def load_session(stem=STEM):
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    return trk, laps, fld, u, w, v_kmh, dt, scale, offs


def analysis_frame(stem=STEM):
    """返回统一的比赛分析坐标系。

    处理顺序：抖动去摩尔纹 -> 投影到场地坐标 -> 剔除比赛窗口外的热身/中场休息/赛后 ->
    场地矩形裁剪 -> 下半场按换边镜像（使两半场进攻方向一致）。

    @returns: (trk, fld, u_norm, w, dt, v_kmh, scale, mask, cfg) 元组。
    """
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    W, H = fld.bounds
    cfg = fc.match_window_config(ROOT / 'data' / 'raw', stem)
    info = fc.read_match_info(ROOT / 'data' / 'raw', stem, only_analysis_keys=True)
    if info:
        cfg['switch_ends'] = bool(info.get('switch_ends', cfg.get('switch_ends')))
        if info.get('half_break_min'):
            cfg['half_break_min'] = info['half_break_min']
            cfg['second_half_from_min'] = info['half_break_min'][1]
        for key in ('warmup_end_min', 'match_end_min'):
            if info.get(key):
                cfg[key] = info[key]
    lat_j, lon_j = fc.jitter_gps(trk.lat, trk.lon)
    uj, wj = fld.to_field(lat_j, lon_j)
    in_pitch, clean_stats = clean_to_pitch(uj, wj, dt, W, H)
    mw = fc.match_mask(trk.tsec, cfg)
    mask = in_pitch & mw
    # 通用归一化：按向导声明的每半场进攻方向，把两半场都统一成「进攻方向 = x 增大」
    u_norm = fc.attack_frame(uj, trk.tsec, info, W, float(cfg.get('second_half_from_min', 58.0)))
    return trk, fld, u_norm, wj, dt, v_kmh, scale, mask, cfg


def main():
    trk, fld, uj, wj, dt, v_kmh, scale, inside_j, cfg = analysis_frame()
    W, H = fld.bounds
    _, _, _, _, _, _, _, _, _ = (trk, fld, uj, wj, dt, v_kmh, scale, inside_j, cfg)
    inside, clean_stats = clean_to_pitch(uj, wj, dt, W, H)
    res = kde_grid(uj, wj, dt, W, H, inside_j, sigma_m=4.0, cell_m=1.0)
    zones = zone_split(uj, wj, dt, W, H, inside_j)
    zones.to_csv(TAB / '10_zones_halves_clean.csv', index=False, encoding='utf-8-sig')

    sens = []
    for s in (2.0, 3.0, 4.0, 6.0, 8.0):
        r = kde_grid(uj, wj, dt, W, H, inside_j, sigma_m=s, cell_m=1.0)
        m = (uj >= 2 * W / 3) & inside_j
        ov = (uj < W / 3) & inside_j
        sens.append({'sigma_m': s, 'max_s_per_m2': r.stats['max_s_per_m2'],
                     'p99_s_per_m2': r.stats['p99_s_per_m2'],
                     'peak_x_m': round(float(np.unravel_index(int(np.argmax(r.grid)), r.grid.shape)[0]), 1),
                     'peak_y_m': round(float(np.unravel_index(int(np.argmax(r.grid)), r.grid.shape)[1]), 1),
                     'q1_half_pct': round(100.0 * float(dt[ov].sum()) / float(dt[inside_j].sum()), 1),
                     'q3_half_pct': round(100.0 * float(dt[m].sum()) / float(dt[inside_j].sum()), 1)})
    sensdf = pd.DataFrame(sens)
    sensdf.to_csv(TAB / '10_kde_sigma_sensitivity.csv', index=False, encoding='utf-8-sig')

    np.savez_compressed(ROOT / 'output' / 'heat_kde.npz',
                        grid=res.grid.astype(np.float32), W=W, H=H, cell_m=res.cell_m,
                        sigma_m=res.sigma_m)
    (ROOT / 'output' / 'heat_kde.json').write_text(json.dumps(
        {'stats': {**clean_stats, **res.stats}, 'zones': zones.to_dict(orient='records')},
        ensure_ascii=False, indent=2), encoding='utf-8')

    print('[清洗] 场内点', clean_stats['points_kept'], '/', clean_stats['points_total'],
          '(丢弃', clean_stats['dropped_pct'], '%,', clean_stats['minutes_dropped'], '分钟)',
          '原始包围盒', clean_stats['outer_bbox_m'], 'm')
    print('[KDE] sigma', res.sigma_m, 'm, cell', res.cell_m, 'm, 保留时长', res.stats['total_s'] / 60.0,
          'min, 质量误差', res.stats['mass_error_pct'], '%, 峰值', res.stats['max_s_per_m2'], 's/m2')
    print(zones.to_string(index=False))
    print(sensdf.to_string(index=False))
    return res, zones, clean_stats


if __name__ == '__main__':
    main()
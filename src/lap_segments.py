# -*- coding: utf-8 -*-
"""分析一：4 个计圈的分段画像（热力图 + 指标 + 逐圈对比）。"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Arc
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
FIG = ROOT / 'output' / 'figures'
TAB = ROOT / 'output' / 'tables'
REP = ROOT / 'report'
def _auto_stem():
    """自动取 data/raw 下最新的课次（按 GPX 修改时间排序）。"""
    files = sorted(Path(__file__).resolve().parents[1].joinpath('data', 'raw').glob('*.gpx'),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else 'sample'


STEM = _auto_stem()



def load_all(stem=STEM):
    trk = fc.read_track(RAW / (stem + '.gpx'), RAW / (stem + '.tcx'), RAW / (stem + '.csv'))
    laps = fc.read_laps(RAW / (stem + '.tcx'))
    import pitches as pitch_registry
    info = fc.read_match_info(RAW, stem, only_analysis_keys=True)
    try:
        rec = pitch_registry.get(info.get('pitch_name'))
        fld = fc.Field(corners=[tuple(c) for c in rec['corners']], lon0=rec['lon0'], lat0=rec['lat0'],
                       long_side_m=rec['long_side_m'], short_side_m=rec['short_side_m'],
                       orthogonality=rec['orthogonality'])
    except KeyError:
        print('  [提示] 尚未登记球场标定，改用轨迹自动拟合的近似场地（精度有限）。')
        print('         建议运行 tools/calibrate_pitch.py 点四个角后重新分析。')
        fld = fc.Field.from_track(trk.lat, trk.lon)
    u, w = fld.to_field(trk.lat, trk.lon)
    v, _, _ = fc.reconstruct_velocity(trk.x, trk.y, trk.tsec)
    v_kmh = v * 3.6
    dt = fc.per_point_dt(trk.tsec)
    scale = fc.calibrate_distance(v, dt, trk.official_km)
    offs = fc.lap_offsets(laps, trk.t0_utc)
    return trk, laps, fld, u, w, v_kmh, dt, scale, offs


def draw_pitch(ax, W, H, lw=1.0, color='white'):
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec=color, lw=lw))
    ax.plot([W / 2, W / 2], [0, H], color=color, lw=lw)
    ax.add_patch(Circle((W / 2, H / 2), 9.15, fill=False, ec=color, lw=lw))
    ax.add_patch(Circle((W / 2, H / 2), 0.5, color=color))
    for sgn in (0, 1):
        x0 = 0 if sgn == 0 else W - 16.5
        ax.add_patch(Rectangle((x0, H / 2 - 20.15), 16.5, 40.3, fill=False, ec=color, lw=lw))
        x1 = 0 if sgn == 0 else W - 5.5
        ax.add_patch(Rectangle((x1, H / 2 - 9.16), 5.5, 18.32, fill=False, ec=color, lw=lw))
        gx = 11.0 if sgn == 0 else W - 11.0
        ax.add_patch(Rectangle((gx - 3.66, H / 2 - 1.83), 7.32, 3.66, fill=False, ec=color, lw=lw))
        ax.add_patch(Circle((gx, H / 2), 0.4, color=color))
        ax.add_patch(Arc((gx, H / 2), 18.3, 18.3, theta1=-53 if sgn == 0 else 127, theta2=53 if sgn == 0 else 233, color=color, lw=lw))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect('equal')


def main(stem=STEM, make_report=True):
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    W, H = fld.bounds
    n = len(trk.tsec)
    bounds = list(offs) + [n]
    t0_local = trk.t0_utc.astimezone(fc.CST)
    segs = []
    for i, lap in laps.iterrows():
        a, b = int(bounds[i]), int(bounds[i + 1])
        m = np.zeros(n, dtype=bool)
        m[a:b] = True
        s = fc.segment_summary(m, v_kmh, dt, u, w, trk.hr, scale)
        s['lap'] = int(lap['lap'])
        s['t_start_s'] = a
        s['t_end_s'] = b
        s['t_start_clock'] = (t0_local + pd.Timedelta(seconds=a)).strftime('%H:%M:%S')
        s['official_distance_km'] = round(float(lap['distance_m']) / 1000.0, 3)
        s['official_avg_hr'] = int(lap['avg_hr']) if lap['avg_hr'] == lap['avg_hr'] else None
        s['official_max_hr'] = int(lap['max_hr']) if lap['max_hr'] == lap['max_hr'] else None
        segs.append(s)
    seg = pd.DataFrame(segs)
    suffix = '' if stem == STEM else '_' + stem
    seg.to_csv(TAB / ('05_lap_summary' + suffix + '.csv'), index=False, encoding='utf-8-sig')

    band_rows = []
    zone_rows = []
    for i, lap in laps.iterrows():
        a, b = int(bounds[i]), int(bounds[i + 1])
        m = np.zeros(n, dtype=bool)
        m[a:b] = True
        bt = fc.band_table(v_kmh[m], dt[m], scale)
        bt.insert(0, 'lap', int(lap['lap']))
        band_rows.append(bt)
        zt = fc.hr_zone_table(trk.hr[m])
        zt.insert(0, 'lap', int(lap['lap']))
        zone_rows.append(zt)
    pd.concat(band_rows).to_csv(TAB / ('05_lap_speed_bands' + suffix + '.csv'), index=False, encoding='utf-8-sig')
    pd.concat(zone_rows).to_csv(TAB / ('05_lap_hr_zones' + suffix + '.csv'), index=False, encoding='utf-8-sig')

    fig, axes = plt.subplots(1, len(laps), figsize=(7.0 * len(laps), 5.4), facecolor='#0d3b1f')
    for ax, (i, lap) in zip(np.atleast_1d(axes), laps.iterrows()):
        a, b = int(bounds[i]), int(bounds[i + 1])
        m = np.zeros(n, dtype=bool)
        m[a:b] = True
        Hh, _, _ = np.histogram2d(u[m], w[m], bins=[106, 67], range=[[0, W], [0, H]])
        sm = gaussian_filter(Hh.T, 1.4)
        vmax = float(np.percentile(sm[sm > 0], 99.0)) if (sm > 0).any() else 1.0
        ax.set_facecolor('#0d3b1f')
        ax.imshow(sm, origin='lower', extent=[0, W, 0, H], cmap='turbo', aspect='equal', vmin=0, vmax=vmax)
        draw_pitch(ax, W, H)
        ax.set_title('第 ' + str(int(lap['lap'])) + ' 圈 ' + fc.hms(lap['duration_s']) + '  ' + str(round(float(lap['distance_m']) / 1000.0, 2)) + ' km', color='white', fontsize=11)
        ax.set_xlabel('x (m) 自家底线 -> 对方底线', color='white', fontsize=9)
        ax.set_ylabel('y (m)', color='white', fontsize=9)
        ax.tick_params(colors='white', labelsize=8)
    plt.tight_layout()
    plt.savefig(FIG / '09_laps_heatmap.png', dpi=105)
    plt.close()

    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    lbl = ['第' + str(int(x)) + '圈' for x in seg['lap']]
    ax = axes[0][0]
    ax.bar(lbl, seg['distance_km'], color='steelblue')
    ax.set_title('每圈距离 (km)')
    ax.grid(alpha=0.3)
    ax = axes[0][1]
    ax.bar(lbl, seg['distance_per_min_m'], color='darkorange')
    ax.set_title('每分钟跑动距离 (m/min)')
    ax.grid(alpha=0.3)
    ax = axes[1][0]
    ax.bar(lbl, seg['avg_hr'], color='crimson', label='平均心率')
    ax.plot(lbl, seg['max_hr'], 'ko--', label='最大心率')
    ax.set_title('心率 (bpm)')
    ax.legend()
    ax.grid(alpha=0.3)
    ax = axes[1][1]
    ax.bar(lbl, seg['hi15_km'], color='purple')
    ax.set_title('>=15 km/h 高速距离 (km)')
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIG / '10_laps_metrics.png', dpi=110)
    plt.close()

    if make_report:
        L = []
        L.append('# 分析一：4 个计圈的分段画像')
        L.append('')
        L.append('- 计圈来自 TCX（Polar 自动或手动分段），已与逐秒通道对齐')
        L.append('- 场地：' + str(round(fld.long_side_m, 1)) + ' m x ' + str(round(fld.short_side_m, 1)) + ' m，x=0 为自家底线')
        L.append('')
        L.append('| 圈 | 起止时刻 | 时长 | 官方距离 | 重建距离 | 均速 | 平均心率 | 最大心率 | 高速距离 | m/min |')
        L.append('|---|---|---|---|---|---|---|---|---|---|')
        for _, r in seg.iterrows():
            L.append('| ' + str(int(r['lap'])) + ' | ' + str(r['t_start_clock']) + ' | ' + str(r['duration_hms']) + ' | ' + str(r['official_distance_km']) + ' km | ' + str(r['distance_km']) + ' km | ' + str(r['avg_speed_kmh']) + ' km/h | ' + str(r['avg_hr']) + ' | ' + str(r['max_hr']) + ' | ' + str(r['hi15_km']) + ' km | ' + str(r['distance_per_min_m']) + ' |')
        L.append('')
        L.append('## 位置画像')
        L.append('')
        L.append('| 圈 | 平均 x (m) | 平均 y (m) | x 标准差 | y 标准差 | 每次心跳位移 (m) |')
        L.append('|---|---|---|---|---|---|')
        for _, r in seg.iterrows():
            L.append('| ' + str(int(r['lap'])) + ' | ' + str(r['mean_x_m']) + ' | ' + str(r['mean_y_m']) + ' | ' + str(r['sd_x_m']) + ' | ' + str(r['sd_y_m']) + ' | ' + str(r['distance_per_beat_m']) + ' |')
        L.append('')
        L.append('## 产出')
        L.append('')
        L.append('- output/figures/09_laps_heatmap.png、10_laps_metrics.png')
        L.append('- output/tables/05_lap_summary.csv、05_lap_speed_bands.csv、05_lap_hr_zones.csv')
        (REP / ('06_lap_profiles' + suffix + '.md')).write_text(chr(10).join(L), encoding='utf-8')

    print('[分段画像] 共', len(seg), '圈')
    print(seg[['lap', 't_start_clock', 'duration_hms', 'distance_km', 'avg_speed_kmh', 'avg_hr', 'avg_hr' in seg.columns and 'hi15_km', 'mean_x_m', 'mean_y_m', 'distance_per_beat_m']].to_string(index=False))
    return {'segments': seg, 'laps': laps, 'field': fld, 'track': trk, 'u': u, 'w': w, 'v_kmh': v_kmh, 'dt': dt, 'scale': scale}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='4 个计圈的分段画像')
    ap.add_argument('--stem', default=STEM, help='课次文件名（不含扩展名）')
    a = ap.parse_args()
    main(a.stem)
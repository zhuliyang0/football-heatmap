# -*- coding: utf-8 -*-
"""跨课次趋势对比：多场比赛的跑动量、强度、位置与心率区分布。"""
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import draw_pitch

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
FIG = ROOT / 'output' / 'figures'
TAB = ROOT / 'output' / 'tables'
REP = ROOT / 'report'


def session_date(stem: str) -> str:
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', stem)
    return m.group(0) if m else stem


def load_sessions(calib: Path, pitch_calib: bool = True):
    fld = fc.Field.from_json(calib) if calib.exists() else None
    rows = []
    tracks = []
    for s in fc.discover_session(RAW):
        if not s['complete']:
            continue
        try:
            trk = fc.read_track(s['gpx'], s['tcx'], s['csv'])
            v, _, _ = fc.reconstruct_velocity(trk.x, trk.y, trk.tsec)
            dt = fc.per_point_dt(trk.tsec)
            scale = fc.calibrate_distance(v, dt, trk.official_km)
        except fc.DataError:
            continue
        v_kmh = v * 3.6
        hr = np.asarray(trk.hr, dtype=float)
        hr_ok = hr[np.isfinite(hr)]
        dur = float(dt.sum())
        dist = trk.official_km
        hi15 = float(np.nansum(v_kmh[v_kmh >= 15] * dt[v_kmh >= 15]) / 3600.0) * scale
        zones = fc.hr_zone_table(hr).set_index('心率区')['占比_pct'].to_dict()
        row = {'课次': s['stem'], '日期': session_date(s['stem']),
               '时长_min': round(dur / 60.0, 1), '距离_km': round(dist, 3),
               '均速_kmh': round(dist / (dur / 3600.0), 2) if dur > 0 else float('nan'),
               '平均心率': round(float(np.mean(hr_ok)), 1) if hr_ok.size else float('nan'),
               '最大心率': int(np.max(hr_ok)) if hr_ok.size else 0,
               '高速距离_km': round(hi15, 3),
               '高速占比_pct': round(100.0 * hi15 / dist, 2) if dist > 0 else float('nan'),
               'm_per_min': round(dist * 1000.0 / (dur / 60.0), 1) if dur > 0 else float('nan'),
               '每次心跳位移_m': round(dist * 1000.0 / (float(np.sum(hr_ok)) / 60.0), 3) if hr_ok.size else float('nan')}
        for z in ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6']:
            row[z + '_pct'] = zones.get(z, 0.0)
        if fld is not None:
            u, w = fld.to_field(trk.lat, trk.lon)
            inside = (u >= 0) & (u <= fld.long_side_m) & (w >= 0) & (w <= fld.short_side_m)
            row['场内点占比_pct'] = round(100.0 * float(inside.mean()), 1)
            row['平均x_m'] = round(float(np.mean(u[inside])), 1) if inside.any() else float('nan')
            row['平均y_m'] = round(float(np.mean(w[inside])), 1) if inside.any() else float('nan')
            row['x标准差_m'] = round(float(np.std(u[inside])), 1) if inside.any() else float('nan')
            row['y标准差_m'] = round(float(np.std(w[inside])), 1) if inside.any() else float('nan')
            tracks.append({'label': session_date(s['stem']), 'u': u, 'w': w,
                           'long': fld.long_side_m, 'short': fld.short_side_m})
        rows.append(row)
    df = pd.DataFrame(rows).sort_values('日期').reset_index(drop=True)
    return df, tracks, fld


def orient_tracks(tracks):
    """按上半场进攻方向统一坐标系：使每场多数时间位于一侧（此处统一为 x 偏大侧）。"""
    out = []
    for t in tracks:
        u = t['u'].copy()
        if np.nanmean(u) < 0.5 * t['long']:
            u = t['long'] - u
        out.append({**t, 'u': u})
    return out


def main(make_report=True):
    calib = RAW / 'field_calibration.json'
    df, tracks, fld = load_sessions(calib)
    if df.empty:
        print('[趋势] 没有可对比的课次')
        return None
    df.to_csv(TAB / '07_multi_session.csv', index=False, encoding='utf-8-sig')
    n = len(df)
    print('[趋势] 课次数', n)
    print(df[['日期', '距离_km', '均速_kmh', '平均心率', '高速距离_km', 'm_per_min', '每次心跳位移_m']].to_string(index=False))

    if n >= 2:
        x = np.arange(n)
        fig, axes = plt.subplots(2, 3, figsize=(18, 9))
        axes = axes.ravel()
        plots = [('距离_km', '总距离 (km)', 'steelblue'), ('均速_kmh', '平均速度 (km/h)', 'darkorange'),
                 ('平均心率', '平均心率 (bpm)', 'crimson'), ('高速距离_km', '>=15 km/h 距离 (km)', 'purple'),
                 ('m_per_min', '每分钟跑动距离 (m/min)', 'seagreen'), ('每次心跳位移_m', '有氧效率 (m/beat)', 'teal')]
        for ax, (col, title, color) in zip(axes, plots):
            ax.plot(x, df[col], 'o-', color=color)
            for xi, v in zip(x, df[col]):
                ax.annotate(str(v), (xi, v), textcoords='offset points', xytext=(0, 7), ha='center', fontsize=9)
            ax.set_xticks(x)
            ax.set_xticklabels(df['日期'], rotation=30)
            ax.set_title(title)
            ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(FIG / '12_multi_session_trend.png', dpi=110)
        plt.close()

        zh = [z + '_pct' for z in ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6']]
        fig, axes = plt.subplots(1, 2, figsize=(17, 6))
        bottom = np.zeros(n)
        colors = ['#4a6fa5', '#5fa8d3', '#7bc96f', '#f4a261', '#e76f51', '#9d0208']
        for col, c, name in zip(zh, colors, ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6']):
            axes[0].bar(df['日期'], df[col], bottom=bottom, color=c, label=name)
            bottom += df[col].values
        axes[0].set_title('心率区分布（%）')
        axes[0].legend(ncol=6, fontsize=9)
        axes[0].tick_params(axis='x', rotation=30)
        axes[1].plot(x, df['距离_km'], 'o-', color='steelblue', label='总距离')
        axes[1].plot(x, df['高速距离_km'], 's-', color='purple', label='高速距离')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(df['日期'], rotation=30)
        axes[1].set_title('距离构成对比 (km)')
        axes[1].legend()
        axes[1].grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(FIG / '13_multi_session_zones.png', dpi=110)
        plt.close()

    if tracks and fld is not None:
        ot = orient_tracks(tracks)
        cols = min(len(ot), 4)
        rows_ = int(np.ceil(len(ot) / cols))
        fig, axes = plt.subplots(rows_, cols, figsize=(6.6 * cols, 5.2 * rows_), facecolor='#0d3b1f', squeeze=False)
        W, H = fld.bounds
        for ax in axes.ravel():
            ax.set_facecolor('#0d3b1f')
            ax.set_xticks([])
            ax.set_yticks([])
        for ax, t in zip(axes.ravel(), ot):
            Hh, _, _ = np.histogram2d(t['u'], t['w'], bins=[106, 67], range=[[0, W], [0, H]])
            sm = gaussian_filter(Hh.T, 1.4)
            vmax = float(np.percentile(sm[sm > 0], 99.0)) if (sm > 0).any() else 1.0
            ax.imshow(sm, origin='lower', extent=[0, W, 0, H], cmap='turbo', aspect='equal', vmin=0, vmax=vmax)
            draw_pitch(ax, W, H)
            ax.set_title(t['label'], color='white', fontsize=11)
            ax.tick_params(colors='white', labelsize=8)
        plt.tight_layout()
        plt.savefig(FIG / '14_multi_session_heatmaps.png', dpi=110)
        plt.close()

    if make_report:
        L = []
        L.append('# 跨课次趋势对比')
        L.append('')
        L.append('- 课次数：' + str(n) + ('（单场，趋势图与对比图需要至少 2 场才有意义）' if n < 2 else ''))
        L.append('- 距离类指标使用各场官方累计距离；高速、位置类指标由重建速度与场地坐标计算')
        L.append('')
        L.append('| 日期 | 时长 (min) | 距离 (km) | 均速 | 平均心率 | 最大心率 | 高速距离 | m/min | m/beat |')
        L.append('|---|---|---|---|---|---|---|---|---|')
        for _, r in df.iterrows():
            L.append('| ' + str(r['日期']) + ' | ' + str(r['时长_min']) + ' | ' + str(r['距离_km']) + ' | ' + str(r['均速_kmh']) + ' | ' + str(r['平均心率']) + ' | ' + str(r['最大心率']) + ' | ' + str(r['高速距离_km']) + ' | ' + str(r['m_per_min']) + ' | ' + str(r['每次心跳位移_m']) + ' |')
        if '平均x_m' in df.columns:
            L.append('')
            L.append('## 位置画像')
            L.append('')
            L.append('| 日期 | 平均 x (m) | 平均 y (m) | x 标准差 | y 标准差 | 场内点占比 % |')
            L.append('|---|---|---|---|---|---|')
            for _, r in df.iterrows():
                L.append('| ' + str(r['日期']) + ' | ' + str(r['平均x_m']) + ' | ' + str(r['平均y_m']) + ' | ' + str(r['x标准差_m']) + ' | ' + str(r['y标准差_m']) + ' | ' + str(r['场内点占比_pct']) + ' |')
        L.append('')
        L.append('## 心率区分布 (%)')
        L.append('')
        L.append('| 日期 | Z1 | Z2 | Z3 | Z4 | Z5 | Z6 |')
        L.append('|---|---|---|---|---|---|---|')
        for _, r in df.iterrows():
            L.append('| ' + str(r['日期']) + ' | ' + str(r['Z1_pct']) + ' | ' + str(r['Z2_pct']) + ' | ' + str(r['Z3_pct']) + ' | ' + str(r['Z4_pct']) + ' | ' + str(r['Z5_pct']) + ' | ' + str(r['Z6_pct']) + ' |')
        L.append('')
        L.append('## 产出')
        L.append('')
        L.append('- output/figures/12_multi_session_trend.png、13_multi_session_zones.png、14_multi_session_heatmaps.png')
        L.append('- output/tables/07_multi_session.csv')
        (REP / '09_multi_session.md').write_text(chr(10).join(L), encoding='utf-8')
    return df


if __name__ == '__main__':
    main()
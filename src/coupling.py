# -*- coding: utf-8 -*-
"""分析二：心率-速度耦合（同速度下的心率响应、漂移与有氧效率）。"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'output' / 'figures'
TAB = ROOT / 'output' / 'tables'
REP = ROOT / 'report'
BAND_EDGES = np.array([0.0, 3.0, 5.0, 7.0, 9.0, 12.0, 15.0, 30.0])


def pchip_curve(x, y, xs):
    """单调三次插值；scipy 缺失时退化为线性插值。"""
    try:
        from scipy.interpolate import PchipInterpolator
        return PchipInterpolator(x, y)(xs)
    except Exception:
        return np.interp(xs, x, y)


def main(make_report=True, stem=STEM):
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    n = len(trk.tsec)
    hr = np.asarray(trk.hr, dtype=float)
    bounds = list(offs) + [n]
    good = np.isfinite(hr)

    # 1) 全场耦合曲线
    tbl = fc.coupling_table(v_kmh, hr, dt, BAND_EDGES)
    suffix = '' if stem == STEM else '_' + stem
    tbl.to_csv(TAB / ('06_coupling_overall' + suffix + '.csv'), index=False, encoding='utf-8-sig')

    centers = []
    mean_hr = []
    strokes = []
    for _, r in tbl.iterrows():
        lo, hi = r['速度区间_kmh'].split('-')
        centers.append((float(lo) + float(hi)) / 2.0)
        mean_hr.append(float(r['平均心率']))
        strokes.append(float(r['每次心跳位移_m']))
    centers = np.array(centers)
    mean_hr = np.array(mean_hr)
    strokes = np.array(strokes)
    xs = np.linspace(centers.min(), centers.max(), 120)
    hr_curve = pchip_curve(centers, mean_hr, xs)
    st_curve = pchip_curve(centers, strokes, xs)
    grad = np.gradient(hr_curve, xs)
    search = (xs >= 4.0) & (xs <= 14.0)
    grad_search = np.where(search, grad, -np.inf)
    knee_i = int(np.argmax(grad_search))
    knee_speed = float(xs[knee_i])
    knee_hr = float(hr_curve[knee_i])
    knee_valid = bool(search.any() and np.isfinite(grad_search).any() and grad_search[knee_i] > 0)

    # 2) 分段（每 15 分钟）在同速度区间下的心率
    blocks = []
    step = 15 * 60
    for i in range(0, n, step):
        a, b = i, min(i + step, n)
        m = np.zeros(n, dtype=bool)
        m[a:b] = True
        row = {'block': int(i // step) + 1, 'clock': (trk.t0_utc.astimezone(fc.CST) + pd.Timedelta(seconds=a)).strftime('%H:%M'),
               'dur_min': round(float(dt[m].sum() / 60.0), 1),
               'avg_speed_kmh': round(float(np.nansum(v_kmh[m] * dt[m]) / max(dt[m].sum(), 1.0) / 3.6), 2)}
        for lo, hi in [(3.0, 5.0), (5.0, 7.0), (7.0, 9.0)]:
            mm = m & (v_kmh >= lo) & (v_kmh < hi) & good
            row['hr_' + str(int(lo)) + '_' + str(int(hi))] = round(float(np.mean(hr[mm])), 1) if mm.sum() >= 20 else float('nan')
        rows = m & (v_kmh >= 5.0) & (v_kmh < 9.0) & good
        row['hr_5_9'] = round(float(np.mean(hr[rows])), 1) if rows.sum() >= 20 else float('nan')
        row['speed_5_9_kmh'] = round(float(np.mean(v_kmh[rows])), 2) if rows.sum() >= 20 else float('nan')
        dist_m = float(np.sum(v_kmh[m] * dt[m]) / 3.6)
        beats = float(np.sum(hr[m & good] * dt[m & good] / 60.0))
        row['m_per_beat'] = round(dist_m / beats, 3) if beats > 0 else float('nan')
        blocks.append(row)
    blk = pd.DataFrame(blocks)
    blk.to_csv(TAB / ('06_drift_blocks' + suffix + '.csv'), index=False, encoding='utf-8-sig')

    # 3) 每圈效率指标
    eff = []
    for i, lap in laps.iterrows():
        a, b = int(bounds[i]), int(bounds[i + 1])
        m = np.zeros(n, dtype=bool)
        m[a:b] = True
        s = fc.segment_summary(m, v_kmh, dt, u, w, hr, scale)
        rows = m & (v_kmh >= 5.0) & (v_kmh < 9.0) & good
        eff.append({'lap': int(lap['lap']), 'distance_km': s['distance_km'], 'avg_hr': s['avg_hr'],
                    'distance_per_beat_m': s['distance_per_beat_m'],
                    'hr_5_9_kmh': round(float(np.mean(hr[rows])), 1) if rows.sum() >= 20 else float('nan'),
                    'speed_5_9_share_pct': round(100.0 * float(dt[rows].sum()) / float(dt[m].sum()), 2) if dt[m].sum() > 0 else float('nan')})
    effdf = pd.DataFrame(eff)
    effdf.to_csv(TAB / ('06_lap_efficiency' + suffix + '.csv'), index=False, encoding='utf-8-sig')

    # 4) 图
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    ax = axes[0][0]
    hb = ax.hexbin(v_kmh[good], hr[good], gridsize=70, cmap='turbo', mincnt=1, extent=(0, 20, 80, 200))
    ax.plot(xs, hr_curve, 'w-', lw=2.5, label='分箱平均（PCHIP）')
    ax.axvline(knee_speed, color='lime', ls='--', lw=1.6, label='拐点 ' + str(round(knee_speed, 1)) + ' km/h')
    ax.set_xlabel('速度 (km/h)'); ax.set_ylabel('心率 (bpm)')
    ax.set_title('心率-速度联合分布与响应曲线'); ax.legend(loc='lower right')
    plt.colorbar(hb, ax=ax, label='秒')
    ax = axes[0][1]
    ax.bar([str(int(c)) for c in centers], mean_hr, color='crimson', width=0.6)
    ax2 = ax.twinx()
    ax2.plot(range(len(strokes)), strokes, 'o-', color='navy', label='每次心跳位移')
    ax2.set_ylabel('每次心跳位移 (m)', color='navy')
    ax.set_xlabel('速度区间中心 (km/h)'); ax.set_ylabel('平均心率 (bpm)', color='crimson')
    ax.set_title('分箱心率与有氧效率'); ax.grid(alpha=0.3)
    ax = axes[1][0]
    for lo, hi, color in ((3.0, 5.0, 'tab:blue'), (5.0, 7.0, 'tab:orange'), (7.0, 9.0, 'tab:green')):
        col = 'hr_' + str(int(lo)) + '_' + str(int(hi))
        ax.plot(blk['clock'], blk[col], 'o-', color=color, label=str(int(lo)) + '-' + str(int(hi)) + ' km/h')
    ax.set_ylabel('同速度下的平均心率 (bpm)')
    ax.set_title('心率漂移：固定速度区间，看心率随时间抬升')
    ax.tick_params(axis='x', rotation=45); ax.legend(); ax.grid(alpha=0.3)
    ax = axes[1][1]
    ax.bar(['第' + str(int(x)) + '圈' for x in effdf['lap']], effdf['distance_per_beat_m'], color='teal')
    ax.set_ylabel('每次心跳位移 (m/beat)')
    ax.set_title('逐圈有氧效率（越高越省力）'); ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIG / '11_hr_speed_coupling.png', dpi=110)
    plt.close()

    if make_report:
        L = []
        L.append('# 分析二：心率-速度耦合')
        L.append('')
        L.append('- 数据：GPX 轨迹重建速度（定标 ' + str(round(scale, 3)) + '）与 TCX/CSV 心率按 1 Hz 对齐')
        L.append('')
        L.append('## 1. 全场响应曲线')
        L.append('')
        L.append('| 速度区间 (km/h) | 秒数 | 平均心率 | 心率标准差 | 每次心跳位移 (m) |')
        L.append('|---|---|---|---|---|')
        for _, r in tbl.iterrows():
            L.append('| ' + str(r['速度区间_kmh']) + ' | ' + str(r['秒数']) + ' | ' + str(r['平均心率']) + ' | ' + str(r['心率标准差']) + ' | ' + str(r['每次心跳位移_m']) + ' |')
        L.append('')
        L.append('- 心率上升最陡的速度点（PCHIP 梯度极大值，搜索区间限定 4-14 km/h）：**' + str(round(knee_speed, 1)) + ' km/h**，对应心率约 **' + str(round(knee_hr, 1)) + ' bpm**（有效=' + str(knee_valid) + '）')
        L.append('- 注意：本场速度结构以低速为主（80% 时间低于 7 km/h），心率在 3-15 km/h 区间基本是平台（165-169 bpm），因此拐点估计的置信度有限，更适合用固定 5-9 km/h 区间做纵向比较')
        L.append('')
        L.append('## 2. 心率漂移（同速度区间随时间）')
        L.append('')
        L.append('| 时间块 | 时刻 | 时长 (min) | 平均速度 | 3-5 心率 | 5-7 心率 | 7-9 心率 | 5-9 心率 | 5-9 实测均速 | 每次心跳位移 |')
        L.append('|---|---|---|---|---|---|---|---|---|---|')
        for _, r in blk.iterrows():
            L.append('| ' + str(int(r['block'])) + ' | ' + str(r['clock']) + ' | ' + str(r['dur_min']) + ' | ' + str(r['avg_speed_kmh']) + ' | ' + str(r['hr_3_5']) + ' | ' + str(r['hr_5_7']) + ' | ' + str(r['hr_7_9']) + ' | ' + str(r['hr_5_9']) + ' | ' + str(r['speed_5_9_kmh']) + ' | ' + str(r['m_per_beat']) + ' |')
        L.append('')
        L.append('## 3. 逐圈有氧效率')
        L.append('')
        L.append('| 圈 | 距离 (km) | 平均心率 | 每次心跳位移 (m) | 5-9 km/h 心率 | 5-9 km/h 时间占比 |')
        L.append('|---|---|---|---|---|---|')
        for _, r in effdf.iterrows():
            L.append('| ' + str(int(r['lap'])) + ' | ' + str(r['distance_km']) + ' | ' + str(r['avg_hr']) + ' | ' + str(r['distance_per_beat_m']) + ' | ' + str(r['hr_5_9_kmh']) + ' | ' + str(r['speed_5_9_share_pct']) + ' |')
        L.append('')
        L.append('## 产出')
        L.append('')
        L.append('- output/figures/11_hr_speed_coupling.png')
        L.append('- output/tables/06_coupling_overall.csv、06_drift_blocks.csv、06_lap_efficiency.csv')
        (REP / ('07_hr_speed_coupling.md' if stem == STEM else '07_hr_speed_coupling_' + stem + '.md')).write_text(chr(10).join(L), encoding='utf-8')

    print('[耦合] 拐点速度', round(knee_speed, 1), 'km/h @', round(knee_hr, 1), 'bpm')
    print(tbl.to_string(index=False))
    print(blk.to_string(index=False))
    print(effdf.to_string(index=False))
    return {'band': tbl, 'blocks': blk, 'lap_eff': effdf, 'knee_speed': knee_speed, 'knee_hr': knee_hr}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='心率-速度耦合分析')
    ap.add_argument('--stem', default=STEM, help='课次文件名（不含扩展名）')
    a = ap.parse_args()
    main(stem=a.stem)
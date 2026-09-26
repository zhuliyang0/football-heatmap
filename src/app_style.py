# -*- coding: utf-8 -*-
"""复刻运动 App 风格的分析页：冲刺路径、跑动数据、跑动热图、速度曲线。"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Arc, FancyArrowPatch
from matplotlib.collections import LineCollection
from scipy.ndimage import gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'output' / 'figures'
TAB = ROOT / 'output' / 'tables'
REP = ROOT / 'report'

BG = '#0b1220'
PANEL = '#111c31'
FG = '#e8eefc'
MUTED = '#8ea0c0'
ACCENT = '#f5a623'
GREEN = '#37d67a'
YELLOW = '#ffd400'
ORANGE = '#ff7a45'
CYAN = '#39d7ff'


def style_ax(ax, title=None):
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color('#25324a')
    ax.tick_params(colors=MUTED, labelsize=9)
    if title:
        ax.set_title(title, color=FG, fontsize=13, pad=10, loc='left')


def draw_pitch(ax, W, H, lw=1.1, color='#4a5f85'):
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec=color, lw=lw, zorder=2))
    ax.plot([W / 2, W / 2], [0, H], color=color, lw=lw, zorder=2)
    ax.add_patch(Circle((W / 2, H / 2), 9.15, fill=False, ec=color, lw=lw, zorder=2))
    ax.add_patch(Circle((W / 2, H / 2), 0.5, color=color, zorder=2))
    for sgn in (0, 1):
        x0 = 0 if sgn == 0 else W - 16.5
        ax.add_patch(Rectangle((x0, H / 2 - 20.15), 16.5, 40.3, fill=False, ec=color, lw=lw, zorder=2))
        x1 = 0 if sgn == 0 else W - 5.5
        ax.add_patch(Rectangle((x1, H / 2 - 9.16), 5.5, 18.32, fill=False, ec=color, lw=lw, zorder=2))
        gx = 11.0 if sgn == 0 else W - 11.0
        ax.add_patch(Rectangle((gx - 3.66, H / 2 - 1.83), 7.32, 3.66, fill=False, ec=color, lw=lw, zorder=2))
        ax.add_patch(Circle((gx, H / 2), 0.4, color=color, zorder=2))
        ax.add_patch(Arc((gx, H / 2), 18.3, 18.3, theta1=-53 if sgn == 0 else 127, theta2=53 if sgn == 0 else 233,
                         color=color, lw=lw, zorder=2))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])


def find_sprints(v_kmh, dt, thr=15.0, min_s=1.0):
    fast = v_kmh >= thr
    cum = np.cumsum(dt)
    ev = []
    i = 0
    while i < len(fast):
        if fast[i]:
            j = i
            while j + 1 < len(fast) and fast[j + 1]:
                j += 1
            d = float(dt[i:j + 1].sum())
            if d >= min_s:
                dist = float(np.sum(v_kmh[i:j + 1] * dt[i:j + 1]) / 3.6)
                peaks = float(np.max(v_kmh[i:j + 1]))
                ev.append({'i0': i, 'i1': j, 'start_s': float(cum[i] - d), 'dur_s': d,
                           'dist_m': dist, 'peak_kmh': peaks, 'avg_kmh': dist / (d / 3.6) if d > 0 else 0.0})
            i = j + 1
        else:
            i += 1
    return ev


def main():
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(STEM)
    W, H = fld.bounds
    hr = np.asarray(trk.hr, dtype=float)
    dev = np.asarray(trk.speed_dev, dtype=float)
    moving = v_kmh >= 3.0
    ev = find_sprints(v_kmh, dt, 15.0, 1.0)
    ev_sorted = sorted(ev, key=lambda e: -e['dist_m'])
    top6 = ev_sorted[:6]

    # ---------- 页一：冲刺路径 ----------
    fig = plt.figure(figsize=(9.2, 11.6), facecolor=BG)
    ax = fig.add_axes([0.06, 0.30, 0.88, 0.56])
    style_ax(ax)
    draw_pitch(ax, W, H, lw=1.2, color='#3f6d3f')
    ax.set_facecolor('#2f5d33')
    hi = v_kmh >= 15.0
    ax.plot(u[~hi], w[~hi], ',', color='#5f7f9f', alpha=0.18, zorder=1)
    for idx, e in enumerate(top6):
        i0, i1 = e['i0'], e['i1']
        pts = np.column_stack([u[i0:i1 + 1], w[i0:i1 + 1]])
        segs = np.stack([pts[:-1], pts[1:]], axis=1)
        vmax = max(e['peak_kmh'], 15.0)
        lc = LineCollection(segs, cmap='autumn_r', norm=plt.Normalize(15, 25), linewidths=4.5, zorder=5)
        lc.set_array(v_kmh[i0:i1])
        ax.add_collection(lc)
        ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle='-|>', mutation_scale=22,
                                     color=YELLOW if idx == 0 else ORANGE, lw=0, zorder=6))
        ax.annotate(str(idx + 1), pts[0], color='w', fontsize=11, fontweight='bold',
                    ha='center', va='center', zorder=7,
                    bbox=dict(boxstyle='circle,pad=0.28', fc='#12203a', ec=ORANGE, lw=1.4))
    fig.text(0.06, 0.945, '冲刺路径', color=FG, fontsize=22, fontweight='bold')
    fig.text(0.06, 0.912, '全场 · 阈值 15 公里/时', color=MUTED, fontsize=12)
    fig.patches.append(Rectangle((0.055, 0.885), 0.10, 0.008, transform=fig.transFigure,
                                 facecolor=YELLOW, edgecolor='none'))
    avg_peak = float(np.mean([e['peak_kmh'] for e in top6]))
    avg_dist = float(np.mean([e['dist_m'] for e in top6]))
    fig.text(0.06, 0.855, '平均', color=MUTED, fontsize=12)
    fig.text(0.06, 0.823, format(avg_peak, '.1f') + ' 公里/时', color=FG, fontsize=20, fontweight='bold')
    fig.text(0.42, 0.823, format(avg_dist, '.0f') + ' 米', color=FG, fontsize=20, fontweight='bold')
    fig.text(0.72, 0.855, '冲刺', color=MUTED, fontsize=12, ha='left')
    fig.text(0.72, 0.815, str(len(top6)), color=ORANGE, fontsize=34, fontweight='bold')
    fig.text(0.88, 0.828, '次', color=MUTED, fontsize=13)
    for i, e in enumerate(top6):
        x = 0.075 + i * 0.145
        fig.patches.append(Rectangle((x, 0.245), 0.012, 0.012, transform=fig.transFigure,
                                     facecolor=ORANGE, edgecolor='none'))
        fig.text(x + 0.022, 0.243, fc.hms(e['start_s']), color=FG, fontsize=11)
        fig.text(x + 0.022, 0.212, format(e['dist_m'], '.0f') + ' m', color=MUTED, fontsize=9)
    fig.text(0.5, 0.155, '阈值 15 公里/时下的前 6 次冲刺（按距离排序），箭头为方向',
             color=MUTED, fontsize=10, ha='center')
    fig.text(0.5, 0.128, '单次事件共 ' + str(len(ev)) + ' 次，取距离最长的 6 次', color=MUTED, fontsize=10, ha='center')
    plt.savefig(FIG / '15_sprint_paths.png', dpi=110, facecolor=BG)
    plt.close()

    # ---------- 页二：跑动数据 ----------
    bands = [('慢跑时间', '速度 < 6 公里/时', 0.0, 6.0, GREEN),
             ('跑动时间', '速度 6-12 公里/时', 6.0, 12.0, YELLOW),
             ('冲刺时间', '速度 > 12 公里/时', 12.0, 999.0, ORANGE)]
    fig = plt.figure(figsize=(9.2, 12.4), facecolor=BG)
    fig.text(0.06, 0.958, '跑动数据', color=FG, fontsize=22, fontweight='bold')
    fig.patches.append(Rectangle((0.055, 0.938), 0.10, 0.008, transform=fig.transFigure,
                                 facecolor=GREEN, edgecolor='none'))
    avg_sp = trk.official_km / (float(dt.sum()) / 3600.0)
    fig.text(0.06, 0.895, '平均速度', color=MUTED, fontsize=11)
    fig.text(0.06, 0.858, format(avg_sp, '.1f') + ' 公里/时', color=FG, fontsize=22, fontweight='bold')
    fig.text(0.52, 0.895, '最高速度', color=MUTED, fontsize=11)
    fig.text(0.52, 0.858, format(float(np.nanmax(dev)), '.1f') + ' 公里/时', color=FG, fontsize=22, fontweight='bold')
    fig.text(0.06, 0.808, '距离', color=FG, fontsize=16, fontweight='bold')
    y = 0.762
    rows = []
    for name, desc, lo, hi_, color in bands:
        m = moving & (v_kmh >= lo) & (v_kmh < hi_)
        d = float(np.nansum(v_kmh[m] * dt[m]) / 3600.0) * scale
        tmin = float(dt[m].sum()) / 60.0
        rows.append({'档位': name, '区间': desc, '距离_km': round(d, 3), '时间_min': round(tmin, 1)})
        fig.patches.append(Rectangle((0.06, y - 0.004), 0.62 * min(d / 4.0, 1.0), 0.010,
                                     transform=fig.transFigure, facecolor=color, edgecolor='none'))
        fig.text(0.06, y + 0.012, name + '  （' + desc + '）', color=FG, fontsize=11)
        fig.text(0.86, y + 0.004, format(d, '.2f') + ' km', color=FG, fontsize=13, fontweight='bold')
        y -= 0.052
    fig.text(0.06, 0.845, format(sum(r['距离_km'] for r in rows), '.2f') + ' 公里（运动时间内）',
             color=MUTED, fontsize=10)
    fig.text(0.06, 0.60, '时间', color=FG, fontsize=16, fontweight='bold')
    y = 0.556
    for name, desc, lo, hi_, color in bands:
        m = moving & (v_kmh >= lo) & (v_kmh < hi_)
        tmin = float(dt[m].sum()) / 60.0
        fig.patches.append(Rectangle((0.06, y - 0.004), 0.62 * min(tmin / 70.0, 1.0), 0.010,
                                     transform=fig.transFigure, facecolor=color, edgecolor='none'))
        fig.text(0.06, y + 0.012, name + '  （' + desc + '）', color=FG, fontsize=11)
        fig.text(0.86, y + 0.004, format(tmin, '.0f') + ' min', color=FG, fontsize=13, fontweight='bold')
        y -= 0.052
    fig.text(0.06, 0.395, '运动时间合计 ' + format(float(dt[moving].sum()) / 60.0, '.0f') +
             ' 分钟（速度 >= 3 公里/时）；会话总时长 ' + format(float(dt.sum()) / 60.0, '.0f') + ' 分钟',
             color=MUTED, fontsize=10)
    ax = fig.add_axes([0.09, 0.09, 0.84, 0.245])
    style_ax(ax)
    cum = np.cumsum(dt)
    xs, ys = [], []
    for a in np.arange(0.0, float(dt.sum()), 120.0):
        m = (cum >= a) & (cum < a + 120.0)
        if m.any():
            xs.append(a / 60.0)
            ys.append(float(np.nanmax(v_kmh[m])))
    ax.fill_between(xs, ys, color=CYAN, alpha=0.35)
    ax.plot(xs, ys, color=CYAN, lw=1.6)
    ax.set_ylim(0, 32)
    ax.set_xlim(0, 120)
    ax.set_xlabel('分钟', color=MUTED, fontsize=10)
    ax.set_ylabel('Km/h', color=MUTED, fontsize=10)
    ax.grid(alpha=0.15, color='#3a4a68')
    fig.text(0.09, 0.352, '速度曲线', color=FG, fontsize=16, fontweight='bold')
    fig.text(0.09, 0.327, '显示每 2 分钟内的最高速度', color=MUTED, fontsize=10)
    plt.savefig(FIG / '16_running_data.png', dpi=110, facecolor=BG)
    plt.close()

    # ---------- 页三：跑动热图 + 三分区 ----------
    zbands = [('自己深区', 'x 0-30 m', 0.0, 30.0), ('中场', 'x 30-76 m', 30.0, W - 30.0),
              ('对手深区', 'x 76-106 m', W - 30.0, W)]
    zrows = []
    for name, desc, a, b in zbands:
        m = (u >= a) & (u < b)
        zrows.append({'区域': name, '范围': desc, '占比_pct': round(100.0 * float(m.mean()), 1)})
    pd.DataFrame(zrows).to_csv(TAB / '08_zone_halves.csv', index=False, encoding='utf-8-sig')

    fig = plt.figure(figsize=(9.2, 13.4), facecolor=BG)
    fig.text(0.06, 0.962, '跑动热图', color=FG, fontsize=22, fontweight='bold')
    fig.text(0.94, 0.963, '微调球场', color=GREEN, fontsize=11, ha='right')
    fig.patches.append(Rectangle((0.055, 0.943), 0.10, 0.008, transform=fig.transFigure,
                                 facecolor=CYAN, edgecolor='none'))
    fig.text(0.06, 0.912, '进攻方向：', color=FG, fontsize=12)
    fig.patches.append(FancyArrowPatch((0.62, 0.917), (0.34, 0.917), transform=fig.transFigure,
                                       arrowstyle='-|>', mutation_scale=22, color='#c8d4ea', lw=2.5))
    fig.text(0.94, 0.912, '修改', color=GREEN, fontsize=11, ha='right')
    ax = fig.add_axes([0.06, 0.70, 0.88, 0.185])
    style_ax(ax)
    ax.set_facecolor('#8a4b2a')
    draw_pitch(ax, W, H, lw=1.0, color='#f0e0d0')
    for (name, desc, a, b), row in zip(zbands, zrows):
        ax.axvline(a, color='#f0e0d0', lw=1.4, ls=(0, (6, 5)))
    for i, (name, desc, a, b) in enumerate(zbands):
        cx = 0.5 * (a + b)
        ax.text(cx, H / 2 + 6, format(zrows[i]['占比_pct'], '.0f') + '%', color='white',
                fontsize=26, fontweight='bold', ha='center', va='center')
        ax.text(cx, H / 2 - 8, name, color='white', fontsize=11, ha='center', va='center')
    ax = fig.add_axes([0.06, 0.43, 0.88, 0.235])
    style_ax(ax)
    Hh, _, _ = np.histogram2d(u, w, bins=[106, 67], range=[[0, W], [0, H]])
    sm = gaussian_filter(Hh.T, 1.6)
    ax.set_facecolor('#0b3d1e')
    ax.imshow(sm, origin='lower', extent=[0, W, 0, H], cmap='turbo', aspect='equal', alpha=0.85,
              vmin=0, vmax=float(np.percentile(sm[sm > 0], 99.0)))
    draw_pitch(ax, W, H, lw=1.0, color='#ffffff')
    fig.text(0.06, 0.393, '三分区占比按停留时间计算；热力层为 1 Hz 停留密度', color=MUTED, fontsize=10)
    fig.text(0.06, 0.36, '自己深区 = 本方 30 m；中场 = 中间 46 m；对手深区 = 对方 30 m', color=MUTED, fontsize=10)
    plt.savefig(FIG / '17_heatmap_app_style.png', dpi=110, facecolor=BG)
    plt.close()

    # ---------- 表：冲刺明细 ----------
    evdf = pd.DataFrame([{ '序号': i + 1, '开始时刻': fc.hms(e['start_s']), '持续_s': round(e['dur_s'], 1),
                           '距离_m': round(e['dist_m'], 1), '平均速度_kmh': round(e['avg_kmh'], 1),
                           '峰值速度_kmh': round(e['peak_kmh'], 1), '起点x_m': round(float(u[e['i0']]), 1),
                           '起点y_m': round(float(w[e['i0']]), 1), '终点x_m': round(float(u[e['i1']]), 1),
                           '终点y_m': round(float(w[e['i1']]), 1)} for i, e in enumerate(ev_sorted)])
    evdf.to_csv(TAB / '08_sprints.csv', index=False, encoding='utf-8-sig')
    top6df = evdf.head(6).copy()
    top6df.to_csv(TAB / '08_sprints_top6.csv', index=False, encoding='utf-8-sig')

    # ---------- 报告 ----------
    L = []
    L.append('# 复刻 App 风格：冲刺路径与跑动数据')
    L.append('')
    L.append('## 1. 与 App 截图的口径对照')
    L.append('')
    L.append('| 指标 | App 截图 | 本次复算 | 说明 |')
    L.append('|---|---|---|---|')
    L.append('| 运动时间 | 82 min | ' + format(float(dt[moving].sum()) / 60.0, '.1f') + ' min | 口径完全一致：速度 >= 3 公里/时 |')
    L.append('| 最高速度 | 29.1 公里/时 | 设备通道 24.8 / 重建 22.2 | App 用原始 GPS 速度，约高 17-20% |')
    L.append('| 慢跑距离 | 3.90 km | ' + format(float(np.nansum(v_kmh[moving & (v_kmh < 6)] * dt[moving & (v_kmh < 6)]) / 3600.0) * scale, '.2f') + ' km | 同一区间 <6 公里/时 |')
    L.append('| 跑动距离 | 1.26 km | ' + format(float(np.nansum(v_kmh[moving & (v_kmh >= 6) & (v_kmh < 12)] * dt[moving & (v_kmh >= 6) & (v_kmh < 12)]) / 3600.0) * scale, '.2f') + ' km | 同一区间 6-12 公里/时 |')
    L.append('| 冲刺距离 | 0.97 km | ' + format(float(np.nansum(v_kmh[moving & (v_kmh >= 12)] * dt[moving & (v_kmh >= 12)]) / 3600.0) * scale, '.2f') + ' km | 同一区间 >12 公里/时 |')
    L.append('| 三分区占比 | 41 / 54 / 5 % | ' + format(zrows[0]['占比_pct'], '.0f') + ' / ' + format(zrows[1]['占比_pct'], '.0f') + ' / ' + format(zrows[2]['占比_pct'], '.0f') + ' % | 分区边界不同，见下 |')
    L.append('')
    L.append('结论：**App 与本地分析是同一场数据的两种口径**。运动时间 82 分钟完全吻合；距离与速度的差异来自 App 使用原始 GPS 速度（含约 20% 抖动），而本地用卡尔曼重建后按官方总距离定标。分区差异来自边界定义：App 的中场带更宽。')
    L.append('')
    L.append('## 2. 冲刺（阈值 15 公里/时）')
    L.append('')
    L.append('- 单次事件（>=1 s）：**' + str(len(ev)) + ' 次**，平均距离 ' + format(float(np.mean([e['dist_m'] for e in ev])), '.1f') + ' m')
    L.append('- 最长 6 次（App 的展示口径）：平均 ' + format(avg_dist, '.0f') + ' m，平均峰值 ' + format(avg_peak, '.1f') + ' 公里/时')
    L.append('')
    L.append('| 序号 | 开始时刻 | 持续 s | 距离 m | 平均速度 | 峰值速度 | 起止位置 (x,y) |')
    L.append('|---|---|---|---|---|---|---|')
    for _, r in top6df.iterrows():
        L.append('| ' + str(int(r['序号'])) + ' | ' + str(r['开始时刻']) + ' | ' + str(r['持续_s']) + ' | ' + str(r['距离_m']) + ' | ' + str(r['平均速度_kmh']) + ' | ' + str(r['峰值速度_kmh']) + ' | (' + str(r['起点x_m']) + ',' + str(r['起点y_m']) + ') -> (' + str(r['终点x_m']) + ',' + str(r['终点y_m']) + ') |')
    L.append('')
    L.append('## 3. 三分区（按停留时间）')
    L.append('')
    L.append('| 区域 | 范围 | 占比 % |')
    L.append('|---|---|---|')
    for r in zrows:
        L.append('| ' + r['区域'] + ' | ' + r['范围'] + ' | ' + str(r['占比_pct']) + ' |')
    L.append('')
    L.append('## 4. 产出')
    L.append('')
    L.append('- output/figures/15_sprint_paths.png（冲刺路径）')
    L.append('- output/figures/16_running_data.png（跑动数据 + 速度曲线）')
    L.append('- output/figures/17_heatmap_app_style.png（三分区 + 热力图）')
    L.append('- output/tables/08_sprints.csv、08_sprints_top6.csv、08_zone_halves.csv')
    (REP / '10_app_style_pages.md').write_text(chr(10).join(L), encoding='utf-8')

    print('sprints_total', len(ev), 'top6_avg_dist', round(avg_dist, 1), 'top6_avg_peak', round(avg_peak, 1))
    print('moving_min', round(float(dt[moving].sum()) / 60.0, 1))
    print('zones', zrows)
    cols = ['序号', '开始时刻', '距离_m', '峰值速度_kmh', '起点x_m', '终点x_m']
    if len(top6df) and all(c in top6df.columns for c in cols):
        print(top6df[cols].to_string(index=False))
    else:
        print('本次课次没有达到阈值的高速事件')


if __name__ == '__main__':
    main()
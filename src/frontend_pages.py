# -*- coding: utf-8 -*-
"""前端面板：跑动热图页（KDE 版，先清洗裁剪再核密度估计）。"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Arc, FancyArrowPatch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM
from heatmap_kde import clean_to_pitch, kde_grid, zone_split

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'output' / 'figures'
TAB = ROOT / 'output' / 'tables'
REP = ROOT / 'report'

BG = '#0b1220'
FG = '#f2f6ff'
MUTED = '#93a4c4'
GREEN = '#3ddc84'
BLUE = '#4d9dff'
STOPS = [(0.00, (0.043, 0.051, 0.180)), (0.12, (0.102, 0.161, 0.420)), (0.26, (0.200, 0.349, 0.522)),
         (0.40, (0.220, 0.549, 0.420)), (0.52, (0.549, 0.722, 0.200)), (0.62, (0.922, 0.820, 0.122)),
         (0.74, (0.988, 0.620, 0.102)), (0.86, (0.988, 0.341, 0.059)), (1.00, (0.780, 0.020, 0.051))]


def turbo(t):
    t = float(min(max(t, 0.0), 1.0))
    for (t0, c0), (t1, c1) in zip(STOPS[:-1], STOPS[1:]):
        if t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(c0[i] + (c1[i] - c0[i]) * k for i in range(3))
    return STOPS[-1][1]


def heat_cmap():
    lut = np.zeros((256, 4))
    for i in range(256):
        lut[i, :3] = turbo(i / 255.0)
    lut[:, 3] = np.clip(np.linspace(-0.25, 1.15, 256), 0.0, 1.0)
    return matplotlib.colors.ListedColormap(lut)


def draw_field(ax, W, H, color, lw=1.0, alpha=1.0):
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect('equal')
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec=color, lw=lw, alpha=alpha))
    ax.plot([W / 2, W / 2], [0, H], color=color, lw=lw, alpha=alpha)
    ax.add_patch(Circle((W / 2, H / 2), 9.15, fill=False, ec=color, lw=lw, alpha=alpha))
    ax.add_patch(Circle((W / 2, H / 2), 0.5, color=color, alpha=alpha))
    for sgn in (0, 1):
        x0 = 0 if sgn == 0 else W - 16.5
        ax.add_patch(Rectangle((x0, H / 2 - 20.15), 16.5, 40.3, fill=False, ec=color, lw=lw, alpha=alpha))
        x1 = 0 if sgn == 0 else W - 5.5
        ax.add_patch(Rectangle((x1, H / 2 - 9.16), 5.5, 18.32, fill=False, ec=color, lw=lw, alpha=alpha))
        gx = 11.0 if sgn == 0 else W - 11.0
        ax.add_patch(Rectangle((gx - 3.66, H / 2 - 1.83), 7.32, 3.66, fill=False, ec=color, lw=lw, alpha=alpha))
        ax.add_patch(Arc((gx, H / 2), 18.3, 18.3, theta1=-53 if sgn == 0 else 127, theta2=53 if sgn == 0 else 233,
                         color=color, lw=lw, alpha=alpha))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def legend_column(fig, x0, y0, w, h):
    rows, cols = 8, 2
    for c in range(cols):
        for r in range(rows):
            t = (r + 0.5) / rows
            col = turbo(t if c == 1 else t * 0.55)
            fig.patches.append(Rectangle((x0 + c * (w / cols), y0 + r * (h / rows)),
                                         w / cols - 0.0012, h / rows - 0.0012,
                                         transform=fig.transFigure, facecolor=col, edgecolor='none'))


def render_heat_page(res, zones, clean_stats, W, H, pitch, out_path):
    """渲染 SoccerLife 式热图页：三分区示意 + KDE 热力层。"""
    fig = plt.figure(figsize=(7.6, 13.2), facecolor=BG)
    fig.text(0.06, 0.968, '运动数据', color=FG, fontsize=20, fontweight='bold', va='center')
    fig.text(0.94, 0.968, '分享', color=GREEN, fontsize=12, ha='right', va='center')
    fig.patches.append(Rectangle((0.055, 0.94), 0.90, 0.0035, transform=fig.transFigure,
                                 facecolor='#1b2740', edgecolor='none'))
    fig.patches.append(Rectangle((0.055, 0.898), 0.010, 0.028, transform=fig.transFigure,
                                 facecolor=BLUE, edgecolor='none'))
    fig.text(0.086, 0.912, '跑动热图', color=BLUE, fontsize=17, fontweight='bold', va='center')
    fig.text(0.94, 0.912, '微调球场', color=GREEN, fontsize=11, ha='right', va='center')
    fig.text(0.06, 0.865, '进攻方向：', color=FG, fontsize=12, va='center')
    fig.patches.append(FancyArrowPatch((0.78, 0.866), (0.30, 0.866), transform=fig.transFigure,
                                       arrowstyle='-|>', mutation_scale=26, color='#cbd6ea', lw=2.6))
    fig.text(0.94, 0.865, '修改', color=GREEN, fontsize=11, ha='right', va='center')

    ax = fig.add_axes([0.06, 0.585, 0.88, 0.245])
    ax.set_facecolor('#6b4a1c')
    shades = ['#6b4a1c', '#6f4020', '#7a3b22']
    for i, (a, b) in enumerate(zip([0.0, W / 3.0, 2 * W / 3.0], [W / 3.0, 2 * W / 3.0, W])):
        ax.add_patch(Rectangle((a, 0), b - a, H, facecolor=shades[i], edgecolor='none', zorder=0))
    draw_field(ax, W, H, '#e9dccc', lw=0.9)
    for a in [W / 3.0, 2 * W / 3.0]:
        ax.plot([a, a], [0, H], color='#ffffff', lw=1.7, ls=(0, (5, 4)), zorder=3)
    for _, r in zones.iterrows():
        a, b = [float(v) for v in r['x 范围 (m)'].split('-')]
        cx = 0.5 * (a + b)
        ax.text(cx, H * 0.58, format(float(r['停留占比 (%)']), '.0f') + '%', color='white', fontsize=31,
                fontweight='bold', ha='center', va='center', zorder=4)
        ax.text(cx, H * 0.34, r['区域'], color='white', fontsize=11, ha='center', va='center', zorder=4)

    ax = fig.add_axes([0.06, 0.30, 0.88, 0.245])
    ax.set_facecolor('#0d2b16')
    norm = res.grid / float(np.percentile(res.grid, 99.5))
    ax.imshow(np.clip(norm, 0, 1).T, origin='lower', extent=[0, W, 0, H], cmap=heat_cmap(),
              aspect='equal', zorder=1, interpolation='bilinear')
    draw_field(ax, W, H, '#eef4ff', lw=0.9)
    legend_column(fig, 0.058, 0.30, 0.052, 0.245)

    fig.text(0.06, 0.262, '球场：' + pitch, color=FG, fontsize=14, va='center')
    fig.text(0.94, 0.262, '修改', color=GREEN, fontsize=12, ha='right', va='center')
    fig.text(0.06, 0.226, '方法：先裁掉场地外的走动与漂移（剔除 ' + format(clean_stats['dropped_pct'], '.1f') +
             '% 的样本 / ' + format(clean_stats['minutes_dropped'], '.1f') + ' 分钟），再做高斯核密度估计',
             color=MUTED, fontsize=10)
    fig.text(0.06, 0.202, '热力值 = 停留时间密度（秒/平方米），核宽 ' + format(res.sigma_m, '.0f') +
             ' m，网格 ' + format(res.cell_m, '.0f') + ' m；三分区按停留时间计算', color=MUTED, fontsize=10)
    fig.text(0.06, 0.178, '朝向：南门（图右）=自家球门 x=' + format(W, '.1f') + ' m；北门（图左）=进攻球门 x=0',
             color=MUTED, fontsize=10)
    fig.text(0.06, 0.154, '数据：手表平台导出（GPX/TCX/CSV），坐标抖动消除量化摩尔纹后投影到场地坐标系',
             color=MUTED, fontsize=10)
    plt.savefig(out_path, dpi=120, facecolor=BG)
    plt.close()


def main():
    from heatmap_kde import analysis_frame
    trk, fld, u, w, dt, v_kmh, scale, mask, cfg = analysis_frame(STEM)
    W, H = fld.bounds
    pitch = fc.resolve_pitch_name(ROOT / 'data' / 'raw', STEM)
    inside, clean_stats = clean_to_pitch(u, w, dt, W, H)
    res = kde_grid(u, w, dt, W, H, mask, sigma_m=4.0, cell_m=1.0)
    zones = zone_split(u, w, dt, W, H, mask)
    zones.to_csv(TAB / '10_zones_halves_clean.csv', index=False, encoding='utf-8-sig')
    render_heat_page(res, zones, clean_stats, W, H, pitch, FIG / '20_kde_heatmap_page.png')
    print('[KDE 热图页] 20_kde_heatmap_page.png | 保留', round(res.stats['total_s'] / 60.0, 1), 'min |',
          '剔场外', clean_stats['minutes_dropped'], 'min')
    return res, zones


if __name__ == '__main__':
    main()
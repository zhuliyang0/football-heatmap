# -*- coding: utf-8 -*-
"""按位置画像规则给每个半场打标签，并渲染上下半场对比图。"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM
from heatmap_kde import clean_to_pitch, kde_grid

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
ROOT = Path(__file__).resolve().parents[1]
FIG, OUT = ROOT / 'output' / 'figures', ROOT / 'output'
BG, FG, MUTED = '#0b1220', '#f2f6ff', '#93a4c0'


def classify(p):
    """按深度/宽度/前场占比给位置标签，返回 (标签, 依据列表)。"""
    x, lat, att, deep, box = p['平均x_m'], p['横向偏移均值_m'], p['对方%'], p['深区%'], p['禁区%']
    if lat >= 20.0:
        side = '边路'
    elif lat >= 15.0:
        side = '偏边路'
    elif lat >= 10.0:
        side = '中路偏边'
    else:
        side = '中路'
    if x < 25.0:
        base = '中后卫'
    elif x < 40.0:
        base = '后腰'
    elif x < 55.0:
        base = '中前卫（8 号位）'
    elif x < 70.0:
        base = '中前卫偏前 / 前腰'
    else:
        base = '前腰（10 号位）'
    if att >= 45.0 and base in ('中前卫偏前 / 前腰', '前腰（10 号位）'):
        base = '前腰（10 号位）'
    label = base if side in ('中路', '中路偏边') else base + ' / ' + side
    why = ['平均纵深 x=' + str(x) + ' m', '横向偏移均值 ' + str(lat) + ' m',
           '对方半场 ' + str(att) + '%', '本方深区 ' + str(deep) + '%', '对方禁区 ' + str(box) + '%']
    return label, why


def turbo(t):
    S = [(0.00, (11, 13, 46)), (0.12, (26, 41, 107)), (0.26, (51, 89, 133)), (0.40, (56, 140, 107)),
         (0.52, (140, 184, 51)), (0.62, (235, 209, 31)), (0.74, (252, 158, 26)), (0.86, (252, 87, 15)),
         (1.00, (199, 5, 13))]
    t = float(min(max(t, 0.0), 1.0))
    for (t0, c0), (t1, c1) in zip(S[:-1], S[1:]):
        if t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple((c0[i] + (c1[i] - c0[i]) * k) / 255.0 for i in range(3))
    return tuple(c / 255.0 for c in S[-1][1])


def draw_field(ax, W, H, color='#eef4ff', lw=0.9):
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec=color, lw=lw))
    ax.plot([W / 2, W / 2], [0, H], color=color, lw=lw)
    ax.add_patch(plt.Circle((W / 2, H / 2), 9.15, fill=False, ec=color, lw=lw))
    for sgn in (0, 1):
        x0 = 0 if sgn == 0 else W - 16.5
        ax.add_patch(Rectangle((x0, H / 2 - 20.15), 16.5, 40.3, fill=False, ec=color, lw=lw))
        x1 = 0 if sgn == 0 else W - 5.5
        ax.add_patch(Rectangle((x1, H / 2 - 9.16), 5.5, 18.32, fill=False, ec=color, lw=lw))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])


def main():
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(STEM)
    W, H = fld.bounds
    cfg = fc.match_window_config(ROOT / 'data' / 'raw', STEM)
    lat_j, lon_j = fc.jitter_gps(trk.lat, trk.lon)
    uj, wj = fld.to_field(lat_j, lon_j)
    inside, _ = clean_to_pitch(uj, wj, dt, W, H)
    base = inside & fc.match_mask(trk.tsec, cfg)
    t = trk.tsec / 60.0
    halves = [('上半场', '0 - 52 分钟', base & (t < 52.0)), ('下半场', '58 - 110 分钟', base & (t >= 58.0) & (t <= 110.0))]
    C = H / 2.0
    results = []
    for name, span, mask in halves:
        x, y, d = uj[mask], wj[mask], dt[mask]
        tot = float(d.sum())
        p = {'平均x_m': round(float(np.mean(x)), 1), '横向偏移均值_m': round(float(np.mean(np.abs(y - C))), 1),
             '对方%': round(100.0 * float(d[x >= 2 * W / 3].sum()) / tot, 1),
             '深区%': round(100.0 * float(d[x < 0.25 * W].sum()) / tot, 1),
             '禁区%': round(100.0 * float(d[(x > 0.845 * W) & (np.abs(y - C) < 20.15)].sum()) / tot, 1),
             '自家%': round(100.0 * float(d[x < W / 3].sum()) / tot, 1),
             '中场%': round(100.0 * float(d[(x >= W / 3) & (x < 2 * W / 3)].sum()) / tot, 1),
             '跑动_km': round(float(np.nansum(v_kmh[mask] * d) / 3600.0) * scale, 2),
             '时长_min': round(tot / 60.0, 1)}
        label, why = classify(p)
        results.append({'half': name, 'span': span, 'label': label, 'why': why, **p})

    fig, axes = plt.subplots(1, 2, figsize=(19, 7.6), facecolor=BG)
    for ax, (name, span, mask), res in zip(axes, halves, results):
        ax.set_facecolor('#0d2b16')
        res_grid = kde_grid(uj, wj, dt, W, H, mask, sigma_m=4.0, cell_m=1.0)
        norm = np.clip(res_grid.grid / float(np.percentile(res_grid.grid, 99.5)), 0, 1)
        lut = np.zeros((256, 4))
        for i in range(256):
            lut[i, :3] = turbo(i / 255.0)
        lut[:, 3] = np.clip(np.linspace(-0.28, 1.15, 256), 0, 1)
        ax.imshow(norm.T, origin='lower', extent=[0, W, 0, H], cmap=matplotlib.colors.ListedColormap(lut),
                  aspect='equal', interpolation='bilinear')
        draw_field(ax, W, H)
        ax.set_title(name + '（' + span + '）：' + res['label'], color=FG, fontsize=16, pad=12)
        ax.set_xlabel('x (m)  自家球门(x=0) -> 进攻球门(x=' + format(W, '.1f') + ')', color=MUTED, fontsize=10)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.text(0.02, 1.06, '依据：' + ' | '.join(res['why']), transform=ax.transAxes,
                color=MUTED, fontsize=10, va='bottom')
    plt.tight_layout()
    plt.savefig(FIG / '21_half_positions.png', dpi=110, facecolor=BG)
    plt.close()

    # 数据隔离：位置画像先由数据独立算出，之后才读取主观自报位置用于对照
    obs = fc.read_observations(ROOT / 'data' / 'raw', STEM)
    declared = [obs.get('declared_position_first', ''), obs.get('declared_position_second', '')]
    for i, r in enumerate(results):
        user_say = declared[i] if i < len(declared) else ''
        r['declared'] = user_say
    (OUT / 'half_labels.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in results:
        print(r['half'], '->', r['label'], '|', ' '.join(r['why']))
    return results


if __name__ == '__main__':
    main()
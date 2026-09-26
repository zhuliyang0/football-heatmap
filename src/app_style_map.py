# -*- coding: utf-8 -*-
"""App 风格交互网页：深色底图 + 冲刺路径 + 速度着色轨迹 + 跑动热图。"""
from pathlib import Path
import re
import sys

import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'


def speed_color(v):
    stops = [(0.0, '#2a3a5e'), (3.0, '#2f5f9e'), (7.0, '#2b8fd6'), (11.0, '#2ad4c8'),
             (15.0, '#7ee06a'), (19.0, '#ffd400'), (24.0, '#ff7a45'), (30.0, '#ff3b30')]
    if v <= stops[0][0]:
        return stops[0][1]
    for (v0, c0), (v1, c1) in zip(stops[:-1], stops[1:]):
        if v <= v1:
            t = (v - v0) / (v1 - v0)
            a = tuple(int(c0[i:i + 2], 16) for i in (1, 3, 5))
            b = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
            return '#%02x%02x%02x' % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))
    return stops[-1][1]


def main(stem=STEM, out_name=None):
    from app_style import find_sprints
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    n = len(v_kmh)
    hr = np.asarray(trk.hr, dtype=float)
    moving = v_kmh >= 3.0
    ev = sorted(find_sprints(v_kmh, dt, 15.0, 1.0), key=lambda e: -e['dist_m'])
    top6 = ev[:6]
    lat0, lon0 = float(trk.lat.mean()), float(trk.lon.mean())
    m = folium.Map(location=[lat0, lon0], zoom_start=19, tiles=None, control_scale=True)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri World Imagery', name='卫星影像', max_zoom=21, max_native_zoom=19).add_to(m)


    # 冲刺路径：只画起终点连线（App 的箭头口径），带序号标记
    sprint_layer = folium.FeatureGroup(name='冲刺路径（前 6 次）', show=True).add_to(m)
    for idx, e in enumerate(top6):
        i0, i1 = e['i0'], e['i1']
        pts = [[float(trk.lat[i0]), float(trk.lon[i0])], [float(trk.lat[i1]), float(trk.lon[i1])]]
        col = '#ffd400' if idx == 0 else '#ff7a45'
        tip = ('<b>冲刺 ' + str(idx + 1) + '</b><br>' + fc.hms(e['start_s']) + '<br>' +
               format(e['dist_m'], '.0f') + ' m  ' + format(e['dur_s'], '.0f') + ' s<br>峰值 ' +
               format(e['peak_kmh'], '.1f') + ' km/h')
        folium.PolyLine(pts, color=col, weight=5, opacity=0.95, tooltip=tip,
                        popup=folium.Popup(tip, max_width=220)).add_to(sprint_layer)
        folium.CircleMarker([float(trk.lat[i0]), float(trk.lon[i0])], radius=3, color='#ffffff',
                            weight=1, fill=True, fill_color=col, fill_opacity=1).add_to(sprint_layer)

    speed_layer = folium.FeatureGroup(name='速度着色轨迹', show=True).add_to(m)
    for a in range(0, n - 1, 20):
        b = min(a + 21, n)
        pts = [[float(la), float(lo)] for la, lo in zip(trk.lat[a:b], trk.lon[a:b])]
        if len(pts) < 2:
            continue
        vmean = float(np.nanmean(v_kmh[a:b]))
        hrm = float(np.nanmean(hr[a:b])) if np.isfinite(hr[a:b]).any() else float('nan')
        tip = ('t+' + fc.hms(trk.tsec[a]) + '  ' + format(vmean, '.1f') + ' km/h' +
               ('  心率 ' + format(hrm, '.0f') + ' bpm' if hrm == hrm else ''))
        folium.PolyLine(pts, color=speed_color(vmean), weight=1.8, opacity=0.6, tooltip=tip).add_to(speed_layer)

    lap_layer = folium.FeatureGroup(name='计圈分段', show=False).add_to(m)
    bounds = list(offs) + [n]
    for i, lap in laps.iterrows():
        a = int(bounds[i])
        tip = ('第 ' + str(int(lap['lap'])) + ' 圈：' + fc.hms(lap['duration_s']) + '  ' +
               format(float(lap['distance_m']) / 1000.0, '.2f') + ' km  均心率 ' + str(int(lap['avg_hr'])))
        folium.CircleMarker([float(trk.lat[a]), float(trk.lon[a])], radius=7, color='#39d7ff', weight=3,
                            fill=True, fill_color='#0b1220', fill_opacity=0.9, tooltip=tip).add_to(lap_layer)

    heat_layer = folium.FeatureGroup(name='跑动热图', show=False)
    HeatMap([[float(la), float(lo)] for la, lo in zip(trk.lat, trk.lon)], radius=11, blur=9,
            min_opacity=0.3, max_zoom=21).add_to(heat_layer)
    heat_layer.add_to(m)

    folium.Polygon([[float(la), float(lo)] for la, lo in fld.corners], color='#37d67a', weight=2,
                   fill=False, dash_array='10 6',
                   tooltip='场地 ' + format(fld.long_side_m, '.1f') + ' x ' + format(fld.short_side_m, '.1f') + ' m').add_to(m)
    # 冲刺箭头最后加入，保证渲染在轨迹之上
    sprint_layer.add_to(m)

    W = fld.long_side_m
    z_self = 100.0 * float((u < 30.0).mean())
    z_mid = 100.0 * float(((u >= 30.0) & (u < W - 30.0)).mean())
    z_opp = 100.0 * float((u >= W - 30.0).mean())
    avg_peak = float(np.mean([e['peak_kmh'] for e in top6])) if top6 else 0.0
    avg_dist = float(np.mean([e['dist_m'] for e in top6])) if top6 else 0.0
    ui = ('''<div style="position:fixed;top:14px;left:14px;z-index:9999;background:linear-gradient(180deg,rgba(11,18,32,.96),rgba(17,28,49,.96));'''
          '''color:#e8eefc;border:1px solid #24314a;border-radius:14px;padding:14px 16px;'''
          '''font:13px/1.7 "Microsoft YaHei",sans-serif;min-width:300px;box-shadow:0 8px 28px rgba(0,0,0,.45)">'''
          '''<div style="font-size:19px;font-weight:700;color:#ffd400">冲刺路径</div>'''
          '''<div style="color:#8ea0c0;font-size:11px;margin-bottom:8px">全场 · 阈值 15 公里/时</div>'''
          '''<div style="display:flex;justify-content:space-between;margin-bottom:6px">'''
          '''<div><div style="color:#8ea0c0;font-size:11px">平均</div><div style="font-size:17px;font-weight:700">AVGPEAK 公里/时</div></div>'''
          '''<div><div style="color:#8ea0c0;font-size:11px">距离</div><div style="font-size:17px;font-weight:700">AVGDIST 米</div></div>'''
          '''<div style="text-align:right"><div style="color:#8ea0c0;font-size:11px">冲刺</div>'''
          '''<div style="font-size:24px;font-weight:700;color:#ff7a45">NSPRINT 次</div></div></div>'''
          '''<hr style="border-color:#24314a;margin:8px 0">'''
          '''<div style="color:#8ea0c0;font-size:11px">三分区停留（自己 / 中场 / 对手）</div>'''
          '''<div style="font-weight:600">ZSELF% / ZMID% / ZOPP%</div>'''
          '''<hr style="border-color:#24314a;margin:8px 0">'''
          '''<div style="color:#8ea0c0;font-size:11px">课次概览</div>'''
          '''<div>时长 DUR · 官方 DIST km · 平均心率 HR bpm</div>'''
          '''<div>运动时间（&gt;=3 公里/时）MOVING 分钟</div>'''
          '''<div style="color:#8ea0c0;font-size:11px;margin-top:8px">图层可开关；冲刺箭头可点击查看距离与峰值速度</div></div>''')
    ui = (ui.replace('AVGPEAK', format(avg_peak, '.1f')).replace('AVGDIST', format(avg_dist, '.0f'))
            .replace('NSPRINT', str(len(top6)))
            .replace('ZSELF', format(z_self, '.0f')).replace('ZMID', format(z_mid, '.0f'))
            .replace('ZOPP', format(z_opp, '.0f'))
            .replace('DUR', fc.hms(float(dt.sum()))).replace('DIST', format(trk.official_km, '.2f'))
            .replace('HR', format(float(np.nanmean(hr)), '.0f'))
            .replace('MOVING', format(float(dt[moving].sum()) / 60.0, '.0f')))
    m.get_root().html.add_child(folium.Element(ui))
    folium.LayerControl(collapsed=True).add_to(m)

    raw = m.get_root().render()
    mapping = {}
    def repl(match):
        token = match.group(0)
        if token not in mapping:
            mapping[token] = 'dsh%04x' % len(mapping)
        return mapping[token]
    raw = re.sub(r'[0-9a-f]{32}', repl, raw)
    raw = re.sub(r'<span>Leaflet \|[^<]*</span>', '<span>Leaflet</span>', raw)
    raw = re.sub(r', created \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b', '', raw)
    out = OUT / (out_name or ('football_' + stem.replace('polar_', '') + '_app_style.html'))
    out.write_text(raw, encoding='utf-8')
    print('[App 风格网页]', out.name, '| 冲刺(前6)', len(top6), '| 单次事件', len(ev),
          '| 文件', round(len(raw) / 1024), 'KB')
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='App 风格交互网页')
    ap.add_argument('--stem', default=STEM)
    a = ap.parse_args()
    main(a.stem)
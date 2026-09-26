# -*- coding: utf-8 -*-
"""分析三：folium 交互式轨迹网页（速度着色 / 计圈 / 冲刺点 / 热力层）。"""
from pathlib import Path
import sys

import json
import folium
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc
from lap_segments import load_all, STEM

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
OUT.mkdir(parents=True, exist_ok=True)


def kmh_to_color(v_kmh):
    """速度 -> 颜色（与热力图配色一致的 turbo 近似）。"""
    stops = [(0.0, '#30123b'), (3.0, '#4145ab'), (7.0, '#4675ed'), (11.0, '#39a2fc'),
             (15.0, '#1bcfd4'), (19.0, '#25eca8'), (24.0, '#cfe11a'), (30.0, '#fbb938'), (36.0, '#f5691f')]
    if v_kmh <= stops[0][0]:
        return stops[0][1]
    for (v0, c0), (v1, c1) in zip(stops[:-1], stops[1:]):
        if v_kmh <= v1:
            t = (v_kmh - v0) / (v1 - v0)
            a = tuple(int(c0[i:i + 2], 16) for i in (1, 3, 5))
            b = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
            return '#%02x%02x%02x' % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))
    return stops[-1][1]


def _freeze_element_ids(html: str) -> str:
    """把 folium 随机元素 ID 固定化，使重复运行产生相同文件（便于版本管理对比）。"""
    global re
    import re
    mapping = {}
    def repl(match):
        token = match.group(0)
        if token not in mapping:
            mapping[token] = 'dsh%04x' % len(mapping)
        return mapping[token]
    return re.sub(r'[0-9a-f]{32}', repl, html)


def main(stem=STEM, chunk_sec: int = 20, out_name: str = 'football_2026-09-19_interactive.html') -> Path:
    trk, laps, fld, u, w, v_kmh, dt, scale, offs = load_all(stem)
    n = len(trk.tsec)
    hr = np.asarray(trk.hr, dtype=float)
    bounds = list(offs) + [n]
    lat0, lon0 = float(trk.lat.mean()), float(trk.lon.mean())
    m = folium.Map(location=[lat0, lon0], zoom_start=19, tiles=None, control_scale=True,
                   prefer_canvas=True)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery', name='卫星影像', max_zoom=21, max_native_zoom=19, overlay=False, control=True).add_to(m)


    lap_layer = folium.FeatureGroup(name='计圈分段').add_to(m)
    for i, lap in laps.iterrows():
        a, b = int(bounds[i]), int(bounds[i + 1])
        hr_seg = hr[a:b]
        hr_seg = hr_seg[np.isfinite(hr_seg)]
        pop = ('<b>第 ' + str(int(lap['lap'])) + ' 圈</b><br>'
               '时长 ' + fc.hms(lap['duration_s']) + '<br>'
               '官方距离 ' + str(round(float(lap['distance_m']) / 1000.0, 2)) + ' km<br>'
               '平均心率 ' + str(int(lap['avg_hr'])) + ' / 最大 ' + str(int(lap['max_hr'])))
        folium.CircleMarker([float(trk.lat[a]), float(trk.lon[a])], radius=9, color='#00e5ff',
                            weight=3, fill=True, fill_color='#003b45', fill_opacity=0.9,
                            tooltip='第 ' + str(int(lap['lap'])) + ' 圈开始', popup=folium.Popup(pop, max_width=240)).add_to(lap_layer)

    overlay_png = OUT / 'heat_overlay.png'
    overlay_json = OUT / 'heat_overlay.json'
    if overlay_png.exists() and overlay_json.exists():
        meta = json.loads(overlay_json.read_text(encoding='utf-8'))
        import base64
        b64 = base64.b64encode(overlay_png.read_bytes()).decode('ascii')
        heat_layer = folium.FeatureGroup(name='跑动热图（KDE 停留密度）', show=True).add_to(m)
        folium.raster_layers.ImageOverlay(
            image='data:image/png;base64,' + b64,
            bounds=[[meta['bounds'][0][0], meta['bounds'][0][1]], [meta['bounds'][1][0], meta['bounds'][1][1]]],
            opacity=0.85, interactive=False, cross_origin=False, zindex=2,
            alt='跑动热图').add_to(heat_layer)

    speed_layer = folium.FeatureGroup(name='速度着色轨迹（默认隐藏）', show=False).add_to(m)
    for a in range(0, n - 1, chunk_sec):
        b = min(a + chunk_sec + 1, n)
        vs = v_kmh[a:b]
        if len(vs) == 0:
            continue
        vmean = float(np.nanmean(vs))
        pts = [[float(la), float(lo)] for la, lo in zip(trk.lat[a:b], trk.lon[a:b])]
        if len(pts) < 2:
            continue
        m_ = np.mean(hr[a:b]) if np.isfinite(hr[a:b]).any() else float('nan')
        tip = ('t+' + fc.hms(trk.tsec[a]) + '  ' + str(round(vmean, 1)) + ' km/h' +
               ('  心率 ' + str(int(round(m_))) + ' bpm' if m_ == m_ else ''))
        folium.PolyLine(pts, color=kmh_to_color(vmean), weight=4, opacity=0.9, tooltip=tip).add_to(speed_layer)

    start_pt = [float(trk.lat[0]), float(trk.lon[0])]
    end_pt = [float(trk.lat[-1]), float(trk.lon[-1])]
    folium.Marker(start_pt, tooltip='起点', popup=folium.Popup('起点 ' + trk.t0_utc.astimezone(fc.CST).strftime('%H:%M:%S'), max_width=200),
                  icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker(end_pt, tooltip='终点', popup=folium.Popup('终点 ' + (trk.t0_utc.astimezone(fc.CST) + pd.Timedelta(seconds=int(trk.tsec[-1]))).strftime('%H:%M:%S'), max_width=200),
                  icon=folium.Icon(color='red', icon='stop')).add_to(m)

    ev = fc.sprint_events(v_kmh, dt, thr_kmh=15.0, min_s=0.5)
    cum = np.cumsum(dt)
    sprint_layer = folium.FeatureGroup(name='高速事件 (>15 km/h)', show=False).add_to(m)
    for e in ev:
        idx = int(np.searchsorted(cum, e['start_s'] + 0.1))
        idx = min(idx, n - 1)
        folium.CircleMarker([float(trk.lat[idx]), float(trk.lon[idx])], radius=6, color='#ffd400', weight=2,
                            fill=True, fill_color='#ff8c00', fill_opacity=0.95,
                            tooltip=str(e['peak_kmh']) + ' km/h  ' + str(e['dur_s']) + ' s',
                            popup=folium.Popup('峰值 ' + str(e['peak_kmh']) + ' km/h<br>持续 ' + str(e['dur_s']) + ' s<br>距离 ' + str(e['dist_m']) + ' m', max_width=200)).add_to(sprint_layer)



    corners = [[float(la), float(lo)] for la, lo in fld.corners]
    folium.Polygon(corners, color='#00ff88', weight=3, fill=False, dash_array='8 6',
                   tooltip='标定场地 ' + str(round(fld.long_side_m, 1)) + ' x ' + str(round(fld.short_side_m, 1)) + ' m').add_to(m)

    legend = ('<div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:rgba(20,20,20,.86);'
              'color:#fff;padding:12px 14px;border-radius:8px;font:13px/1.6 Microsoft YaHei,sans-serif;min-width:250px">'
              '<b>2026-09-19 足球课次</b><br>'
              '时长 ' + fc.hms(trk.tsec[-1] - trk.tsec[0]) + ' | 官方 ' + str(round(trk.official_km, 2)) + ' km<br>'
              '平均心率 ' + str(int(np.nanmean(hr))) + ' bpm<br>'
              '场地 ' + str(round(fld.long_side_m, 1)) + ' x ' + str(round(fld.short_side_m, 1)) + ' m<br>'
              '<hr style="border-color:#555">'
              '轨迹按速度着色：<br>'
              '<span style="color:#4145ab">■</span> &lt;3 &nbsp; '
              '<span style="color:#4675ed">■</span> 3-7 &nbsp; '
              '<span style="color:#39a2fc">■</span> 7-11 &nbsp; '
              '<span style="color:#1bcfd4">■</span> 11-15 &nbsp; '
              '<span style="color:#fbb938">■</span> &gt;15 km/h<br>'
              '<span style="color:#00e5ff">●</span> 计圈起点 &nbsp; '
              '<span style="color:#ffd400">●</span> 高速事件<br>'
              '数据来源 手表平台导出（GPX/TCX/CSV）</div>')
    m.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(collapsed=False).add_to(m)
    raw = m.get_root().render()
    raw = _freeze_element_ids(raw)
    raw = re.sub(r'<span>Leaflet \|[^<]*</span>', '<span>Leaflet</span>', raw)
    raw = re.sub(r', created \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b', '', raw)
    out = OUT / out_name
    out.write_text(raw, encoding='utf-8')
    print('[交互网页]', out, '轨迹点', n, '速度分段', int(np.ceil(n / chunk_sec)), '高速事件', len(ev))
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='folium 交互式轨迹网页')
    ap.add_argument('--stem', default=STEM, help='课次文件名（不含扩展名）')
    a = ap.parse_args()
    main(a.stem, out_name='football_' + a.stem.replace('polar_', '') + '_interactive.html')
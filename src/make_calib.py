# -*- coding: utf-8 -*-
"""生成球场四角标定页：卫星底图 + 该课次轨迹叠加，供人工点击四角。"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
NS = {'g': 'http://www.topografix.com/GPX/1/1'}
TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>球场四角标定</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{margin:0;height:100%%;font-family:"Microsoft YaHei",sans-serif}
  #map{position:absolute;inset:0}
  #panel{position:absolute;top:10px;right:10px;z-index:1000;background:rgba(255,255,255,.95);
         padding:12px 14px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.35);max-width:340px;font-size:13px}
  #panel h3{margin:0 0 6px;font-size:15px}
  #panel ol{margin:6px 0;padding-left:20px}
  #panel button{margin-top:6px;padding:5px 10px;border:1px solid #888;border-radius:5px;background:#f4f4f4;cursor:pointer}
  #verdict{margin-top:8px;font-weight:bold}
  .ok{color:#0a7a2f}.warn{color:#b06a00}.bad{color:#b00020}
  #out{position:absolute;left:10px;bottom:10px;z-index:1000;background:rgba(0,0,0,.72);color:#fff;
       padding:8px 10px;border-radius:6px;font-size:12px;max-width:660px;word-break:break-all}
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <h3>球场四角标定</h3>
  <div>11 人制标准场应为 <b>105 m x 68 m</b>。按顺序点击球场的四个角：</div>
  <ol><li>左下角</li><li>右下角</li><li>右上角</li><li>左上角</li></ol>
  <div>第一次点击的角度决定长边方向。红色细线是该课次的跑动轨迹，可核对场地范围。</div>
  <button id="reset">重标（清空）</button>
  <div id="verdict"></div>
</div>
<div id="out">点击 0 / 4</div>
<script>
const TRK = __TRACK__;
const map = L.map('map', {zoomControl: true}).setView([__LAT__, __LON__], 19);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {maxZoom: 21, maxNativeZoom: 19}).addTo(map);
L.polyline(TRK, {color:'#ff3b3b', weight:1.4, opacity:0.85}).addTo(map);
const corners = [];
const marks = [];
let poly = null;
const out = document.getElementById('out');
const verdict = document.getElementById('verdict');
function dist(a, b) {
  const R = 6371008.8, d2r = Math.PI / 180;
  const p1 = a.lat * d2r, p2 = b.lat * d2r;
  const dp = p2 - p1, dl = (b.lng - a.lng) * d2r;
  const h = Math.sin(dp/2)**2 + Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function fmt(v){ return v.toFixed(6); }
function render() {
  out.textContent = '点击 ' + corners.length + ' / 4  ' +
    corners.map(function(c, i){ return 'P'+(i+1)+' ('+fmt(c.lat)+','+fmt(c.lng)+')'; }).join('  ');
}
function reset() {
  marks.forEach(function(mm){ map.removeLayer(mm); });
  marks.length = 0; corners.length = 0;
  if (poly) { map.removeLayer(poly); poly = null; }
  verdict.textContent = ''; verdict.className = '';
  render();
}
map.on('click', function(e) {
  if (corners.length >= 4) return;
  const c = {lat: e.latlng.lat, lng: e.latlng.lng};
  corners.push(c);
  marks.push(L.circleMarker(c, {radius: 7, color:'#ffcc00', fillColor:'#e8890c', fillOpacity:1, weight:3}).addTo(map));
  render();
  if (corners.length === 4) {
    poly = L.polygon(corners, {color:'#ffcc00', weight:3, fillOpacity:0.12}).addTo(map);
    const L1 = dist(corners[0], corners[1]), L2 = dist(corners[1], corners[2]);
    const lngSide = Math.max(L1, L2), shtSide = Math.min(L1, L2);
    const eL = 100 * Math.abs(lngSide - 105) / 105, eW = 100 * Math.abs(shtSide - 68) / 68;
    let cls = 'ok', msg = '尺寸良好（与 105x68 偏差 <5%）';
    if (Math.max(eL, eW) > 15) { cls = 'bad'; msg = '偏差较大，建议重标'; }
    else if (Math.max(eL, eW) > 5) { cls = 'warn'; msg = '轻微偏差（5%-15%）'; }
    verdict.className = cls;
    verdict.textContent = '长边 ' + lngSide.toFixed(1) + ' m（误差 ' + eL.toFixed(1) + '%），短边 ' +
                          shtSide.toFixed(1) + ' m（误差 ' + eW.toFixed(1) + '%）。' + msg;
  }
});
document.getElementById('reset').addEventListener('click', reset);
window.__getCorners = function(){ return corners; };
render();
</script>
</body>
</html>
'''


def build(lat0, lon0, track, out_path):
    html = TEMPLATE.replace('%%', '%')
    html = html.replace('__TRACK__', str(track).replace(' ', ''))
    html = html.replace('__LAT__', repr(lat0)).replace('__LON__', repr(lon0))
    out_path.write_text(html, encoding='utf-8')
    return out_path


def main():
    ap = argparse.ArgumentParser(description='生成球场四角标定页')
    ap.add_argument('--stem', default=None, help='用于叠加轨迹的课次，缺省取 data/raw 里最新的 GPX')
    ap.add_argument('--out', default=None, help='输出 HTML 路径')
    ap.add_argument('--pitch', nargs=2, type=float, default=None, metavar=('LAT', 'LON'),
                    help='不叠加轨迹时，直接指定场地中心经纬度')
    ap.add_argument('--name', default='football pitch', help='场地名称，写入标定 JSON')
    ap.add_argument('--corners', nargs=8, type=float, default=None, metavar='VAL',
                    help='把标定结果写入 field_calibration.json：lat1 lon1 lat2 lon2 lat3 lon3 lat4 lon4')
    a = ap.parse_args()

    if a.corners:
        import football_core as fc
        v = a.corners
        corners = [(v[i], v[i + 1]) for i in range(0, 8, 2)]
        lat0 = sum(c[0] for c in corners) / 4.0
        lon0 = sum(c[1] for c in corners) / 4.0
        fld = fc.Field(corners=corners, lon0=lon0, lat0=lat0, long_side_m=0.0, short_side_m=0.0, orthogonality=0.0)
        out = RAW / 'field_calibration.json'
        fld.to_json(out, a.name)
        print('calibration written ->', out)
        print('long', round(fld.long_side_m, 2), 'm  short', round(fld.short_side_m, 2), 'm  ortho', round(fld.orthogonality, 4))
        return 0

    track = []
    if a.pitch:
        lat0, lon0 = a.pitch
    else:
        gpx = RAW / (a.stem + '.gpx')
        if not gpx.exists():
            print('找不到 ' + str(gpx) + '，请用 --pitch LAT LON 指定中心')
            return 1
        pts = ET.parse(gpx).getroot().findall('.//g:trkpt', NS)
        lat = [float(p.get('lat')) for p in pts]
        lon = [float(p.get('lon')) for p in pts]
        lat0, lon0 = sum(lat) / len(lat), sum(lon) / len(lon)
        track = [[round(lat[i], 6), round(lon[i], 6)] for i in range(0, len(lat), 5)]
    out = Path(a.out) if a.out else (RAW / 'calib_field.html')
    build(lat0, lon0, track, out)
    print('标定页 ->', out, '中心', round(lat0, 6), round(lon0, 6), '轨迹点', len(track))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
# -*- coding: utf-8 -*-
"""生成合成示例数据（虚构坐标），让用户无需真实数据即可跑通全流程。"""
import argparse
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'

# 虚构场地中心（不指向任何真实地点）
LAT0, LON0 = 30.000000, 120.000000
PITCH_LONG, PITCH_SHORT = 105.0, 68.0


def simulate(total_min=100.0, break_min=(45.0, 49.0), warmup_min=2.0, seed=7):
    """模拟一名中前卫/前腰的比赛跑动，返回逐秒采样。"""
    rng = random.Random(seed)
    n = int(total_min * 60)
    x = PITCH_LONG * 0.5
    y = PITCH_SHORT * 0.5
    heading = rng.uniform(0, 2 * math.pi)
    rows = []
    dist = 0.0
    sprint_left = 0
    for t in range(n):
        minute = t / 60.0
        in_break = break_min[0] <= minute < break_min[1]
        warm = minute < warmup_min
        if in_break:
            speed = rng.uniform(0.0, 0.6)
        elif warm:
            speed = rng.uniform(0.8, 2.2)
        elif sprint_left > 0:
            # 冲刺爆发：连续 6-10 秒高速，方向基本不变
            speed = rng.uniform(5.8, 7.4)
            sprint_left -= 1
        else:
            r = rng.random()
            if r < 0.18:
                speed = rng.uniform(0.0, 0.8)
            elif r < 0.66:
                speed = rng.uniform(0.6, 1.8)
            elif r < 0.90:
                speed = rng.uniform(1.8, 3.0)
            elif r < 0.97:
                speed = rng.uniform(3.0, 4.6)
            else:
                speed = rng.uniform(4.6, 6.4)
            if rng.random() < 0.0018:
                sprint_left = rng.randint(6, 10)
                heading = rng.uniform(0, 2 * math.pi)
        # 位置更新：中前卫倾向中路，下半场前提
        progress = 0.0 if minute < break_min[0] else (minute - break_min[1]) / max(total_min - break_min[1], 1)
        target_x = PITCH_LONG * (0.42 + 0.28 * progress)
        target_y = PITCH_SHORT * 0.5
        heading += rng.uniform(-0.55, 0.55)
        if rng.random() < 0.25:
            heading = math.atan2(target_y - y, target_x - x) + rng.uniform(-0.7, 0.7)
        x += speed * math.cos(heading)
        y += speed * math.sin(heading)
        # 反弹回场内（把跑出边界的部分折回）
        if x < 2 or x > PITCH_LONG - 2:
            heading = math.pi - heading
            x = min(max(x, 2), PITCH_LONG - 2)
        if y < 2 or y > PITCH_SHORT - 2:
            heading = -heading
            y = min(max(y, 2), PITCH_SHORT - 2)
        dist += speed
        # 心率：随速度上升 + 随时间漂移 + 噪声；休息时下降
        if in_break:
            hr = 118 + rng.uniform(-6, 8)
        elif warm:
            hr = 120 + speed * 12 + rng.uniform(-5, 6)
        else:
            drift = 6.0 * progress
            hr = 132 + speed * 11 + drift + rng.uniform(-6, 7)
        rows.append({'t': t, 'x': x, 'y': y, 'speed_kmh': speed * 3.6, 'hr': max(95, min(196, hr)),
                     'dist_m': dist, 'alt': 20 + rng.uniform(-1.5, 1.5)})
    return rows


def to_latlon(x, y):
    """场地坐标（x 长边朝东、y 短边朝北）-> 经纬度。"""
    east = x - PITCH_LONG / 2.0
    north = y - PITCH_SHORT / 2.0
    lat = LAT0 + north / 110574.0
    lon = LON0 + east / (111320.0 * math.cos(math.radians(LAT0)))
    return lat, lon


def write_gpx(rows, path, t0):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="sample-data">',
             '  <trk><name>示例比赛</name><trkseg>']
    for r in rows:
        lat, lon = to_latlon(r['x'], r['y'])
        ts = (t0 + timedelta(seconds=r['t'])).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        parts.append('    <trkpt lat="%.5f" lon="%.5f"><ele>%.1f</ele><time>%s</time></trkpt>'
                     % (round(lat, 5), round(lon, 5), r['alt'], ts))
    parts += ['  </trkseg></trk>', '</gpx>']
    path.write_text(chr(10).join(parts), encoding='utf-8')


def write_tcx(rows, path, t0):
    lap_len = len(rows) // 4
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">',
             '  <Activities><Activity Sport="Other">',
             '    <Id>' + t0.strftime('%Y-%m-%dT%H:%M:%S.000Z') + '</Id>']
    for li in range(4):
        chunk = rows[li * lap_len:(li + 1) * lap_len] if li < 3 else rows[3 * lap_len:]
        if not chunk:
            continue
        hrs = [c['hr'] for c in chunk]
        d0 = chunk[0]['dist_m'] / 1000.0
        d1 = chunk[-1]['dist_m'] / 1000.0
        parts.append('    <Lap StartTime="%s">' % (t0 + timedelta(seconds=chunk[0]['t'])).strftime('%Y-%m-%dT%H:%M:%S.000Z'))
        parts.append('      <TotalTimeSeconds>%d.0</TotalTimeSeconds>' % len(chunk))
        parts.append('      <DistanceMeters>%.1f</DistanceMeters>' % ((d1 - d0) * 1000.0))
        parts.append('      <Calories>%d</Calories>' % int(len(chunk) * 0.32))
        parts.append('      <AverageHeartRateBpm><Value>%d</Value></AverageHeartRateBpm>' % int(sum(hrs) / len(hrs)))
        parts.append('      <MaximumHeartRateBpm><Value>%d</Value></MaximumHeartRateBpm>' % int(max(hrs)))
        parts.append('      <Track>')
        for c in chunk:
            lat, lon = to_latlon(c['x'], c['y'])
            ts = (t0 + timedelta(seconds=c['t'])).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            parts.append('        <Trackpoint><Time>%s</Time><Position><LatitudeDegrees>%.5f</LatitudeDegrees>'
                         '<LongitudeDegrees>%.5f</LongitudeDegrees></Position>'
                         '<DistanceMeters>%.1f</DistanceMeters>'
                         '<HeartRateBpm><Value>%d</Value></HeartRateBpm></Trackpoint>'
                         % (ts, round(lat, 5), round(lon, 5), c['dist_m'], int(c['hr'])))
        parts += ['      </Track>', '    </Lap>']
    parts += ['  </Activity></Activities>', '</TrainingCenterDatabase>']
    path.write_text(chr(10).join(parts), encoding='utf-8')


def write_csv(rows, path, date_str, start_hm):
    total_min = len(rows) / 60.0
    total_km = rows[-1]['dist_m'] / 1000.0
    hrs = [r['hr'] for r in rows]
    avg_speed = total_km / (total_min / 60.0)
    head1 = ('Name,Sport,Date,Start time,Duration,Total distance (km),Average heart rate (bpm),Average speed (km/h),'
             'Max speed (km/h),Average pace (min/km),Max pace (min/km),Calories')
    head2 = 'Sample Player,SOCCER,%s,%s,%02d:%02d:%02d,%.2f,%d,%.1f,%.1f,15:00,02:20,%d' % (
        date_str, start_hm, int(total_min // 60), int(total_min % 60), len(rows) % 60, total_km,
        int(sum(hrs) / len(hrs)), avg_speed, max(r['speed_kmh'] for r in rows), int(len(rows) * 0.32))
    head3 = 'Sample rate,Time,HR (bpm),Speed (km/h),Pace (min/km),Cadence,Altitude (m),Stride length (m),Distances (m),Temperatures (C),Power (W)'
    lines = [head1, head2, head3]
    for r in rows:
        hh = r['t'] // 3600
        mm = (r['t'] % 3600) // 60
        ss = r['t'] % 60
        lines.append('1,%02d:%02d:%02d,%d,%.1f,,%.0f,,%.1f,30.0,' % (hh, mm, ss, int(r['hr']), r['speed_kmh'], r['alt'], r['dist_m']))
    path.write_text(chr(10).join(lines), encoding='utf-8')


def register_pitch(name='示例球场（合成数据）'):
    """把合成场地的四角登记到球场注册表，让示例数据也能跑到精确场地坐标。"""
    import sys
    sys.path.insert(0, str(ROOT / 'src'))
    import pitches as pitch_registry
    # 角点顺序遵循 Field 约定：P1->P2 是短边（球门线），P1->P4 是长边
    corners = [to_latlon(0.0, 0.0), to_latlon(0.0, PITCH_SHORT),
               to_latlon(PITCH_LONG, PITCH_SHORT), to_latlon(PITCH_LONG, 0.0)]
    pitch_registry.add(name, corners, note='由 make_sample_data.py 合成，仅用于演示', make_active=True)
    print('  已登记示例球场：' + name)


def main():
    ap = argparse.ArgumentParser(description='生成合成示例课次')
    ap.add_argument('--stem', default='sample_football_session')
    ap.add_argument('--minutes', type=float, default=100.0)
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    rows = simulate(total_min=a.minutes)
    t0 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    write_gpx(rows, RAW / (a.stem + '.gpx'), t0)
    write_tcx(rows, RAW / (a.stem + '.tcx'), t0)
    write_csv(rows, RAW / (a.stem + '.csv'), '2026-06-01', '10:00:00')
    register_pitch()
    km = rows[-1]['dist_m'] / 1000.0
    print('已生成示例数据 ->', RAW)
    print('  ' + a.stem + '.gpx / .tcx / .csv')
    print('  时长 %.0f 分钟，距离 %.2f km，平均心率 %d' % (len(rows) / 60.0, km, sum(r['hr'] for r in rows) / len(rows)))
    print('  坐标是虚构的（30.000000, 120.000000 附近），可直接用来试跑，然后换成你自己的数据')


if __name__ == '__main__':
    main()
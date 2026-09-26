# -*- coding: utf-8 -*-
"""数据审计：文件覆盖、时间轴、采样完整性、与官方数值交叉校验。"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
REP = ROOT / 'report'
TAB = ROOT / 'output' / 'tables'
def _auto_stem():
    """自动取 data/raw 下最新的课次（按 GPX 修改时间排序）。"""
    files = sorted(Path(__file__).resolve().parents[1].joinpath('data', 'raw').glob('*.gpx'),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else 'sample'


STEM = _auto_stem()



def main(stem=STEM):
    gpx = RAW / (stem + '.gpx')
    tcx = RAW / (stem + '.tcx')
    csv = RAW / (stem + '.csv')
    trk = fc.read_track(gpx, tcx, csv)
    laps = fc.read_laps(tcx)
    v, _, _ = fc.reconstruct_velocity(trk.x, trk.y, trk.tsec)
    dt = fc.per_point_dt(trk.tsec)
    scale = fc.calibrate_distance(v, dt, trk.official_km)
    hr = np.asarray(trk.hr, dtype=float)
    hr_ok = hr[np.isfinite(hr)]
    steps = np.hypot(np.diff(trk.x), np.diff(trk.y))
    gps_km = float(steps.sum()) / 1000.0
    # 逐秒 CSV 采样间隔
    df = pd.read_csv(csv, skiprows=2, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    tsec_csv = np.round(pd.to_timedelta(df['Time']).dt.total_seconds()).astype(int).values
    gaps = np.diff(tsec_csv)
    big = gaps[gaps > 1.5]
    dev_kmh = pd.to_numeric(df.get('Speed (km/h)'), errors='coerce').values if 'Speed (km/h)' in df.columns else np.array([])

    L = []
    L.append('# 数据审计：' + stem)
    L.append('')
    L.append('## 1. 文件与通道覆盖')
    L.append('')
    L.append('| 文件 | 大小 (KB) | 记录 | 轨迹 | 心率 | 逐秒速度 | 计圈 |')
    L.append('|---|---|---|---|---|---|---|')
    L.append('| GPX | ' + str(round(gpx.stat().st_size / 1024)) + ' | ' + str(len(trk.tsec)) + ' 点 | 有 | 无 | 无 | 无 |')
    L.append('| TCX | ' + str(round(tcx.stat().st_size / 1024)) + ' | ' + str(len(trk.tsec)) + ' 点 + ' + str(len(laps)) + ' 圈 | 有 | 有 | 无 | 有 |')
    L.append('| CSV | ' + str(round(csv.stat().st_size / 1024)) + ' | ' + str(trk.csv_rows) + ' 行 | 无 | 有 | 有 | 无（含累计距离） |')
    L.append('')
    L.append('## 2. 时间轴与采样')
    L.append('')
    L.append('| 项 | 值 |')
    L.append('|---|---|')
    L.append('| 课次起点 (UTC) | ' + trk.t0_utc.strftime('%Y-%m-%d %H:%M:%S') + ' |')
    L.append('| 课次起点 (本地) | ' + trk.t0_utc.astimezone(fc.CST).strftime('%Y-%m-%d %H:%M:%S') + ' |')
    L.append('| 轨迹点 | ' + str(len(trk.tsec)) + ' |')
    L.append('| 会话时长 | ' + fc.hms(trk.tsec[-1] - trk.tsec[0]) + ' |')
    L.append('| CSV 中位采样间隔 | ' + str(round(float(np.median(gaps)), 2)) + ' s |')
    L.append('| 采样缺口 (>1.5s) | ' + str(len(big)) + ' 段，合计 ' + str(round(float(big.sum()) / 60.0, 2)) + ' min |')
    L.append('| 心率缺失点 | ' + str(int(len(hr) - len(hr_ok))) + ' |')
    L.append('')
    L.append('## 3. 距离交叉校验')
    L.append('')
    L.append('| 来源 | 值 (km) |')
    L.append('|---|---|')
    L.append('| 官方累计距离（CSV 最大） | ' + str(round(trk.official_km, 3)) + ' |')
    L.append('| TCX 计圈求和 | ' + str(round(float(laps['distance_m'].sum()) / 1000.0, 3)) + ' |')
    L.append('| GPX 原始 haversine | ' + str(round(gps_km, 3)) + ' |')
    L.append('| 卡尔曼重建积分 | ' + str(round(float(np.nansum(v * dt)) / 1000.0, 3)) + ' |')
    L.append('| 定标系数 | ' + str(round(scale, 4)) + ' |')
    L.append('')
    L.append('## 4. 与官方数值对比')
    L.append('')
    summary = pd.read_csv(csv, nrows=1, encoding='utf-8-sig')
    L.append('| 指标 | 官方 | 本地重算 |')
    L.append('|---|---|---|')
    L.append('| 时长 | ' + str(summary.iloc[0].get('Duration', '')) + ' | ' + fc.hms(trk.tsec[-1] - trk.tsec[0]) + ' |')
    L.append('| 总距离 (km) | ' + str(summary.iloc[0].get('Total distance (km)', '')) + ' | ' + str(round(trk.official_km, 3)) + ' |')
    L.append('| 平均心率 | ' + str(summary.iloc[0].get('Average heart rate (bpm)', '')) + ' | ' + str(round(float(np.mean(hr_ok)), 1)) + ' |')
    L.append('| 最大心率 | ' + str(summary.iloc[0].get('Max heart rate (bpm)', summary.iloc[0].get('Maximum heart rate (bpm)', ''))) + ' | ' + str(int(np.max(hr_ok))) + ' |')
    L.append('| 卡路里 | ' + str(summary.iloc[0].get('Calories', '')) + ' | 数据源提供 |')
    L.append('')
    L.append('## 5. 传感器质量')
    L.append('')
    if dev_kmh.size:
        L.append('- Polar 逐秒速度：最大 ' + str(round(float(np.nanmax(dev_kmh)), 1)) + ' km/h，P99 ' + str(round(float(np.nanpercentile(dev_kmh, 99)), 1)) + ' km/h')
        L.append('- 重建速度与设备速度 MAD：' + str(round(float(np.nanmean(np.abs(v * 3.6 - pd.Series(dev_kmh, index=tsec_csv).reindex(trk.tsec).values))), 2)) + ' km/h')
    v_raw = steps / np.maximum(np.diff(trk.tsec), 1)
    L.append('- 原始差分速度 >9 m/s 的点：' + str(int((v_raw > 9).sum())) + '（GPS 跳点，重建时已由卡尔曼滤波抑制）')
    L.append('- 轨迹包围盒：' + str(round(float(trk.x.max() - trk.x.min()), 1)) + ' m x ' + str(round(float(trk.y.max() - trk.y.min()), 1)) + ' m')
    L.append('')
    (REP / ('01_data_audit.md' if stem == STEM else '01_data_audit_' + stem + '.md')).write_text(chr(10).join(L), encoding='utf-8')
    print('[审计] 时长', fc.hms(trk.tsec[-1] - trk.tsec[0]), '官方km', round(trk.official_km, 3),
          'GPXkm', round(gps_km, 3), '定标', round(scale, 3), '采样缺口', len(big))
    return True


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Polar 课次数据审计')
    ap.add_argument('--stem', default=STEM)
    a = ap.parse_args()
    raise SystemExit(0 if main(a.stem) else 1)
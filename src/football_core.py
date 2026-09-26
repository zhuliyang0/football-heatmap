# -*- coding: utf-8 -*-
"""Polar 足球课次分析核心模块：读取、滤波、场地标定、指标计算。"""
from __future__ import annotations
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

CST = timezone(timedelta(hours=8))
GPS_NS = {'g': 'http://www.topografix.com/GPX/1/1'}
TCX_NS = {'t': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}
M_PER_DEG_LAT = 110574.0
M_PER_DEG_LON = 111320.0
SPEED_BANDS = [(0.0, 3.0, '静止/慢走'), (3.0, 7.0, '走/慢跑'), (7.0, 11.0, '慢跑'),
               (11.0, 15.0, '快跑'), (15.0, 19.0, '高速'), (19.0, 99.0, '尖峰')]
HR_ZONES = [(0, 104, 'Z1'), (104, 125, 'Z2'), (125, 146, 'Z3'), (146, 166, 'Z4'), (166, 187, 'Z5'), (187, 999, 'Z6')]


class DataError(RuntimeError):
    """输入数据缺失或格式不可解析。"""


@dataclass
class Track:
    """GPX 轨迹与逐秒通道，时间基准为课次起点。"""
    t0_utc: datetime
    lat: np.ndarray
    lon: np.ndarray
    tsec: np.ndarray
    x: np.ndarray
    y: np.ndarray
    hr: np.ndarray
    speed_dev: np.ndarray
    cum_dist_m: np.ndarray
    csv_rows: int

    @property
    def official_km(self) -> float:
        return float(np.nanmax(self.cum_dist_m)) / 1000.0


@dataclass
class Field:
    """场地四角标定结果（WGS84 经纬度）与局部投影基。"""
    corners: list
    lon0: float
    lat0: float
    long_side_m: float
    short_side_m: float
    orthogonality: float
    _c: tuple = field(default=None, repr=False)

    def __post_init__(self) -> None:
        a, b, c, d = [self._to_local(la, lo) for la, lo in self.corners]
        ux, uy = b[0] - a[0], b[1] - a[1]
        vx, vy = d[0] - a[0], d[1] - a[1]
        su, sv = float(np.hypot(ux, uy)), float(np.hypot(vx, vy))
        self.short_side_m, self.long_side_m = su, sv
        self.orthogonality = float((ux / su) * (vx / sv) + (uy / su) * (vy / sv))
        self._c = ((a[0] + b[0] + c[0] + d[0]) / 4.0, (a[1] + b[1] + c[1] + d[1]) / 4.0,
                    ux / su, uy / su, vx / sv, vy / sv)

    def _to_local(self, la: float, lo: float) -> tuple:
        return ((lo - self.lon0) * M_PER_DEG_LON * np.cos(np.radians(self.lat0)),
                (la - self.lat0) * M_PER_DEG_LAT)

    def to_field(self, lat, lon):
        """经纬度 -> 场地坐标（x 沿长边 0..长, y 沿短边 0..短）。"""
        cx, cy, ex, ey, fx, fy = self._c
        X, Y = self._to_local(np.asarray(lat), np.asarray(lon))
        return ((X - cx) * fx + (Y - cy) * fy + self.long_side_m / 2.0,
                (X - cx) * ex + (Y - cy) * ey + self.short_side_m / 2.0)

    @property
    def bounds(self):
        return (self.long_side_m, self.short_side_m)

    @classmethod
    def from_track(cls, lat, lon, long_m: float = 105.0, short_m: float = 68.0) -> 'Field':
        """没有球场标定时，用轨迹自身估计一片标准尺寸场地（近似，精度受限）。

        做法：以轨迹质心为场地中心，用 PCA 主轴作为场地长轴方向，再合成四个角点。
        由于 GPS 漂移会撑大坐标包围盒，这种方法只能保证朝向与相对位置，不能保证绝对尺度；
        要精确结果请用 tools/calibrate_pitch.py 点四个角。

        @param lat: 纬度数组。
        @param lon: 经度数组。
        @param long_m: 场地长边（米）。
        @param short_m: 场地短边（米）。
        @returns: Field 实例。
        """
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        lat0, lon0 = float(lat.mean()), float(lon.mean())
        x = (lon - lon0) * M_PER_DEG_LON * np.cos(np.radians(lat0))
        y = (lat - lat0) * M_PER_DEG_LAT
        pts = np.column_stack([x - x.mean(), y - y.mean()])
        cov = np.cov(pts.T)
        evals, evecs = np.linalg.eigh(cov)
        long_axis = evecs[:, int(np.argmax(evals))]
        ang = np.arctan2(long_axis[1], long_axis[0])
        ca, sa = np.cos(ang), np.sin(ang)
        half_l, half_s = long_m / 2.0, short_m / 2.0
        corners_local = [(-half_l, -half_s), (half_l, -half_s), (half_l, half_s), (-half_l, half_s)]
        corners = []
        for dx, dy in corners_local:
            ex = dx * ca - dy * sa
            ny = dx * sa + dy * ca
            corners.append((lat0 + ny / M_PER_DEG_LAT,
                            lon0 + ex / (M_PER_DEG_LON * np.cos(np.radians(lat0)))))
        return cls(corners=corners, lon0=lon0, lat0=lat0, long_side_m=0.0, short_side_m=0.0, orthogonality=0.0)


    @staticmethod
    def from_json(path) -> 'Field':
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        return Field(corners=[tuple(p) for p in raw['corners']],
                     lon0=raw['lon0'], lat0=raw['lat0'],
                     long_side_m=raw.get('long_side_m', 0.0),
                     short_side_m=raw.get('short_side_m', 0.0),
                     orthogonality=raw.get('orthogonality', 0.0))

    def to_json(self, path, pitch_name: str = '') -> None:
        Path(path).write_text(json.dumps({
            'pitch_name': pitch_name,
            'corners': [[float(a), float(b)] for a, b in self.corners],
            'lon0': self.lon0, 'lat0': self.lat0,
            'order': 'P1 左下 / P2 右下 / P3 右上 / P4 左上（卫星图方位）',
            'long_side_m': round(self.long_side_m, 2),
            'short_side_m': round(self.short_side_m, 2),
            'orthogonality': round(self.orthogonality, 5),
        }, ensure_ascii=False, indent=2), encoding='utf-8')


def discover_session(raw_dir) -> list:
    """列出目录下所有可用课次（同名 GPX/TCX/CSV 三件套）。"""
    raw = Path(raw_dir)
    out = []
    for gpx in sorted(raw.glob('*.gpx')):
        stem = gpx.with_suffix('')
        tcx, csv = stem.with_suffix('.tcx'), stem.with_suffix('.csv')
        out.append({'stem': stem.name, 'gpx': gpx, 'tcx': tcx if tcx.exists() else None,
                    'csv': csv if csv.exists() else None,
                    'complete': tcx.exists() and csv.exists()})
    return out


def read_track(gpx_path, tcx_path=None, csv_path=None) -> Track:
    """读取 手表平台 导出的 GPX/TCX/CSV，统一到同一时间基准。"""
    root = ET.parse(gpx_path).getroot()
    pts = root.findall('.//g:trkpt', GPS_NS)
    if not pts:
        raise DataError('GPX 中没有 trkpt：' + str(gpx_path))
    lat = np.array([float(p.get('lat')) for p in pts])
    lon = np.array([float(p.get('lon')) for p in pts])
    t0 = None
    if tcx_path is not None and Path(tcx_path).exists():
        troot = ET.parse(tcx_path).getroot()
        first = troot.find('.//t:Trackpoint/t:Time', TCX_NS)
        if first is not None:
            t0 = datetime.strptime(first.text, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    if t0 is None:
        t0 = datetime.strptime(pts[0].find('g:time', GPS_NS).text, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    tsec = np.round([(datetime.strptime(p.find('g:time', GPS_NS).text, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc) - t0).total_seconds() for p in pts]).astype(int)
    lat0, lon0 = float(lat.mean()), float(lon.mean())
    x = (lon - lon0) * M_PER_DEG_LON * np.cos(np.radians(lat0))
    y = (lat - lat0) * M_PER_DEG_LAT
    hr = np.full(len(tsec), np.nan)
    spd = np.full(len(tsec), np.nan)
    cum = np.full(len(tsec), np.nan)
    rows = 0
    if csv_path is not None and Path(csv_path).exists():
        df = pd.read_csv(csv_path, skiprows=2, encoding='utf-8-sig')
        df.columns = [c.strip() for c in df.columns]
        if 'Time' not in df.columns:
            raise DataError('CSV 缺少 Time 列，Polar 导出格式可能已变化：' + str(csv_path))
        rows = len(df)
        idx = np.round(pd.to_timedelta(df['Time']).dt.total_seconds()).astype(int)
        for col, target in (('HR (bpm)', hr), ('Speed (km/h)', spd), ('Distances (m)', cum)):
            if col in df.columns:
                s = pd.Series(pd.to_numeric(df[col], errors='coerce').values, index=idx)
                s = s[~s.index.duplicated()]
                target[:] = s.reindex(tsec).values
    x, y = np.asarray(x), np.asarray(y)
    return Track(t0_utc=t0, lat=lat, lon=lon, tsec=tsec, x=x, y=y, hr=hr,
                 speed_dev=spd, cum_dist_m=cum, csv_rows=rows)


def read_laps(tcx_path) -> pd.DataFrame:
    """读取 TCX 计圈（Polar 的自动/手动分段）。"""
    root = ET.parse(tcx_path).getroot()
    rows = []
    for i, lap in enumerate(root.findall('.//t:Activity/t:Lap', TCX_NS), 1):
        def txt(tag):
            el = lap.find('t:' + tag, TCX_NS)
            return float(el.text) if el is not None and el.text else float('nan')
        rows.append({'lap': i, 'start_utc': lap.get('StartTime'),
                     'duration_s': txt('TotalTimeSeconds'), 'distance_m': txt('DistanceMeters'),
                     'calories': txt('Calories'),
                     'avg_hr': txt('AverageHeartRateBpm/t:Value') if lap.find('t:AverageHeartRateBpm/t:Value', TCX_NS) is not None else float('nan'),
                     'max_hr': txt('MaximumHeartRateBpm/t:Value') if lap.find('t:MaximumHeartRateBpm/t:Value', TCX_NS) is not None else float('nan'),
                     'max_speed_ms': txt('MaximumSpeed')})
    if not rows:
        raise DataError('TCX 中没有计圈数据：' + str(tcx_path))
    return pd.DataFrame(rows)


def lap_offsets(laps: pd.DataFrame, t0_utc: datetime) -> np.ndarray:
    """把每个计圈的起始时间换算成相对课次起点的秒数。"""
    out = []
    for s in laps['start_utc']:
        dt = datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
        out.append(int(round((dt - t0_utc).total_seconds())))
    return np.array(out, dtype=int)


def reconstruct_velocity(x, y, tsec, sigma_a: float = 3.0, sigma_z: float = 4.0):
    """恒速卡尔曼滤波重建速度（位置差分噪声极大，必须先滤波）。"""
    z = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    xv = np.zeros(4)
    P = np.eye(4) * 100.0
    F = np.array([[1.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    Q = sigma_a ** 2 * np.array([[0.25, 0.0, 0.5, 0.0], [0.0, 0.25, 0.0, 0.5], [0.5, 0.0, 1.0, 0.0], [0.0, 0.5, 0.0, 1.0]])
    H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    R = np.eye(2) * sigma_z ** 2
    out = np.zeros((len(z), 4))
    for i in range(len(z)):
        xv = F @ xv
        P = F @ P @ F.T + Q
        K = P @ H.T @ np.linalg.inv(H @ P @ H.T + R)
        xv = xv + K @ (z[i] - H @ xv)
        P = (np.eye(4) - K @ H) @ P
        out[i] = xv
    v = np.hypot(out[:, 2], out[:, 3])
    if len(v) >= 15:
        v = savgol_filter(v, 15, 2)
    return v, out[:, 0], out[:, 1]


def jitter_gps(lat, lon, quantum_deg=1e-5, seed: int = 20260919):
    """抖动量化的 GPS 坐标，消除点阵旋转产生的摩尔纹。

    Polar 导出的经纬度只保留 5 位小数（约 1 m 台阶），把这种点阵旋转到场地坐标系后会产生
    规则条纹。量化误差在本台阶内近似均匀，因此加半个台阶的均匀抖动再做投影是无偏的。

    @param lat: 纬度数组。
    @param lon: 经度数组。
    @param quantum_deg: 量化步长（度），默认 1e-5 对应 GPX 精度。
    @param seed: 随机种子，保证结果可复现。
    @returns: (lat_jittered, lon_jittered) 元组。
    """
    rng = np.random.default_rng(seed)
    return (np.asarray(lat, dtype=float) + (rng.random(len(lat)) - 0.5) * quantum_deg,
            np.asarray(lon, dtype=float) + (rng.random(len(lon)) - 0.5) * quantum_deg)


def match_mask(tsec, cfg) -> np.ndarray:
    """比赛窗口掩码：剔除热身、中场休息与赛后走动。"""
    t = np.asarray(tsec, dtype=float) / 60.0
    m = t >= float(cfg.get('warmup_end_min', 0.0))
    m &= t <= float(cfg.get('match_end_min', 1e9))
    brk = cfg.get('half_break_min')
    if brk:
        m &= ~((t >= float(brk[0])) & (t <= float(brk[1])))
    return m


DEFAULT_MATCH_WINDOW = {'warmup_end_min': 3.0, 'half_break_min': [52.0, 58.0], 'second_half_from_min': 58.0,
                        'match_end_min': 110.0, 'switch_ends': False}


def resolve_pitch_name(raw_dir, stem: str) -> str:
    """球场显示名：向导答案优先，其次注册表默认球场，最后给占位名。"""
    info = read_match_info(raw_dir, stem, only_analysis_keys=True)
    if info.get('pitch_name'):
        return str(info['pitch_name'])
    legacy = legacy_calibration(raw_dir).get('pitch_name')
    if legacy:
        return str(legacy)
    try:
        import pitches as pitch_registry
        return str(pitch_registry.get(None)['name'])
    except Exception:
        return '示例球场'


def legacy_calibration(raw_dir) -> dict:
    """读取旧版单球场标定文件；不存在时返回空字典。"""
    p = Path(raw_dir) / 'field_calibration.json'
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}


def match_window_config(raw_dir, stem: str) -> dict:
    """比赛窗口配置：向导答案优先，其次旧标定文件，最后内置默认值。"""
    cfg = dict(DEFAULT_MATCH_WINDOW)
    legacy = legacy_calibration(raw_dir).get('match_window')
    if legacy:
        cfg.update(legacy)
    info = read_match_info(raw_dir, stem, only_analysis_keys=True)
    if info:
        cfg['switch_ends'] = bool(info.get('switch_ends', cfg['switch_ends']))
        if info.get('half_break_min'):
            cfg['half_break_min'] = info['half_break_min']
            cfg['second_half_from_min'] = info['half_break_min'][1]
        for key in ('warmup_end_min', 'match_end_min'):
            if info.get(key):
                cfg[key] = info[key]
    return cfg


ANALYSIS_KEYS = ('pitch_name', 'session_type', 'switch_ends', 'attack_first_half', 'attack_second_half',
                 'half_break_min', 'warmup_end_min', 'match_end_min')


def read_match_info(raw_dir, stem: str, only_analysis_keys: bool = False) -> dict:
    """读取本场比赛信息向导写下的配置；不存在时返回空字典。

    @param raw_dir: data/raw 目录。
    @param stem: 课次文件名（不含扩展名）。
    @returns: 向导答案字典，缺失键由调用方给默认值。
    """
    p = Path(raw_dir) / (stem + '.match_info.json')
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}
    if only_analysis_keys:
        return {k: v for k, v in data.items() if k in ANALYSIS_KEYS}
    return data


def read_observations(raw_dir, stem: str) -> dict:
    """读取主观观察（自报位置等）。仅用于事后对照，分析流程不得调用。"""
    p = Path(raw_dir) / (stem + '.observations.json')
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}


def attack_frame(x, tsec, info: dict, W: float, second_from_min: float = 58.0):
    """按向导答案把两个半场归一化到「进攻方向 = x 增大」。

    上半场进攻南门（x 减小）时镜像上半场；下半场同理。这样无论是否换边，
    归一化后的 x=0 始终是自家球门、x=W 是进攻球门。

    @param x: 场地坐标系下的 x（x=0 为南门）。
    @param tsec: 秒偏移数组。
    @param info: 向导答案，键 attack_first_half / attack_second_half。
    @param W: 场地长度（米）。
    @param second_from_min: 下半场起始分钟，默认 58。
    @returns: 归一化后的 x 数组。
    """
    x = np.asarray(x, dtype=float).copy()
    t = np.asarray(tsec, dtype=float) / 60.0
    first_south = str(info.get('attack_first_half', 'north')).lower() in ('south', 'nan', '南门', '南')
    second_south = str(info.get('attack_second_half', 'north')).lower() in ('south', 'nan', '南门', '南')
    m1 = t < second_from_min
    if first_south:
        x[m1] = W - x[m1]
    if second_south:
        x[~m1] = W - x[~m1]
    return x


def normalize_halves(x, tsec, cfg, W: float):
    """按进攻方向统一坐标系：下半场换边时镜像 x，使两半场朝向一致。"""
    x = np.asarray(x, dtype=float).copy()
    if cfg.get('switch_ends'):
        t = np.asarray(tsec, dtype=float) / 60.0
        second = t >= float(cfg.get('second_half_from_min', 0.0))
        x[second] = W - x[second]
    return x


def per_point_dt(tsec) -> np.ndarray:
    """每个轨迹点代表的时长（秒），异常间隔按 1 s 处理。"""
    t = np.asarray(tsec)
    dt = np.ones(len(t))
    if len(t) > 1:
        dt[1:] = np.diff(t)
    return np.where((dt <= 0) | (dt > 10), 1.0, dt)


def calibrate_distance(v_mps, dt, official_km: float) -> float:
    """用官方距离给重建速度积分定标，返回系数。"""
    raw = float(np.nansum(v_mps * dt)) / 1000.0
    if raw <= 0:
        raise DataError('重建速度积分为 0，无法定标')
    return official_km / raw


def hms(seconds) -> str:
    s = int(round(float(seconds)))
    return str(s // 3600).zfill(2) + ':' + str((s % 3600) // 60).zfill(2) + ':' + str(s % 60).zfill(2)


def segment_summary(mask, v_kmh, dt, u, w, hr, scale, official_span_km=None) -> dict:
    """对给定掩码区间计算一套跑动/强度指标。"""
    m = np.asarray(mask)
    dur = float(dt[m].sum())
    dist = float(np.nansum(v_kmh[m] * dt[m]) / 3600.0) * scale
    hi = float(np.nansum(v_kmh[m][v_kmh[m] >= 15.0] * dt[m][v_kmh[m] >= 15.0]) / 3600.0) * scale
    hr_m = hr[m]
    hr_v = hr_m[np.isfinite(hr_m)]
    return {
        'duration_s': dur,
        'duration_hms': hms(dur),
        'distance_km': round(dist, 3),
        'avg_speed_kmh': round(dist / (dur / 3600.0), 2) if dur > 0 else float('nan'),
        'hi15_km': round(hi, 3),
        'hi15_pct': round(100.0 * hi / dist, 2) if dist > 0 else float('nan'),
        'avg_hr': round(float(np.mean(hr_v)), 1) if hr_v.size else float('nan'),
        'max_hr': int(np.max(hr_v)) if hr_v.size else 0,
        'min_hr': int(np.min(hr_v)) if hr_v.size else 0,
        'mean_x_m': round(float(np.mean(u[m])), 1) if m.any() else float('nan'),
        'mean_y_m': round(float(np.mean(w[m])), 1) if m.any() else float('nan'),
        'sd_x_m': round(float(np.std(u[m])), 1) if m.any() else float('nan'),
        'sd_y_m': round(float(np.std(w[m])), 1) if m.any() else float('nan'),
        'distance_per_beat_m': round(dist * 1000.0 / (float(np.sum(hr_v)) / 60.0), 3) if hr_v.size else float('nan'),
        'distance_per_min_m': round(dist * 1000.0 / (dur / 60.0), 1) if dur > 0 else float('nan'),
    }


def sprint_events(v_kmh, dt, thr_kmh: float = 15.0, min_s: float = 0.5) -> list:
    """识别高速/冲刺事件（连续超阈值且持续 >= min_s）。"""
    fast = np.asarray(v_kmh) >= thr_kmh
    ev = []
    i = 0
    while i < len(fast):
        if fast[i]:
            j = i
            while j + 1 < len(fast) and fast[j + 1]:
                j += 1
            d = float(dt[i:j + 1].sum())
            if d >= min_s:
                ev.append({'start_s': int(np.asarray(dt).cumsum()[i] - d), 'dur_s': round(d, 2),
                           'peak_kmh': round(float(np.max(v_kmh[i:j + 1])), 2),
                           'dist_m': round(float(np.sum(np.asarray(v_kmh)[i:j + 1] * np.asarray(dt)[i:j + 1]) / 3.6), 1)})
            i = j + 1
        else:
            i += 1
    return ev


def band_table(v_kmh, dt, scale) -> pd.DataFrame:
    """速度档距离/时长表。"""
    rows = []
    for lo, hi, name in SPEED_BANDS:
        m = (v_kmh >= lo) & (v_kmh < hi)
        rows.append({'速度档': str(lo) + '-' + str(hi) + ' km/h', '名称': name,
                     '时长_min': round(float(dt[m].sum() / 60.0), 2),
                     '距离_km': round(float(np.nansum(v_kmh[m] * dt[m]) / 3600.0) * scale, 3)})
    return pd.DataFrame(rows)


def hr_zone_table(hr) -> pd.DataFrame:
    """心率区时长占比表。"""
    rows = []
    h = np.asarray(hr)
    n = int(np.isfinite(h).sum())
    for lo, hi, name in HR_ZONES:
        m = (h >= lo) & (h < hi)
        rows.append({'心率区': name, '区间': str(lo) + '-' + str(hi), '秒': int(m.sum()),
                     '占比_pct': round(100.0 * float(m.sum()) / n, 2) if n else 0.0})
    return pd.DataFrame(rows)


def coupling_table(v_kmh, hr, dt, edges=None) -> pd.DataFrame:
    """速度分箱后的心率响应与每搏距离（心率-速度耦合）。"""
    if edges is None:
        edges = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0])
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (v_kmh >= lo) & (v_kmh < hi) & np.isfinite(hr)
        if m.sum() < 20:
            continue
        d = float(dt[m].sum())
        dist_m = float(np.sum(v_kmh[m] * dt[m]) / 3.6)
        beats = float(np.sum(hr[m] * dt[m] / 60.0))
        rows.append({'速度区间_kmh': str(lo) + '-' + str(hi), '秒数': int(d),
                     '平均心率': round(float(np.mean(hr[m])), 1),
                     '心率标准差': round(float(np.std(hr[m])), 1),
                     '每次心跳位移_m': round(dist_m / beats, 3) if beats > 0 else float('nan')})
    return pd.DataFrame(rows)


def drift_summary(blocks: pd.DataFrame) -> pd.DataFrame:
    """分块心率漂移：同速度区间下的心率变化（需要 blocks 含各块速度区间心率）。"""
    return blocks


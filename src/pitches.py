# -*- coding: utf-8 -*-
"""球场注册表：多片球场的标定集中管理，供向导选择。"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
REGISTRY = DATA / 'pitches.json'
LEGACY = DATA / 'raw' / 'field_calibration.json'
DEFAULT_NAME = '示例球场'


def _load() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding='utf-8'))
    return {'active': DEFAULT_NAME, 'pitches': {}}


def _save(reg: dict) -> None:
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding='utf-8')


def migrate() -> dict:
    """把旧的单球场标定导入注册表（幂等）。"""
    reg = _load()
    if reg['pitches'] or not LEGACY.exists():
        return reg
    old = json.loads(LEGACY.read_text(encoding='utf-8'))
    name = old.get('pitch_name') or DEFAULT_NAME
    reg['pitches'][name] = {
        'corners': old['corners'], 'lon0': old['lon0'], 'lat0': old['lat0'],
        'long_side_m': old.get('long_side_m'), 'short_side_m': old.get('short_side_m'),
        'orthogonality': old.get('orthogonality'),
        'note': old.get('orientation', ''), 'match_window': old.get('match_window'),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    reg['active'] = reg.get('active') or name
    _save(reg)
    return reg


def names() -> list:
    """返回已注册球场名（按录入顺序）。"""
    return list(migrate()['pitches'].keys())


def get(name=None) -> dict:
    """取某片球场的标定；name 为空时取 active。"""
    reg = migrate()
    key = name or reg.get('active')
    if key not in reg['pitches']:
        if not reg['pitches']:
            raise KeyError('还没有任何球场标定，请先运行 新场地标定.bat')
        key = next(iter(reg['pitches']))
    data = dict(reg['pitches'][key])
    data['name'] = key
    return data


def resolve_name(name=None) -> str:
    """把可能为空/不存在的球场名解析为注册表里的有效名称。"""
    reg = migrate()
    if name and name in reg['pitches']:
        return name
    return reg.get('active') or next(iter(reg['pitches']), DEFAULT_NAME)


def add(name: str, corners, note: str = '', make_active: bool = False) -> dict:
    """新增或覆盖一片球场。"""
    import football_core as fc
    lat0 = sum(c[0] for c in corners) / len(corners)
    lon0 = sum(c[1] for c in corners) / len(corners)
    fld = fc.Field(corners=[tuple(c) for c in corners], lon0=lon0, lat0=lat0,
                   long_side_m=0.0, short_side_m=0.0, orthogonality=0.0)
    reg = migrate()
    reg['pitches'][name] = {'corners': [list(c) for c in corners], 'lon0': lon0, 'lat0': lat0,
                            'long_side_m': round(fld.long_side_m, 2),
                            'short_side_m': round(fld.short_side_m, 2),
                            'orthogonality': round(fld.orthogonality, 5), 'note': note,
                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    if make_active or not reg.get('active'):
        reg['active'] = name
    _save(reg)
    return reg['pitches'][name]


def set_active(name: str) -> None:
    """指定默认球场。"""
    reg = migrate()
    if name in reg['pitches']:
        reg['active'] = name
        _save(reg)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    import argparse
    ap = argparse.ArgumentParser(description='球场注册表')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--add', metavar='NAME')
    ap.add_argument('--corners', nargs=8, type=float, metavar='VAL')
    ap.add_argument('--note', default='')
    ap.add_argument('--active', metavar='NAME')
    a = ap.parse_args()
    if a.active:
        set_active(a.active)
        print('默认球场 ->', a.active)
        return 0
    if a.add and a.corners:
        v = a.corners
        info = add(a.add, [(v[i], v[i + 1]) for i in range(0, 8, 2)], a.note)
        print('已添加球场：' + a.add + '  ' + str(info['long_side_m']) + ' x ' + str(info['short_side_m']) + ' m')
        return 0
    reg = migrate()
    print('默认球场：' + str(reg.get('active')))
    for i, (name, info) in enumerate(reg['pitches'].items(), 1):
        print('  ' + str(i) + '. ' + name + '  ' + str(info.get('long_side_m')) + ' x ' +
              str(info.get('short_side_m')) + ' m  ' + str(info.get('note', '')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
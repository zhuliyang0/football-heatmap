# -*- coding: utf-8 -*-
"""比赛信息向导：把数据里看不出来的信息问清楚，写成本场配置 JSON。"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
def _auto_stem():
    """自动取 data/raw 下最新的课次（按 GPX 修改时间排序）。"""
    files = sorted(Path(__file__).resolve().parents[1].joinpath('data', 'raw').glob('*.gpx'),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else 'sample'


STEM = _auto_stem()


QUESTIONS = [
    ('pitch_name', '在哪片球场踢的（输入序号；0=添加新球场）', None),
    ('session_type', '本场类型（比赛/训练/对抗）', '比赛'),
    ('switch_ends', '上下半场是否换边（y/n）', 'y'),
    ('attack_first_half', '上半场进攻方向：南门还是北门（nan/bei）', 'bei'),
    ('attack_second_half', '下半场进攻方向：南门还是北门（留空=与上半场相反/相同自动判断）', ''),
    ('half_break', '中场休息起止分钟（如 52-58，留空=按数据自动判定）', ''),
    ('warmup_end_min', '热身结束/比赛开始于第几分钟（留空=自动）', ''),
    ('match_end_min', '比赛结束于第几分钟（留空=自动）', ''),
    ('declared_position_first', '你上半场打什么位置（可留空）', ''),
    ('declared_position_second', '你下半场打什么位置（可留空）', ''),
    ('played_full', '是否打满全场（y/n/换人说明）', 'y'),
    ('notes', '其它需要记录的（可留空）', ''),
]


def _num(v):
    """把输入解析成 float；空值、None、'None' 一律返回 None。"""
    s = '' if v is None else str(v).strip()
    if s in ('', 'none', 'None'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def ask(prompt, default):
    """单项提问，回车取默认值。"""
    tip = (' [' + default + ']') if default else ''
    try:
        ans = input('  ' + prompt + tip + '：').strip()
    except EOFError:
        ans = ''
    return ans if ans else (default or '')


def newest_stem() -> str:
    """返回 data/raw 下最新课次的文件名前缀（无 GPX 时回退默认值）。"""
    files = sorted(RAW.glob('*.gpx'), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else STEM


def wizard(stem=STEM, assume_yes: bool = False, answers=None) -> Path:
    """交互式采集本场信息，返回写入的 JSON 路径。answers 可注入预置答案（用于测试与批量）。"""
    info_path = RAW / (stem + '.match_info.json')
    old = json.loads(info_path.read_text(encoding='utf-8')) if info_path.exists() else {}
    calib = RAW / 'field_calibration.json'
    calib_data = json.loads(calib.read_text(encoding='utf-8')) if calib.exists() else {}
    import pitches as pitch_registry
    reg = pitch_registry.migrate()
    pitch_list = list(reg['pitches'].keys())
    defaults = dict(old)
    defaults.setdefault('pitch_name', reg.get('active') or calib_data.get('pitch_name', '未命名场地'))
    for i, nm in enumerate(pitch_list, 1):
        mark = '  <= 默认' if nm == reg.get('active') else ''
        print('  ' + str(i) + '. ' + nm + mark)
    if not pitch_list:
        print('  (暂无)')
    if answers is None:
        try:
            go = input('现在填写/更新本场信息吗？[Y/n]：').strip().lower()
        except EOFError:
            go = 'n'
        if go in ('n', 'no', '否'):
            print('  已跳过填写，沿用上次的值。')
            return info_path
    print('=' * 52)
    print(' 比赛信息向导：' + stem)
    print(' 直接回车 = 使用方括号里的默认值')
    print('=' * 52)
    seq = answers if answers is not None else {}
    out = {}
    for key, prompt, default in QUESTIONS:
        raw_default = seq.get(key, defaults.get(key, default if default is not None else ''))
        d = '' if raw_default is None else str(raw_default)
        if answers is not None:
            out[key] = d
            print('  ' + prompt + ' -> ' + (d if d else '(空)'))
            continue
        if assume_yes and key in ('switch_ends', 'played_full'):
            out[key] = d
            print('  ' + prompt + ' -> ' + d + '（--yes 自动确认）')
            continue
        if key == 'pitch_name' and answers is None:
            ans = ask(prompt, d)
            if ans.strip() == '0':
                new_name = input('  新球场名称：').strip()
                if new_name:
                    print('  请先运行 新场地标定.bat 点四个角，再执行：')
                    print('    python src\\pitches.py --add "' + new_name + '" --corners lat1 lon1 ... lat4 lon4')
                    pitch_registry.set_active(new_name)
                    ans = new_name
            elif ans.strip().isdigit() and 1 <= int(ans.strip()) <= len(pitch_list):
                ans = pitch_list[int(ans.strip()) - 1]
            pitch_registry.set_active(ans)
            out[key] = ans
            continue
        out[key] = ask(prompt, d)
    brk = out.get('half_break', '').strip()
    half = None
    if brk and '-' in brk:
        try:
            a, b = brk.replace('至', '-').split('-')[:2]
            half = [float(a), float(b)]
        except ValueError:
            half = None
    switch = str(out.get('switch_ends', 'y')).strip().lower() in ('y', 'yes', '是', 'true', '1')
    first = 'south' if str(out.get('attack_first_half', '')).strip().lower() in ('nan', 'south', '南门', '南') else 'north'
    second_raw = str(out.get('attack_second_half', '')).strip().lower()
    if second_raw in ('nan', 'south', '南门', '南'):
        second = 'south'
    elif second_raw in ('bei', 'north', '北门', '北'):
        second = 'north'
    else:
        second = ('north' if first == 'south' else 'south') if switch else first
    cfg = {
        'stem': stem,
        'pitch_name': out.get('pitch_name', '').strip(),
        'session_type': out.get('session_type', '比赛').strip(),
        'switch_ends': switch,
        'attack_first_half': first,
        'attack_second_half': second,
        'half_break_min': half,
        'warmup_end_min': _num(out.get('warmup_end_min')),
        'match_end_min': _num(out.get('match_end_min')),
        # 注意：自报位置属于主观信息，绝不写入本文件（见下方 observations）
        'filled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'analysis_keys': ['pitch_name', 'session_type', 'switch_ends', 'attack_first_half',
                          'attack_second_half', 'half_break_min', 'warmup_end_min', 'match_end_min'],
    }
    info_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    obs = {
        'stem': stem,
        'declared_position_first': out.get('declared_position_first', '').strip(),
        'declared_position_second': out.get('declared_position_second', '').strip(),
        'played_full': out.get('played_full', '').strip(),
        'notes': out.get('notes', '').strip(),
        'filled_at': cfg['filled_at'],
        'isolation_note': '本文件只用于事后对照，分析流程绝不读取它，以免主观描述影响数据推断的位置画像。',
    }
    (RAW / (stem + '.observations.json')).write_text(json.dumps(obs, ensure_ascii=False, indent=2), encoding='utf-8')
    print()
    print('已保存 ->', info_path.name)
    print('  换边：' + ('是' if switch else '否') + '｜上半场进攻：' + ('南门' if first == 'south' else '北门') +
          '｜下半场进攻：' + ('南门' if second == 'south' else '北门'))
    return info_path


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='比赛信息向导')
    ap.add_argument('--stem', default=None, help='课次文件名前缀，缺省用 data/raw 里最新的 GPX')
    ap.add_argument('--yes', action='store_true', help='对是否类问题自动确认默认值')
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    wizard(a.stem or newest_stem(), assume_yes=a.yes)
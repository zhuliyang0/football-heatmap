# -*- coding: utf-8 -*-
"""一键入口：扫描 data/raw 中的所有课次，跑完全部分析并生成索引页。"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import football_core as fc

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
RAW = ROOT / 'data' / 'raw'
REP = ROOT / 'report'
OUT = ROOT / 'output'
TAB = OUT / 'tables'
PACKAGES = ['numpy', 'pandas', 'scipy', 'matplotlib', 'gpxpy', 'folium']


def run(script, extra=None):
    cmd = [sys.executable, str(SRC / script)] + (extra or [])
    cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = cp.returncode == 0
    print(('  [OK]   ' if ok else '  [FAIL] ') + script)
    if not ok:
        for line in (cp.stderr or cp.stdout or '').strip().splitlines()[-8:]:
            print('         ' + line)
    return ok


def check_env():
    missing = []
    for pkg in PACKAGES:
        try:
            __import__(pkg)
        except Exception:
            missing.append(pkg)
    return missing


def build_index(sessions):
    lines = ['# 分析索引', '']
    lines.append('## 前端面板')
    lines.append('')
    if (OUT / 'panel.html').exists():
        lines.append('- [运动数据面板（跑动热图 / 冲刺路径 / 跑动数据）](../output/panel.html)')
    lines.append('')
    lines.append('## 交互网页')
    lines.append('')
    for s in sessions:
        if s.get('html'):
            lines.append('- [' + s['stem'] + ' 交互轨迹](../output/' + s['html'] + ')')
        if s.get('html_app'):
            lines.append('- [' + s['stem'] + ' App 风格冲刺路径与跑动热图](../output/' + s['html_app'] + ')')
    lines.append('')
    lines.append('## 课次')
    lines.append('')
    lines.append('| 课次 | 文件完整 | 分析状态 | 长度 (min) | 官方距离 (km) | 平均心率 | 分析时间 |')
    lines.append('|---|---|---|---|---|---|---|')
    for s in sessions:
        lines.append('| ' + s['stem'] + ' | ' + ('是' if s['complete'] else '否') + ' | ' + s['status'] +
                     ' | ' + str(s.get('dur_min', '')) + ' | ' + str(s.get('km', '')) + ' | ' + str(s.get('hr', '')) +
                     ' | ' + str(s.get('stamp', '')) + ' |')
    lines.append('')
    lines.append('## 交叉课次产出')
    lines.append('')
    for f in sorted((OUT / 'figures').glob('1[2-4]_multi_session*.png')):
        lines.append('- ![' + f.stem + '](../output/figures/' + f.name + ')')
    if (TAB / '07_multi_session.csv').exists():
        lines.append('- [07_multi_session.csv](../output/tables/07_multi_session.csv)')
    lines.append('')
    lines.append('## 报告')
    lines.append('')
    for f in sorted(REP.glob('*.md')):
        if f.name == '00_index.md':
            continue
        lines.append('- [' + f.name + '](' + f.name + ')')
    lines.append('')
    lines.append('## 图')
    lines.append('')
    for f in sorted((OUT / 'figures').glob('*.png')):
        lines.append('- ![' + f.stem + '](../output/figures/' + f.name + ')')
    lines.append('')
    (REP / '00_index.md').write_text(chr(10).join(lines), encoding='utf-8')


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description='Polar 足球课次一键分析')
    ap.add_argument('--stem', default=None, help='只分析指定课次文件名（不含扩展名）')
    ap.add_argument('--pitch', default=None, help='场地标定 JSON 路径，默认 data/raw/field_calibration.json')
    ap.add_argument('--skip-calib', action='store_true', help='跳过未标定场地的课次')
    args = ap.parse_args()

    for d in (ROOT / 'data' / 'raw', ROOT / 'output' / 'figures', ROOT / 'output' / 'tables', ROOT / 'report'):
        d.mkdir(parents=True, exist_ok=True)
    print('== 环境检查 ==')
    missing = check_env()
    if missing:
        print('  缺少依赖：' + ', '.join(missing))
        print('  请执行：python -m pip install ' + ' '.join(missing))
        return 2
    import matplotlib, numpy, pandas, scipy, folium
    try:
        import gpxpy
    except Exception:
        gpxpy = None
    print('  python ' + sys.version.split()[0] + '，依赖齐全')

    calib = Path(args.pitch) if args.pitch else (RAW / 'field_calibration.json')
    print('== 球场标定 ==')
    try:
        import pitches as pitch_registry
        reg = pitch_registry.migrate()
        if reg['pitches']:
            print('  默认球场：' + str(reg.get('active')))
            for nm, info in reg['pitches'].items():
                print('    - ' + nm + '  ' + str(info.get('long_side_m')) + ' x ' + str(info.get('short_side_m')) + ' m')
        else:
            print('  尚未登记球场：会用轨迹自动拟合近似场地（精度有限）')
            print('  要精确结果请运行：python tools/calibrate_pitch.py 然后 tools/register_pitch.py')
    except Exception as exc:
        print('  球场注册表读取失败，将使用自动拟合：' + str(exc)[:60])

    sessions = fc.discover_session(RAW)
    if args.stem:
        sessions = [s for s in sessions if s['stem'] == args.stem]
    if not sessions:
        print('data/raw 下没有找到 GPX 课次文件')
        return 3
    print('== 发现 ' + str(len(sessions)) + ' 个课次 ==')
    for s in sessions:
        print('  ' + s['stem'] + ('（完整）' if s['complete'] else '（缺少 TCX 或 CSV）'))

    results = []
    for s in sessions:
        print('== 分析 ' + s['stem'] + ' ==')
        ok_audit = run('audit.py', ['--stem', s['stem']])
        ok_heat = run('heatmap_kde.py')
        ok_halves = run('half_labels.py')
        ok_iso = run('verify_isolation.py')
        ok_profile = run('half_profile.py')
        ok_overlay = run('heatmap_overlay.py')
        ok_seg = run('lap_segments.py', ['--stem', s['stem']])
        ok_cpl = run('coupling.py', ['--stem', s['stem']])
        ok_map = run('interactive_map.py', ['--stem', s['stem']])
        ok_app = run('app_style.py', ['--stem', s['stem']])
        ok_appmap = run('app_style_map.py', ['--stem', s['stem']])
        ok_panel = run('frontend_app.py', ['--stem', s['stem']])
        ok_pages2 = run('frontend_pages.py')
        ok_pages = run('frontend_pages.py')
        info = {'stem': s['stem'], 'complete': s['complete'],
                'stamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status': '完成' if all([ok_heat, ok_halves, ok_profile, ok_overlay, ok_seg, ok_cpl, ok_map, ok_app, ok_appmap, ok_panel, ok_pages]) else '有错误',
                'html': 'football_' + s['stem'].replace('polar_', '') + '_interactive.html'}
        info['html'] = info['html'] if (OUT / info['html']).exists() else ''
        app_html = 'football_' + s['stem'].replace('polar_', '') + '_app_style.html'
        info['html_app'] = app_html if (OUT / app_html).exists() else ''
        try:
            trk = fc.read_track(s['gpx'], s['tcx'], s['csv'])
            info['dur_min'] = round(float(trk.tsec[-1] - trk.tsec[0]) / 60.0, 1)
            info['km'] = round(trk.official_km, 2)
            hr = trk.hr[[v == v for v in trk.hr]]
            info['hr'] = int(round(float(hr.mean()))) if len(hr) else ''
        except Exception as exc:
            info['status'] = '读取失败：' + str(exc)[:60]
        results.append(info)

    for s in sessions:
        run('archive_run.py', [s['stem']])
    print('== 跨课次趋势 ==')
    ok_trend = run('multi_trend.py')
    build_index(results)
    print('== 完成 ==')
    print('  索引：report/00_index.md')
    print('  交互网页：output/*_interactive.html')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
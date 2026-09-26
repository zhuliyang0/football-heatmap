# -*- coding: utf-8 -*-
"""把每次运行的 HTML 成果归档到桌面「足球数据」文件夹。"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
def _auto_stem():
    """自动取 data/raw 下最新的课次（按 GPX 修改时间排序）。"""
    files = sorted(Path(__file__).resolve().parents[1].joinpath('data', 'raw').glob('*.gpx'),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else 'sample'


STEM = _auto_stem()



def archive_dir() -> Path:
    """归档根目录：优先桌面；找不到桌面时回退项目目录。"""
    for candidate in (Path.home() / 'Desktop' / '足球数据',
                      Path.home() / 'OneDrive' / 'Desktop' / '足球数据',
                      Path.home() / '桌面' / '足球数据'):
        if candidate.parent.exists():
            return candidate
    return ROOT / '足球数据'


def archive(stem=STEM) -> Path:
    """复制本场 HTML 到 足球数据/<课次>/，并写一份带关键指标的 index.md。"""
    dest = archive_dir() / stem
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in sorted(OUT.glob('*.html')):
        shutil.copy2(f, dest / f.name)
        moved.append(f.name)
    for f in sorted((OUT / 'figures').glob('*.png')):
        shutil.copy2(f, dest / f.name)
    info = json.loads((OUT / 'heat_kde.json').read_text(encoding='utf-8')) if (OUT / 'heat_kde.json').exists() else {}
    labels = json.loads((OUT / 'half_labels.json').read_text(encoding='utf-8')) if (OUT / 'half_labels.json').exists() else []
    match = {}
    p = ROOT / 'data' / 'raw' / (stem + '.match_info.json')
    if p.exists():
        match = json.loads(p.read_text(encoding='utf-8'))
    L = ['# ' + stem + ' 结果归档', '', '归档时间：' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '']
    if match:
        L += ['## 本场信息', '', '| 项 | 值 |', '|---|---|',
              '| 球场 | ' + str(match.get('pitch_name', '')) + ' |',
              '| 类型 | ' + str(match.get('session_type', '')) + ' |',
              '| 换边 | ' + ('是' if match.get('switch_ends') else '否') + ' |',
              '| 上/下半场进攻方向 | ' + str(match.get('attack_first_half')) + ' / ' + str(match.get('attack_second_half')) + ' |', '']
    if labels:
        L += ['## 位置画像（数据推断 vs 自报，二者独立）', '', '| 半场 | 数据推断 | 你填写 | 依据 |', '|---|---|---|---|']
        for r in labels:
            L.append('| ' + r['half'] + ' | ' + r['label'] + ' | ' + str(r.get('declared', '')) + ' | ' + ' · '.join(r['why']) + ' |')
        L.append('')
    st = info.get('stats', {})
    if st:
        L += ['## 关键指标', '', '| 指标 | 值 |', '|---|---|',
              '| 比赛时长 (min) | ' + str(round(st.get('total_s', 0) / 60.0, 1)) + ' |',
              '| 剔除非比赛时间 (min) | ' + str(st.get('minutes_dropped')) + ' |',
              '| KDE 核宽 / 网格 | ' + str(st.get('sigma_m')) + ' m / ' + str(st.get('cell_m')) + ' m |', '']
    L += ['## 网页（双击打开）', ''] + ['- [' + n + '](' + n + ')' for n in moved if n.endswith('.html')]
    pngs = sorted(x.name for x in dest.glob('*.png'))
    if pngs:
        L += ['', '## 图片', ''] + ['- ![' + n + '](' + n + ')' for n in pngs]
    (dest / 'index.md').write_text(chr(10).join(L), encoding='utf-8')
    return dest


if __name__ == '__main__':
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    stem = sys.argv[1] if len(sys.argv) > 1 else STEM
    d = archive(stem)
    print('[归档]', d)
    print('  HTML', len(list(d.glob('*.html'))), '个 | PNG', len(list(d.glob('*.png'))), '张')
# -*- coding: utf-8 -*-
"""数据导入接口：把任意目录里的 GPX/TCX/CSV 复制进 data/raw 并统一命名。"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
SUPPORTED = ('.gpx', '.tcx', '.csv', '.fit')


def import_dir(src: Path, stem: str = None):
    """复制目录下支持的导出文件；同名同类文件自动加后缀避免覆盖。"""
    RAW.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(Path(src).iterdir()):
        if f.suffix.lower() not in SUPPORTED or not f.is_file():
            continue
        target = RAW / ((stem + f.suffix.lower()) if stem else f.name)
        if target.exists() and target.read_bytes() != f.read_bytes():
            target = RAW / ((stem or f.stem) + '_2' + f.suffix.lower())
        shutil.copy2(f, target)
        copied.append(target.name)
    return copied


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description='把导出文件复制进 data/raw')
    ap.add_argument('src', help='包含 GPX/TCX/CSV 的目录')
    ap.add_argument('--stem', default=None, help='统一改成这个名字前缀，例如 my_match_2026-06-01')
    a = ap.parse_args()
    names = import_dir(Path(a.src), a.stem)
    if not names:
        print('目录里没有找到 ' + ' / '.join(SUPPORTED) + ' 文件')
        return 1
    print('已导入 ' + str(len(names)) + ' 个文件到 data/raw：')
    for n in names:
        print('  ' + n)
    print('提示：同一场次请用同一前缀命名，然后运行 python src/run_all.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

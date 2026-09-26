# -*- coding: utf-8 -*-
"""球场注册表：列出、新增、切换默认球场。"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
runpy.run_path(str(Path(__file__).resolve().parents[1] / 'src' / 'pitches.py'), run_name='__main__')

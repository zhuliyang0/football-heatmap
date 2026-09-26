# -*- coding: utf-8 -*-
"""生成球场标定页：在卫星图上点击球场四个角，用于确定场地坐标。"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
runpy.run_path(str(Path(__file__).resolve().parents[1] / 'src' / 'make_calib.py'), run_name='__main__')

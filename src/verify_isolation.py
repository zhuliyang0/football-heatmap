# -*- coding: utf-8 -*-
"""隔离性验证：证明自报位置不会影响数据推断的位置画像。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import football_core as fc
import half_labels as hl


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    raw = ROOT / 'data' / 'raw'
    rows = []
    info = fc.read_match_info(raw, hl.STEM)
    obs = fc.read_observations(raw, hl.STEM)
    leaked = [k for k in info.keys() if k not in fc.ANALYSIS_KEYS and k not in ('stem', 'filled_at', 'analysis_keys')]
    rows.append(('分析输入只含白名单键', '是' if not leaked else '否：多出 ' + str(leaked), not leaked))
    rows.append(('match_info 不含自报位置', '是' if 'declared_position_first' not in info else '否', 'declared_position_first' not in info))
    rows.append(('自报位置另存 observations', '是' if obs else '无', True))

    # 关键验证：屏蔽/伪造自报位置，位置画像必须完全一致
    results_a = hl.main()
    labels_a = [(r['half'], r['label']) for r in results_a]
    obs_path = raw / (hl.STEM + '.observations.json')
    backup = obs_path.read_text(encoding='utf-8') if obs_path.exists() else None
    faked = {'declared_position_first': '中后卫', 'declared_position_second': '边后卫'}
    obs_path.write_text(json.dumps(faked, ensure_ascii=False), encoding='utf-8')
    results_b = hl.main()
    labels_b = [(r['half'], r['label']) for r in results_b]
    if backup is not None:
        obs_path.write_text(backup, encoding='utf-8')
    else:
        obs_path.unlink(missing_ok=True)
    same = labels_a == labels_b
    # 复原：用真实 observations 重算一次，避免伪造值残留在产出里
    hl.main()
    rows.append(('伪造自报位置后画像不变', '是' if same else '否 ' + str(labels_a) + ' vs ' + str(labels_b), same))

    lines = ['# 隔离性验证报告', '', '验证目标：用户自报的位置不得影响数据推断的位置画像。', '',
             '| 检查项 | 结果 | 判定 |', '|---|---|---|']
    for name, value, ok in rows:
        lines.append('| ' + name + ' | ' + str(value) + ' | ' + ('PASS' if ok else 'FAIL') + ' |')
    lines += ['', '## 隔离设计', '',
              '1. `data/raw/<课次>.match_info.json` 只保存影响计算的客观事实（球场、换边、进攻方向、比赛窗口）',
              '2. `data/raw/<课次>.observations.json` 保存主观信息（自报位置、备注），分析流程不读取',
              '3. 分析侧 `read_match_info(..., only_analysis_keys=True)` 按白名单裁剪，未知键无法进入计算',
              '4. 位置画像的输入只有五个量化指标：平均纵深、横向偏移、对方半场占比、本方深区占比、对方禁区占比',
              '5. 上述指标先独立算出并写盘，之后才读取自报位置做对照', '']
    ok_all = all(r[2] for r in rows)
    lines += ['结论：**' + ('全部通过' if ok_all else '存在失败项') + '**', '']
    (ROOT / 'report' / '12_isolation.md').write_text(chr(10).join(lines), encoding='utf-8')
    for name, value, ok in rows:
        print(('PASS' if ok else 'FAIL'), name, '->', value)
    return 0 if ok_all else 1


if __name__ == '__main__':
    raise SystemExit(main())
# -*- coding: utf-8 -*-
"""烘焙自检(内存中, 不写文件):
1. 每个字形: rect 区域应有墨迹(>140), bbox 尺寸 ~= (rw, rh) ±1; rect 外邻域应 <120
2. 打印 '中' 与几个样本字的 rect ASCII 形状, 肉眼可辨
"""
import os, sys
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "_zh_work"))
from font_bake_v6 import bake

atlas, glyphs = bake()

by_char = {g['ch']: g for g in glyphs}
assert len(by_char) == len(glyphs), "charset 有重复字形"

bad = 0
for g in glyphs:
    if g['cell'] is None or g['rw'] == 0:
        continue
    ry, rx, rh, rw = g['ry'], g['rx'], g['rh'], g['rw']
    reg = atlas[ry:ry + rh, rx:rx + rw]
    if reg.max() <= 140:
        print(f"[无墨] {g['ch']!r} gid={g['gid']} rect=({rx},{ry},{rw},{rh}) max={reg.max()}")
        bad += 1
        continue
    m = reg > 140
    ys, xs = np.where(m)
    bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    if abs(bh - rh) > 1 or abs(bw - rw) > 1:
        print(f"[bbox偏] {g['ch']!r} gid={g['gid']} rect=({rx},{ry},{rw},{rh}) ink={bw}x{bh}")
        bad += 1
    # rect 上/左边缘外 3px 应为背景
    if atlas[ry - 3, rx:rx + rw].max() >= 120 or atlas[ry:ry + rh, rx - 3].max() >= 120:
        print(f"[边缘污染] {g['ch']!r} gid={g['gid']} rect=({rx},{ry},{rw},{rh})")
        bad += 1
print(f"自检: {bad} 个异常 / {sum(1 for g in glyphs if g['cell'] is not None)} 个非空字形")

def art(g, tag):
    ry, rx, rh, rw = g['ry'], g['rx'], g['rh'], g['rw']
    print(f"--- {tag} {g['ch']!r} gid={g['gid']} rect=({rx},{ry},{rw},{rh}) "
          f"bx={g['bx']} by={g['by']} adv={g['adv']} ---")
    for y in range(ry - 2, ry + rh + 2):
        row = ""
        for x in range(rx - 2, rx + rw + 2):
            v = atlas[y, x]
            row += "#" if v > 170 else ("+" if v > 128 else ("." if v > 76 else " "))
        print(row)

for ch in "中文字库测试Aあ7":
    g = by_char.get(ch)
    if g and g['cell'] is not None:
        art(g, "样本")
    else:
        print(f"!!! 字符 {ch!r} 不在字库中")

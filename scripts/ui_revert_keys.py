# -*- coding: utf-8 -*-
"""把按键/按钮性质标签从中文还原为英文:
- Enter/ENTER/Cancel/Key/SPACE -> 原文
- 'Start Game (ENTER)' 改为 '开始游戏 (ENTER)' (保留句子翻译, 按键名保持英文)
就地替换: 在已打补丁的组件 raw 里按 [i32长度]+中文 搜索, 校验数量后换回英文。
"""
import json, os, struct, sys, collections
import UnityPy

BASE = r"D:\Steam\steamapps\common\Sixtar Gate STARTRAIL"

REVERT = {"Enter", "ENTER", "Cancel", "Key", "SPACE"}
REWORD = {"Start Game (ENTER)": "开始游戏 (ENTER)"}

d = json.load(open(os.path.join(BASE, "_zh_work", "ui_components.json"), encoding="utf8"))
# file -> pid -> [(orig_en, zh_after)]
todo = collections.defaultdict(lambda: collections.defaultdict(list))
for fname, e in d.items():
    for o in e["objs"]:
        if o["cls"] not in ("TextMeshProUGUI", "TextMeshPro", "Text"):
            continue
        for off, s in o["strs"]:
            if s in REVERT:
                zh = {"Enter": "回车", "ENTER": "回车", "Cancel": "取消",
                      "Key": "按键", "SPACE": "空格"}[s]
                todo[fname][o["pid"]].append((s, zh))
            elif s in REWORD:
                todo[fname][o["pid"]].append((s, "开始游戏（回车）"))

total_ok = total_fail = 0
for fname, pids in todo.items():
    path = os.path.join(BASE, fname.replace("/", os.sep))
    env = UnityPy.load(path)
    bypid = {o.path_id: o for o in env.objects}
    changed = False
    for pid, pairs in pids.items():
        o = bypid[pid]
        raw = o.get_raw_data()
        for en, zh in pairs:
            if en in REWORD:
                new = REWORD[en]
            else:
                new = en
            zb = zh.encode("utf8")
            pat = struct.pack("<i", len(zb)) + zb
            nb = new.encode("utf8")
            # 找出全部匹配位置 (含 4 字节对齐填充)
            positions = []
            i = raw.find(pat)
            while i != -1:
                positions.append(i)
                i = raw.find(pat, i + 1)
            if len(positions) != 1:
                print(f"  !! {os.path.basename(path)}#{pid}: {zh!r} 匹配 {len(positions)} 次 (期望1), 跳过")
                total_fail += 1
                continue
            off = positions[0]
            end = off + 4 + len(zb)
            pad_zh = (-len(zb)) % 4
            pad_new = (-len(nb)) % 4
            raw = (raw[:off] + struct.pack("<i", len(nb)) + nb + b"\x00" * pad_new
                   + raw[end + pad_zh:])
            total_ok += 1
            changed = True
        o.set_raw_data(raw)
    if changed:
        out = env.file.save()
        with open(path, "wb") as f:
            f.write(out)
        print(f"{os.path.basename(path)}: 已还原 {sum(1 for p in pids.values() for _ in p)} 处")

print(f"revert ok={total_ok} fail={total_fail}")

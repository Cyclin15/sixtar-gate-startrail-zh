# -*- coding: utf-8 -*-
"""UI 硬编码文本补丁:
- 从 ui_components.json 取 TMP/Text 组件中每个字符串出现位置 (file, pid, offset)
- 校验: raw[offset-4] 处 int32 长度 == len(old), raw[offset:...] == old 的 UTF-8
- 替换: 写新长度+新数据(4 字节对齐填充), 每对象从高偏移往低偏移处理避免位移
- 每个文件先备份到 _zh_work/backup/<name>.pre_ui
用法: python ui_patch.py [--dry]
"""
import json, os, re, struct, sys, shutil, collections
import UnityPy
from zh_ui import TRANS, SKIP

BASE = r"D:\Steam\steamapps\common\Sixtar Gate STARTRAIL"
DATA = os.path.join(BASE, "Sixtar Gate STARTRAIL_Data")
BK = os.path.join(BASE, "_zh_work", "backup")
DRY = "--dry" in sys.argv

def i32(d, o): return struct.unpack_from("<i", d, o)[0]

def meaningful(s):
    if not s or len(s) > 200: return False
    if not re.search(r"[A-Za-z]", s) and not re.search(r"[\uac00-\ud7af]", s): return False
    if sum(c.isalpha() for c in s) < 2: return False
    if re.search(r"[.](png|asset|prefab|mat|json|txt|cs|dll|strings|bank)$", s): return False
    if "/" in s or chr(92) in s: return False
    if re.fullmatch(r"[A-Za-z0-9_]+", s) and "_" in s: return False
    if s.startswith("http") or "<" in s: return False
    if re.fullmatch(r"[A-Z]{1,4}", s): return False
    return True

d = json.load(open(os.path.join(BASE, "_zh_work", "ui_components.json"), encoding="utf8"))

# 覆盖检查
missing = set()
# file -> pid -> [(offset, old)]
plan = collections.defaultdict(lambda: collections.defaultdict(list))
n_occ = 0
for fname, e in d.items():
    for o in e["objs"]:
        if o["cls"] not in ("TextMeshProUGUI", "TextMeshPro", "Text"):
            continue
        for off, s in o["strs"]:
            if not meaningful(s): continue
            if s in SKIP: continue
            if s not in TRANS:
                missing.add(s); continue
            if TRANS[s] == s: continue
            plan[fname][o["pid"]].append((int(off, 16), s))
            n_occ += 1

print(f"occurrences to patch: {n_occ}, files: {len(plan)}")
if missing:
    print("MISSING translations:")
    for s in sorted(missing): print("   ", repr(s))
    sys.exit(1)
if DRY:
    for f in plan: print("  dry:", f, sum(len(v) for v in plan[f].values()))
    sys.exit(0)

total_ok = total_fail = 0
for fname, pids in plan.items():
    rel = fname.replace(chr(92), "/")
    path = os.path.join(BASE, rel)
    bk = os.path.join(BK, os.path.basename(rel) + ".pre_ui")
    if not os.path.exists(bk):
        shutil.copy2(path, bk)
        print(f"backup -> {bk}")
    env = UnityPy.load(path)
    bypid = {o.path_id: o for o in env.objects}
    for pid, occs in pids.items():
        o = bypid[pid]
        raw = o.get_raw_data()
        # 高偏移先改, 低偏移不受影响; JSON 偏移 = 长度字段位置, 数据在 off+4
        for off, old in sorted(occs, key=lambda x: -x[0]):
            ob = old.encode("utf8")
            L = len(ob)
            if i32(raw, off) != L or raw[off + 4:off + 4 + L] != ob:
                print(f"  !! MISMATCH {os.path.basename(rel)}#{pid} @0x{off:x}: {old[:30]!r}")
                total_fail += 1
                continue
            nb = TRANS[old].encode("utf8")
            end_old = off + 4 + L
            pad_old = (-L) % 4
            pad_new = (-len(nb)) % 4
            raw = (raw[:off] + struct.pack("<i", len(nb)) + nb + b"\x00" * pad_new
                   + raw[end_old + pad_old:])
            total_ok += 1
        o.set_raw_data(raw)
    out = env.file.save()
    with open(path, "wb") as f:
        f.write(out)
    print(f"{os.path.basename(rel)}: saved ({sum(len(v) for v in pids.values())} objs)")

print(f"patched ok={total_ok} fail={total_fail}")

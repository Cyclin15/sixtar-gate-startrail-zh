# -*- coding: utf-8 -*-
"""字体补丁 v2:
1. Font 1327 (Exo2-Regular, 无组件引用) m_FontData -> simhei.ttf
2. NotoSansSC-Bold SDF (30780): Dynamic + source(0,1327) + multiAtlas + 图集1024
3. 各在用 TMP 字体追加 fallback -> (fid, 30780)
关键修复:
- fallback 定位: 降序尝试 N,要求 count 之前 16 字节全零(TMP 布局: [anchor][16B零][count][entries][0][32][GUID])
- 保存: 先写临时文件再原子替换,避免 UnityPy 惰性读取被截断的源文件
"""
import UnityPy, os, struct, tempfile

BASE = "Sixtar Gate STARTRAIL_Data"
SC_PID = 30780
CARRIER_PID = 1327
SIMHEI = r"C:\Windows\Fonts\simhei.ttf"

def i32(d, o): return struct.unpack_from("<i", d, o)[0]
def pk(*a): return struct.pack(*a)

def rstr(d, o):
    l = i32(d, o); o += 4
    return d[o:o+l], o + l + (-l % 4)

def locate_fallback(d, guid):
    """返回 (count_pos, N, entries_end)。尾部锚: [0][32][GUID](GUID 最后一次出现)"""
    g2 = d.rfind(guid)
    assert i32(d, g2-8) == 0 and i32(d, g2-4) == 32, "tail anchor mismatch"
    end = g2 - 8
    for n in range(24, -1, -1):          # 降序,避免最后一条 PPtr 高位零的假 N=0
        pos = end - 4 - 12*n
        if pos < 0: continue
        if i32(d, pos) != n: continue
        if n > 0:
            ok = all(0 <= i32(d, pos+4+12*i) <= 8 and 0 < struct.unpack_from("<q", d, pos+4+12*i+4)[0] < 2**33
                     for i in range(n))
            if not ok: continue
        if d[pos-16:pos] != b"\x00"*16:  # count 前固定 16 字节零
            continue
        return pos, n, end
    raise RuntimeError("fallback table not located")

def walk_font(d):
    o = 28
    name, o = rstr(d, o)
    o += 4 + 12 + 4
    ver, o = rstr(d, o)
    guid, o = rstr(d, o)
    src = o; o += 12
    pop = o; o += 4
    _fn, o = rstr(d, o)
    _fam, o = rstr(d, o); _sty, o = rstr(d, o)
    o += 8 + 64
    gc = i32(d, o); o += 4 + 52*gc
    cc = i32(d, o); o += 4 + 16*cc
    ac = i32(d, o); o += 4 + 12*ac
    flags = o
    fb_cpos, fb_N, fb_end = locate_fallback(d, guid)
    return dict(name=name.decode('utf8','replace'), guid=guid, src=src, pop=pop,
                flags=flags, fb_cpos=fb_cpos, fb_N=fb_N, fb_end=fb_end)

def add_fallback(d, fid, pid, label=""):
    w = walk_font(d)
    entries = d[w['fb_cpos']+4 : w['fb_end']]
    for i in range(w['fb_N']):
        if struct.unpack_from("<iq", entries, 12*i) == (fid, pid):
            print(f"    {label} already has ({fid},{pid}), skip")
            return d
    return (d[:w['fb_cpos']] + pk("<i", w['fb_N']+1) + entries
            + pk("<iq", fid, pid) + d[w['fb_end']:])

def save_replace(env, path):
    out = env.file.save()          # 先在内存中完整生成,避免截断源文件
    with open(path, "wb") as f:    # 此时 save 已完成,直接覆盖安全
        f.write(out)

def get(env, pid):
    for o in env.objects:
        if o.path_id == pid:
            return o
    raise KeyError(pid)

def main():
    # ---------- sharedassets0 ----------
    p0 = os.path.join(BASE, "sharedassets0.assets")
    env0 = UnityPy.load(p0)
    # 1) Font 载体 -> simhei (遍历魔数出现位置,取长度字段合理者)
    o = get(env0, CARRIER_PID)
    raw = o.get_raw_data()
    m = -1
    for magic in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
        pos = 4
        while True:
            m = raw.find(magic, pos)
            if m < 0: break
            L = i32(raw, m-4)
            if 1000 < L <= len(raw) - m:
                break
            pos = m + 1
        if m > 0:
            break
    else:
        raise RuntimeError("TTF magic not found")
    old_len = i32(raw, m-4)
    data = open(SIMHEI, "rb").read()
    o.set_raw_data(raw[:m-4] + pk("<i", len(data)) + data + raw[m+old_len:])
    print(f"Font {CARRIER_PID}: TTF {old_len}B -> simhei {len(data)}B")
    # 2) NotoSansSC 动态化
    o = get(env0, SC_PID)
    d = o.get_raw_data()
    w = walk_font(d)
    assert w['fb_N'] == 0
    assert i32(d, w['src']) == 0 and i32(d, w['src']+4) == 0 and i32(d, w['pop']) == 0
    d = d[:w['src']] + pk("<iq", 0, CARRIER_PID) + d[w['src']+12:]
    d = d[:w['pop']] + pk("<i", 1) + d[w['pop']+4:]
    d = d[:w['flags']+4] + pk("<i", 1) + d[w['flags']+8:]
    # 图集宽高锚点: [W,H,4,4169]
    patched_atlas = False
    for a in range(w['flags'], w['fb_cpos'], 4):
        W, H, pad, rm = struct.unpack_from("<iiii", d, a)
        if pad == 4 and rm == 4169 and 0 < W <= 4096 and 0 < H <= 4096:
            d = d[:a] + pk("<ii", 1024, 1024) + d[a+8:]
            patched_atlas = (W, H)
            break
    print(f"NotoSansSC: pop->Dynamic, source->(0,{CARRIER_PID}), multiAtlas->1, atlas {patched_atlas}->1024x1024")
    o.set_raw_data(d)
    # 3) fallback 追加
    for pid in (30763, 30765, 30766, 30767, 30768, 30769, 30770,
                30777, 30778, 30779, 30781, 30782, 30783, 30784):
        o = get(env0, pid)
        d = o.get_raw_data()
        w = walk_font(d)
        nd = add_fallback(d, 0, SC_PID, f"#{pid}")
        o.set_raw_data(nd)
        print(f"  #{pid} {w['name']}: N={w['fb_N']} -> {w['fb_N']+1}")
    save_replace(env0, p0)
    print("sharedassets0.assets OK")

    # ---------- resources (fid=2) ----------
    pr = os.path.join(BASE, "resources.assets")
    envr = UnityPy.load(pr)
    af = next(iter(envr.objects)).assets_file
    ext_map = {i+1: getattr(e, 'path', '') or '' for i, e in enumerate(af.externals)}
    assert [k for k, v in ext_map.items() if 'sharedassets0' in v] == [2], ext_map
    for pid in (30866, 30867, 30868, 30869):
        o = get(envr, pid)
        d = o.get_raw_data()
        w = walk_font(d)
        o.set_raw_data(add_fallback(d, 2, SC_PID, f"#{pid}"))
        print(f"  #{pid} {w['name']}: N={w['fb_N']} -> {w['fb_N']+1}")
    save_replace(envr, pr)
    print("resources.assets OK")

    # ---------- sharedassets12 (fid=5) ----------
    p12 = os.path.join(BASE, "sharedassets12.assets")
    env12 = UnityPy.load(p12)
    af = next(iter(env12.objects)).assets_file
    ext_map = {i+1: getattr(e, 'path', '') or '' for i, e in enumerate(af.externals)}
    assert [k for k, v in ext_map.items() if 'sharedassets0' in v] == [5], ext_map
    for pid in (11, 12, 13):
        o = get(env12, pid)
        d = o.get_raw_data()
        w = walk_font(d)
        o.set_raw_data(add_fallback(d, 5, SC_PID, f"#{pid}"))
        print(f"  #{pid} {w['name']}: N={w['fb_N']} -> {w['fb_N']+1}")
    save_replace(env12, p12)
    print("sharedassets12.assets OK")

if __name__ == "__main__":
    main()

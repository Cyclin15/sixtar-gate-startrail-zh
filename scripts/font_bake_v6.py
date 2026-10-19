# -*- coding: utf-8 -*-
"""字体补丁 v6: 离线烘焙静态中文 SDF 字体到 LiberationSans SDF (30867)

原理: 游戏内 TMP 动态加字路径会崩溃(v5)或导致面板异常(v2-v4), 因此完全放弃动态方案,
改为离线用 freetype(simhei) 渲染 SDF 图集, 直接写入:
  - resources.assets.resS 末尾追加 16MB Alpha8 图集 (4096x4096)
  - 纹理 1693: 尺寸 1024->4096, 流数据指向新区域
  - 30867: 重建 glyph/char 表(静态, pop=0), pointSize 86->40, 图集宽高 4096
  - 材质 37/38/45: _TextureWidth/_TextureHeight -> 4096 (_GradientScale=10 不变)
  - sa0: 追加 external resources.assets(fid4) + 21字体 fallback(4,30867), 不碰 30780/1327
  - res: 30866/30868/30869 fallback(0,30867)
  - sa12: 11/12/13 fallback(4,30867)

SDF 编码(从原版图集实测): 值 = 127.5 + 距离px * 12.75, spread=10 (=padding+1, 材质 _GradientScale=10)
表布局(实测): glyph 52B = <I 5f 4i 3f>; char 16B = <I I I f> = (1, unicode, gid, 1.0)
"""
import UnityPy, os, sys, struct, shutil, math
import numpy as np
from scipy.ndimage import distance_transform_edt
import freetype

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from font_patch import walk_font, i32, rstr, save_replace, get

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 游戏根目录
DATA = os.path.join(BASE, "Sixtar Gate STARTRAIL_Data")
BK = os.path.join(BASE, "_zh_work", "backup")
SIMHEI = r"C:\Windows\Fonts\simhei.ttf"

S = 40          # pointSize (与游戏全部字体一致)
SS = 4          # 超采样倍数
PAD = 9         # padding (原版, 材质 _GradientScale=10 对应)
SPREAD = 10.0   # SDF 半宽 px
AW = AH = 4096  # 图集尺寸
FONT_PID = 30867
TEX_PID = 1693
MAT_PIDS = (37, 38, 45)

# ---------------- Phase A: 烘焙 ----------------

def build_charset():
    cs = set(open(os.path.join(BASE, "_zh_work", "charset_v6.txt"), encoding="utf8").read())
    cs |= set(chr(c) for c in range(0x20, 0x7f))                      # ASCII
    cs |= set(chr(c) for c in range(0x3041, 0x3100))                  # 假名
    cs |= set(chr(c) for c in range(0xc0, 0x180))                     # Latin-1/扩展
    cs |= set("·—–…“”‘’〔〕【】《》〈〉「」『』％￥°±×÷≠≥≤≈∞→←↑↓™©®☆★♪►◄●○◆□■△▲▽▼✦✧♩♪♫♬")
    cs = {c for c in cs if ord(c) >= 0x20 and not (0xAC00 <= ord(c) <= 0xD7AF)}  # 去控制符/谚文
    return sorted(cs)

def bake():
    face = freetype.Face(SIMHEI)
    face.set_char_size(S * SS * 64)
    M = int(SPREAD * SS)  # 4x 分辨率下的边缘留白 = 40
    glyphs = []
    skipped = []
    for ch in build_charset():
        try:
            face.load_char(ch, freetype.FT_LOAD_RENDER)
        except Exception:
            skipped.append(ch); continue
        g = face.glyph
        bm = g.bitmap
        adv = g.metrics.horiAdvance / 64 / SS
        cols, rows = bm.width, bm.rows
        if cols == 0 or rows == 0:
            if adv <= 0:
                skipped.append(ch); continue
            glyphs.append(dict(ch=ch, adv=adv, bx=0, by=0, w=0, h=0,
                               rw=0, rh=0, cell=None))
            continue
        arr = np.frombuffer(bytes(bm.buffer), dtype=np.uint8).reshape(rows, cols)
        mask = arr > 127
        if not mask.any():
            glyphs.append(dict(ch=ch, adv=adv, bx=0, by=0, w=0, h=0,
                               rw=0, rh=0, cell=None)); continue
        padded = np.zeros((rows + 2 * M, cols + 2 * M), dtype=bool)
        padded[M:M + rows, M:M + cols] = mask
        signed = np.where(padded, distance_transform_edt(padded),
                          -distance_transform_edt(~padded))
        cw = math.ceil(cols / SS) + 2 * PAD
        chh = math.ceil(rows / SS) + 2 * PAD
        # 采样从 (M - PAD*SS) 开始: cell 内布局 = [PAD留白][墨迹][PAD留白], 与 rect(x+PAD,y+PAD) 对齐
        g0 = M - PAD * SS
        ys = g0 + np.arange(chh) * SS + SS // 2
        xs = g0 + np.arange(cw) * SS + SS // 2
        d = signed[np.ix_(np.minimum(ys, padded.shape[0] - 1),
                          np.minimum(xs, padded.shape[1] - 1))] / SS
        cell = np.clip(np.rint(127.5 + d * (255.0 / (2 * SPREAD))), 0, 255).astype(np.uint8)
        glyphs.append(dict(ch=ch, adv=adv,
                           bx=round(g.bitmap_left / SS), by=round(g.bitmap_top / SS),
                           w=round(cols / SS), h=round(rows / SS),
                           rw=round(cols / SS), rh=round(rows / SS), cell=cell))
    print(f"烘焙: {len(glyphs)} 字形, 跳过 {len(skipped)}: {''.join(skipped[:20])}")

    # 货架装箱
    glyphs.sort(key=lambda g: -(g['cell'].shape[0] if g['cell'] is not None else 0))
    atlas = np.zeros((AH, AW), dtype=np.uint8)
    x = y = row_h = 0
    for i, gl in enumerate(glyphs):
        gl['gid'] = i + 1
        if gl['cell'] is None:
            gl['rx'] = gl['ry'] = 0
            continue
        chh, cw = gl['cell'].shape
        if x + cw > AW:
            x = 0; y += row_h; row_h = 0
        if y + chh > AH:
            raise RuntimeError("图集溢出")
        # Unity 纹理首字节=最底行: 逐 cell 垂直翻转, 否则游戏内字形上下颠倒
        atlas[y:y + chh, x:x + cw] = np.flipud(gl['cell'])
        gl['rx'] = x + PAD; gl['ry'] = y + PAD
        x += cw; row_h = max(row_h, chh)
    used = int((atlas > 0).sum())
    print(f"图集 4096x4096, 墨水像素 {used} ({used/(AW*AH):.1%}), 装箱至 y={y+row_h}")
    return atlas, glyphs

# ---------------- Phase B: 重建 30867 原始数据 ----------------

def rebuild_font(d_orig, glyphs):
    # 与分析一致的 walk, 记录各段偏移
    o = 28
    name, o = rstr(d_orig, o); name_end = o
    mat_end = name_end + 20                 # m_Material 块, 原样保留
    ver, o = rstr(d_orig, mat_end); ver_end = o
    guid, o = rstr(d_orig, ver_end); guid_end = o
    o = guid_end + 12 + 4                   # src(0,0) + pop(0) 原样
    s1, o = rstr(d_orig, o); s2, o = rstr(d_orig, o); s3, o = rstr(d_orig, o)
    face_start = o                          # [int pointSize][float scale][16 float]
    o = face_start + 4 + 4 + 64
    gc = i32(d_orig, o); glyph_tab = o      # count 位置
    o = glyph_tab + 4 + 52 * gc
    cc = i32(d_orig, o); char_tab = o
    o = char_tab + 4 + 16 * cc
    ac = i32(d_orig, o); atlas_tex = o      # count + PPtr(0,1693)
    o = atlas_tex + 4 + 12 * ac
    after_atlas = o
    # 找 [W,H,pad,rm] 锚
    w = walk_font(d_orig)
    anchor = None
    for a in range(after_atlas, w['fb_cpos'], 4):
        W, H, pad, rm = struct.unpack_from("<iiii", d_orig, a)
        if 0 < W <= 8192 and 0 < H <= 8192 and 0 < pad < 64 and rm == 4169:
            anchor = a; break
    assert anchor, "atlas anchor not found"

    # faceInfo: pointSize->S, 16 float 中非 0/0.5 的按比例缩放
    f = S / i32(d_orig, face_start)
    floats = struct.unpack_from("<16f", d_orig, face_start + 8)
    new_floats = [v * f if abs(v) > 1.0 else v for v in floats]

    # 新表
    gtab = b"".join(struct.pack("<I5f4i3f", g['gid'], float(g['w']), float(g['h']),
                                float(g['bx']), float(g['by']), float(g['adv']),
                                g['rx'], g['ry'], g['rw'], g['rh'], 1.0, 0.0, 0.0)
                    for g in glyphs)
    ctab = b"".join(struct.pack("<IIIf", 1, ord(g['ch']), g['gid'], 1.0) for g in glyphs)

    nd = (d_orig[:face_start]
          + struct.pack("<i f 16f".replace(" ", ""), S, 1.0, *new_floats)
          + struct.pack("<i", len(glyphs)) + gtab
          + struct.pack("<i", len(glyphs)) + ctab
          + d_orig[atlas_tex:anchor]
          + struct.pack("<iiii", AW, AH, PAD, 4169)
          + d_orig[anchor + 16:])
    return nd

# ---------------- Phase C: 应用 ----------------

def _sum(fl):
    return sum(1 for p in fl if p[0] in ('_TextureWidth', '_TextureHeight') and p[1] == 4096.0)

def main():
    atlas, glyphs = bake()
    # 预览图
    from PIL import Image
    Image.fromarray(atlas).save(os.path.join(BASE, "_zh_work", "shots", "baked_atlas_v6.png"))

    # 1) 还原 3 个文件到原始状态
    for fn in ("resources.assets", "sharedassets0.assets", "sharedassets12.assets"):
        shutil.copy2(os.path.join(BK, fn), os.path.join(DATA, fn))
        print(f"还原 {fn}")

    # 2) resS 追加图集
    ress = os.path.join(DATA, "resources.assets.resS")
    off = os.path.getsize(ress)
    with open(ress, "ab") as fobj:
        fobj.write(atlas.tobytes())
    print(f"resS: 追加 {atlas.nbytes}B @ {off}")

    # 3) resources.assets
    pr = os.path.join(DATA, "resources.assets")
    env = UnityPy.load(pr)
    # 纹理 1693
    t = get(env, TEX_PID)
    tree = t.read_typetree()
    tree['m_Width'] = AW; tree['m_Height'] = AH
    if 'm_CompleteImageSize' in tree: tree['m_CompleteImageSize'] = AW * AH
    tree['m_StreamData']['offset'] = off
    tree['m_StreamData']['size'] = AW * AH
    tree['m_StreamData']['path'] = 'resources.assets.resS'
    t.save_typetree(tree)
    print("纹理 1693 -> 4096x4096 流式")
    # 材质
    for pid in MAT_PIDS:
        m = get(env, pid)
        mt = m.read_typetree()
        fl = mt['m_SavedProperties']['m_Floats']
        fl = [(p[0], 4096.0) if p[0] in ('_TextureWidth', '_TextureHeight') else p for p in fl]
        mt['m_SavedProperties']['m_Floats'] = fl
        m.save_typetree(mt)
        print(f"材质 {pid} ({mt['m_Name']}): 更新 {_sum(fl)}")
    # 30867 重建
    o = get(env, FONT_PID)
    o.set_raw_data(rebuild_font(o.get_raw_data(), glyphs))
    print("30867 重建完成")
    # fallback
    from font_patch import add_fallback
    for pid in (30866, 30868, 30869):
        fo = get(env, pid)
        fo.set_raw_data(add_fallback(fo.get_raw_data(), 0, FONT_PID, f"#{pid}"))
    save_replace(env, pr)
    print("resources.assets OK")

    # 4) sharedassets0: external + fallback (不碰 Font1327!)
    p0 = os.path.join(DATA, "sharedassets0.assets")
    env0 = UnityPy.load(p0)
    sf0 = next(iter(env0.objects)).assets_file
    paths = [getattr(e, 'path', '') for e in sf0.externals]
    if "resources.assets" not in paths:
        import copy
        ne = copy.copy(sf0.externals[-1])
        ne.path = "resources.assets"; ne.guid = b"\x00" * 16; ne.type = 0
        sf0.externals.append(ne)
    fid = [getattr(e, 'path', '') for e in sf0.externals].index("resources.assets") + 1
    for pid in range(30763, 30785):
        if pid == 30780: continue
        fo = get(env0, pid)
        fo.set_raw_data(add_fallback(fo.get_raw_data(), fid, FONT_PID, f"#{pid}"))
    save_replace(env0, p0)
    print(f"sharedassets0 OK (external fid={fid}, 21 fallback)")

    # 5) sharedassets12
    p12 = os.path.join(DATA, "sharedassets12.assets")
    env12 = UnityPy.load(p12)
    sf12 = next(iter(env12.objects)).assets_file
    ext12 = [getattr(e, 'path', '') for e in sf12.externals]
    fid12 = ext12.index("resources.assets") + 1
    assert fid12 == 4, ext12
    for pid in (11, 12, 13):
        fo = get(env12, pid)
        fo.set_raw_data(add_fallback(fo.get_raw_data(), fid12, FONT_PID, f"#{pid}"))
    save_replace(env12, p12)
    print("sharedassets12 OK")

if __name__ == "__main__":
    main()

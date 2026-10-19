import UnityPy, struct, json, os, glob, sys
from collections import Counter, defaultdict

scripts = {int(k): v for k, v in json.load(open("_zh_work/scripts_map.json")).items()}

def find_str_fields(d):
    """Extract all serialized strings (len-prefixed, padded) with offsets."""
    out = []
    pos = 0; n = len(d)
    while pos + 4 <= n:
        ln = struct.unpack_from("<i", d, pos)[0]
        if 1 <= ln <= 8192 and pos + 4 + ln <= n:
            b = d[pos+4:pos+4+ln]
            try:
                s = b.decode("utf-8")
                ok = all(c in "\n\t\r" or 32 <= ord(c) < 0xFFFE for c in s)
                if ok:
                    end = pos + 4 + ln; pad = (-end) & 3
                    if d[end:end+pad] == b"\x00" * pad:
                        out.append((pos, s, end + pad)); pos = end + pad; continue
            except UnicodeDecodeError: pass
        pos += 4
    return out

def scan(path):
    env = UnityPy.load(path)
    exts = [e.path for e in getattr(env.file, "externals", [])]
    def cls_of(raw):
        if len(raw) < 24: return None
        fid, pid = struct.unpack_from("<iq", raw, 16)
        if fid == 0: return None  # same-file script
        idx = fid - 1
        if 0 <= idx < len(exts) and "globalgamemanagers" in exts[idx] and pid in scripts:
            return scripts[pid][0]
        return None
    fonts = {}
    for o in env.objects:
        if o.type.name == "Font":
            try: fonts[o.path_id] = o.read().m_Name
            except Exception: pass
    out = []
    for o in env.objects:
        if o.type.name != "MonoBehaviour": continue
        try: raw = o.get_raw_data()
        except Exception: continue
        cls = cls_of(raw)
        if cls is None: continue
        strs = find_str_fields(raw)
        out.append({"pid": o.path_id, "cls": cls, "strs": [(hex(p), s) for p, s, _ in strs]})
    return out, fonts

if __name__ == "__main__":
    data = r"Sixtar Gate STARTRAIL_Data"
    files = [os.path.join(data, f) for f in sorted(os.listdir(data))
             if f.endswith(".assets") or (f.startswith("level") and "." not in f)]
    bdir = os.path.join(data, "StreamingAssets", "aa", "StandaloneWindows64")
    files += sorted(glob.glob(os.path.join(bdir, "*.bundle")))
    res = {}
    for f in files:
        try:
            out, fonts = scan(f)
        except Exception as e:
            print("ERR", f, e, file=sys.stderr); continue
        if out:
            res[os.path.relpath(f, ".")] = {"fonts": fonts, "objs": out}
    json.dump(res, open("_zh_work/ui_components.json", "w", encoding="utf-8"), ensure_ascii=False)
    # summary
    cc = Counter()
    for f, r in res.items():
        for o in r["objs"]: cc[o["cls"]] += 1
    print("component classes:", dict(cc))

"""Bisect which table's Chinese content breaks the song list.
Usage: python test_bisect.py System            # only System table -> Chinese, rest English
       python test_bisect.py System,Adventure  # comma list; 'ALL' = every table"""
import json, base64, struct, os, sys, zlib
import UnityPy
from UnityPy.helpers import CompressionHelper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_zh_work"))
from localtbl import parse_table, build_table

BUNDLE = os.path.join(ROOT, r"Sixtar Gate STARTRAIL_Data/StreamingAssets/aa/StandaloneWindows64"
                  r"/localization-string-tables-english(unitedstates)(en-us)_assets_all.bundle")
CATALOG = os.path.join(ROOT, r"Sixtar Gate STARTRAIL_Data/StreamingAssets/aa/catalog.json")
BACKUP = os.path.join(ROOT, "_zh_work", "backup",
                      "localization-string-tables-english_assets_all.bundle")

sel = sys.argv[1] if len(sys.argv) > 1 else "ALL"
zh_tables = set()          # fully-Chinese tables
zh_keys = {}               # table -> set(keys) partially Chinese ("Table:key1,key2")
if sel == "ALL":
    zh_tables = {"System", "UnlockPopup", "Adventure_Dialogue", "InputGuide", "Adventure"}
else:
    for part in sel.split(","):
        if ":" in part:
            t, ks = part.split(":", 1)
            zh_keys.setdefault(t, set()).update(ks.split("+"))
        else:
            zh_tables.add(part)
print("tables -> Chinese:", sorted(zh_tables), " keys:", {k: len(v) for k, v in zh_keys.items()})


def unity_bundle_crc(data: bytes) -> int:
    p = 12
    p = data.index(b"\x00", p) + 1
    p = data.index(b"\x00", p) + 1
    compBI, uncompBI = struct.unpack_from(">II", data, p + 8)
    p += 16
    flags = struct.unpack_from(">I", data, p)[0]
    p += 4
    if p % 16:
        p += 16 - (p % 16)
    comp = flags & 0x3F
    bi = data[p:p + compBI] if flags & 0x40 else data[len(data) - compBI:]
    bi_dec = CompressionHelper.decompress_lz4(bi, uncompBI) if comp in (2, 3) else bi
    q = 16
    n = struct.unpack_from(">i", bi_dec, q)[0]; q += 4
    blocks = []
    for _ in range(n):
        u, c = struct.unpack_from(">II", bi_dec, q); q += 8
        bf = struct.unpack_from(">H", bi_dec, q)[0]; q += 2
        blocks.append((u, c, bf))
    off = p + compBI
    if flags & 0x200 and off % 16:
        off += 16 - (off % 16)
    dec = b""
    for (u, c, bf) in blocks:
        blk = data[off:off + c]; off += c
        dec += CompressionHelper.decompress_lz4(blk, u) if (bf & 0x3F) in (2, 3) else blk
    return zlib.crc32(dec)


zh = json.load(open(os.path.join(ROOT, "_zh_work", "zh_strings.json"), encoding="utf8"))
en = json.load(open(os.path.join(ROOT, "_zh_work", "en_strings.json"), encoding="utf8"))
zmap = {}
keymap = {}
for t, entries in en.items():
    for e in entries:
        zmap[(t, e["id"])] = zh[t][e["key"]]
        keymap[(t, e["id"])] = e["key"]

env = UnityPy.load(BACKUP)
done = []
for obj in env.objects:
    if obj.type.name != "MonoBehaviour":
        continue
    t = parse_table(obj.get_raw_data())
    name = t["name"]
    assert name.endswith("_en-US"), name
    table = name[:-len("_en-US")]
    ksel = zh_keys.get(table, set())
    entries = []
    for eid, val in t["entries"]:
        use_zh = table in zh_tables or keymap[(table, eid)] in ksel
        entries.append((eid, zmap[(table, eid)] if use_zh else val))
    obj.set_raw_data(build_table(t, entries))
    done.append(table)
assert sorted(done) == sorted(en.keys()), done

out = env.file.save()
with open(BUNDLE, "wb") as f:
    f.write(out)
crc = unity_bundle_crc(out)
print("bundle:", len(out), "bytes  crc:", crc)

cat = json.load(open(CATALOG, encoding="utf8"))
extras = base64.b64decode(cat["m_ExtraDataString"])
TM = b"JUnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions"
blobs = []
i = 0
while True:
    j = extras.find(TM, i)
    if j < 0:
        break
    ln = struct.unpack_from("<i", extras, j + len(TM))[0]
    blobs.append((j, j + len(TM) + 4 + ln))
    i = j + len(TM) + 4 + ln
bundles = [s for s in cat["m_InternalIds"] if s.endswith(".bundle")]
p = [k for k, s in enumerate(bundles) if "english(unitedstates)" in s][0]
s0, s1 = blobs[p]
opts = json.loads(extras[s0 + len(TM) + 4:s1].decode("utf-16-le"))
opts["m_Crc"] = crc
opts["m_BundleSize"] = len(out)
new_js = json.dumps(opts, separators=(",", ":"))
new_blob = TM + struct.pack("<i", len(new_js) * 2) + new_js.encode("utf-16-le")
extras = extras[:s0] + new_blob + extras[s1:]
cat["m_ExtraDataString"] = base64.b64encode(extras).decode("ascii")
with open(CATALOG, "w", encoding="utf8") as f:
    json.dump(cat, f, separators=(",", ":"))
print("catalog patched: m_Crc=%d m_BundleSize=%d" % (crc, len(out)))

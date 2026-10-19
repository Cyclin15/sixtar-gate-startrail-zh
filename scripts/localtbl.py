"""Parser/serializer for Unity Localization StringTable & SharedTableData MonoBehaviours (raw bytes)."""
import struct


def rd_str(d, off):
    n = struct.unpack_from("<i", d, off)[0]
    off += 4
    s = d[off:off + n].decode("utf-8")
    off += n
    off = (off + 3) & ~3
    return s, off


def wr_str(s):
    b = s.encode("utf-8")
    pad = (-(4 + len(b))) & 3
    return struct.pack("<i", len(b)) + b + b"\x00" * pad


def parse_shared(d):
    off = 12 + 4 + 12
    name, off = rd_str(d, off)
    coll, off = rd_str(d, off)
    guid, off = rd_str(d, off)
    cnt = struct.unpack_from("<i", d, off)[0]
    off += 4
    entries = []
    for i in range(cnt):
        eid = struct.unpack_from("<q", d, off)[0]
        off += 8
        key, off = rd_str(d, off)
        mc = struct.unpack_from("<i", d, off)[0]
        off += 4
        assert mc == 0, f"shared entry {i} meta={mc}"
        entries.append((eid, key))
    return {"name": name, "collection": coll, "entries": entries, "tail": d[off:], "end": off}


def parse_table(d):
    off = 12 + 4 + 12
    name, off = rd_str(d, off)
    locale, off = rd_str(d, off)
    meta_cnt = struct.unpack_from("<i", d, off)[0]
    off += 4
    off += 12 * meta_cnt
    cnt = struct.unpack_from("<i", d, off)[0]
    off += 4
    head = d[:off]
    entries = []
    for i in range(cnt):
        eid = struct.unpack_from("<q", d, off)[0]
        off += 8
        val, off = rd_str(d, off)
        mc = struct.unpack_from("<i", d, off)[0]
        off += 4
        assert mc == 0, f"table {name} entry {i} meta={mc}"
        entries.append((eid, val))
    return {"name": name, "locale": locale, "head": head, "entries": entries,
            "tail": d[off:], "end": off}


def build_table(t, new_entries):
    """new_entries: list of (eid, value); head (through entry count) and tail are reused verbatim."""
    out = bytearray(t["head"])
    assert struct.unpack_from("<i", out, len(out) - 4)[0] == len(new_entries), "entry count mismatch in head"
    for eid, val in new_entries:
        out += struct.pack("<q", eid)
        out += wr_str(val)
        out += struct.pack("<i", 0)
    out += t["tail"]
    return bytes(out)

"""Gunpoint.wad unpack/pack.

Format: u32 data_start, u32 count, then count x [u32 name_len][name][u32 size][u32 offset];
offsets are relative to data_start, files stored back to back without padding.

  python wadtool.py unpack Gunpoint.wad out_dir
  python wadtool.py pack   out_dir Gunpoint.wad [overlay_dir ...]
Pack keeps the original entry order (from _order.txt written by unpack);
a file present in an overlay dir (same relative path) replaces the original.
repack() does the same straight from the original archive, without unpacking it.
"""
import os, re, struct, sys


def winpath(p):
    """Accept Git Bash style /g/dir as well as G:/dir."""
    m = re.match(r'^/([a-zA-Z])(/.*)?$', p)
    return f'{m.group(1).upper()}:{m.group(2) or "/"}' if m else p


def read_table(f):
    data_start, count = struct.unpack('<II', f.read(8))
    ents = []
    for _ in range(count):
        n, = struct.unpack('<I', f.read(4))
        name = f.read(n).decode('ascii')
        size, off = struct.unpack('<II', f.read(8))
        ents.append((name, size, off))
    assert f.tell() == data_start, (f.tell(), data_start)
    return data_start, ents


def entries(wad):
    """-> [(name, size, offset)] with offsets relative to the data start."""
    with open(wad, 'rb') as f:
        return read_table(f)[1]


def read(wad, name):
    with open(wad, 'rb') as f:
        base, ents = read_table(f)
        for n, size, off in ents:
            if n == name:
                f.seek(base + off)
                return f.read(size)
    raise KeyError(f'{name} not in {wad}')


def repack(src_wad, wad, replace):
    """Copy src_wad to wad, replacing entries: replace = {name: bytes}."""
    with open(src_wad, 'rb') as f:
        src_base, ents = read_table(f)
        unknown = set(replace) - {e[0] for e in ents}
        if unknown:
            raise KeyError(f'not in {src_wad}: {", ".join(sorted(unknown))}')
        sizes = [len(replace[n]) if n in replace else s for n, s, _ in ents]
        table = b''
        off = 0
        for (n, _, _), s in zip(ents, sizes):
            b = n.encode('ascii')
            table += struct.pack('<I', len(b)) + b + struct.pack('<II', s, off)
            off += s
        base = 8 + len(table)
        tmp = wad + '.tmp'
        with open(tmp, 'wb') as o:
            o.write(struct.pack('<II', base, len(ents)) + table)
            for n, size, src_off in ents:
                if n in replace:
                    o.write(replace[n])
                    continue
                f.seek(src_base + src_off)
                left = size
                while left:
                    chunk = f.read(min(left, 1 << 22))
                    o.write(chunk)
                    left -= len(chunk)
    os.replace(tmp, wad)
    print(f'wad: {len(replace)} of {len(ents)} files replaced -> {wad}')


def unpack(wad, out):
    with open(wad, 'rb') as f:
        base, ents = read_table(f)
        for name, size, off in ents:
            p = os.path.join(out, *name.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            f.seek(base + off)
            with open(p, 'wb') as o:
                o.write(f.read(size))
    with open(os.path.join(out, '_order.txt'), 'w', encoding='ascii') as o:
        o.write('\n'.join(e[0] for e in ents) + '\n')
    print(f'{len(ents)} files -> {out}')


def pack(src, wad, *overlays):
    names = [l.strip() for l in open(os.path.join(src, '_order.txt'), encoding='ascii') if l.strip()]

    def path(n):
        for d in reversed(overlays):
            p = os.path.join(d, *n.split('/'))
            if os.path.isfile(p):
                return p
        return os.path.join(src, *n.split('/'))

    paths = [path(n) for n in names]
    for n, p in zip(names, paths):
        if not p.startswith(src):
            print('  replaced', n)
    sizes = [os.path.getsize(p) for p in paths]
    table = b''
    off = 0
    for n, s in zip(names, sizes):
        b = n.encode('ascii')
        table += struct.pack('<I', len(b)) + b + struct.pack('<II', s, off)
        off += s
    base = 8 + len(table)
    tmp = wad + '.tmp'
    with open(tmp, 'wb') as o:
        o.write(struct.pack('<II', base, len(names)) + table)
        for p in paths:
            with open(p, 'rb') as i:
                while chunk := i.read(1 << 22):
                    o.write(chunk)
    os.replace(tmp, wad)
    print(f'{len(names)} files -> {wad} ({base + off} bytes)')


if __name__ == '__main__':
    cmd, *args = sys.argv[1:]
    {'unpack': unpack, 'pack': pack}[cmd](*map(winpath, args))

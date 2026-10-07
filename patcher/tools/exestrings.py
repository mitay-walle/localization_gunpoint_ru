"""Gunpoint.exe: find the UTF-16 string literals and patch translations in.

Used by tools/table.py (scan) and build.py (patch).

scan:  every reference (code operand or .data pointer) to a UTF-16 literal in .rdata,
       confirmed against a disassembly of the containing function (PDB symbols).
patch: appends a `.rutext` section with the translated strings (UTF-16, NUL-terminated)
       and repoints the references. The exe has no ASLR and no relocations, so the
       absolute addresses in code are final; length is computed at runtime
       (PGMLVar(const wchar_t*)), so translations may be longer than the original.
       References from engine code (font parser, Lua, Phyre) are never touched.
       Optionally makes file_text_read_string decode files as UTF-8 (see UTF8_STUB).
"""
import bisect, mmap, os, re, struct

import pefile

BASE = 0x400000


def pdb_publics(pdb, pe):
    """S_PUB32 records: name -> VA."""
    secs = pe.sections
    out = {}
    with open(pdb, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for m in re.finditer(rb'\x0e\x11(.{4})(.{4})(.{2})([\x21-\x7e]{3,}?)\x00', mm, re.S):
            off, = struct.unpack('<I', m.group(2))
            seg, = struct.unpack('<H', m.group(3))
            if 1 <= seg <= len(secs):
                out[m.group(4).decode()] = BASE + secs[seg - 1].VirtualAddress + off
    return out


OPS = {'0': 'ctor', '1': 'dtor', '4': 'operator=', '8': 'operator==', '9': 'operator!=', 'A': 'operator[]',
       'B': 'cast', 'H': 'operator+', 'M': 'operator<', 'Y': 'operator+='}


def demangle_short(name):
    """?SetCaseNotes@gml@@YAX... -> gml::SetCaseNotes, ??8PGMLVar@gml@@... -> gml::PGMLVar::operator=="""
    m = re.match(r'\?\?(\w)([^@?$]+)@([^@]*)@', name)
    if m and m.group(1) in OPS:
        ns = m.group(3) + '::' if m.group(3) else ''
        return f'{ns}{m.group(2)}::{OPS[m.group(1)]}'
    m = re.match(r'\?([^@?$]+)@([^@]*)@', name)
    if not m:
        return name.lstrip('_')
    return f'{m.group(2)}::{m.group(1)}' if m.group(2) else m.group(1)


def read_wstr(img, rva):
    """Return the NUL-terminated UTF-16 string at rva if it looks like text, else None."""
    if img[rva - 2:rva] != b'\0\0':
        return None  # literals start after a terminator/padding; otherwise it points mid-string
    out = []
    p = rva
    while p + 1 < len(img):
        c = img[p] | img[p + 1] << 8
        if c == 0:
            break
        if not (0x20 <= c < 0x7F or c in (9, 10, 13) or 0xA0 <= c <= 0x17F or 0x2010 <= c <= 0x2122):
            return None  # game text is Latin; anything else is a narrow string or a pointer table
        out.append(chr(c))
        p += 2
        if len(out) > 20000:
            return None
    if not out or not any(ch.isalpha() for ch in out):
        return None
    return ''.join(out)


TECH_RE = re.compile(r'''(
    \.(gun|guns|gpc|lvl|txt|wav|ogg|png|fnt|bin|ini|ags|phyre|cgfx|dll|exe)$ |
    [\\/] |
    ^[a-z]+[A-Z]\w*$ |            # camelCase identifiers (oPlayer, sBlackBig, mTheme)
    ^[A-Za-z]+_[A-Za-z0-9_]*$ |   # snake_case keys
    ^[A-Z][a-z]+([A-Z0-9][a-z0-9]*)+$ |  # PascalCase ids (ActCorp2Tom, GesslerDryFire)
    ^[^ ]*[&=][^ ]*$ |            # url parameters (&C3=)
    ^%|%[sdif]                    # printf formats
)''', re.X)
# the string goes to something outside the game text: files, Steam, FMOD dll, shell
TECH_CALLS = re.compile(r'ini_|file_|steam|Achieve|execute|asset_get|object_get|sprite_get|Workshop|registry|'
                        r'environment|FMOD|show_debug|SaveLevel|LoadLevel', re.I)
TECH_FUNCS = re.compile(r'^gml::(LoadFMOD|ReadLog|WriteLog|ListCustomMissions|StartEnabledLoops|SaveLevel|'
                        r'LoadLevel|show_debug)')
# the string is compared or used as a map key: fine to translate if it never comes from files/saves
CHECK_CALLS = re.compile(r'operator==|operator!=|GMLMap|ds_map|string_pos|string_count|string_replace')
# GML code: gml:: helpers, data tables, GameMaker event functions (ActOne1_Create, People_oPlayer_Step_0)
GML_CTX = re.compile(r'^(gml::|<\.data|<\.rdata|[A-Z][A-Za-z0-9]*_[^:]*$)')


def classify(text, calls, ctxs):
    funcs = [c.split(' -> ')[0] for c in ctxs]
    if not any(GML_CTX.match(f) for f in funcs):
        return 'tech'  # engine strings (Phyre, Lua, CRT); never patched anyway
    funcs = [f for f in funcs if GML_CTX.match(f)]
    if TECH_RE.search(text) or any(TECH_CALLS.search(c) for c in calls) or any(TECH_FUNCS.match(f) for f in funcs):
        return 'tech'
    if any(CHECK_CALLS.search(c) for c in calls):
        return 'check'
    if ' ' not in text.strip() and '#' not in text:
        return 'word'
    return 'text'


def scan(exe, pdb):
    """Returns (rows, refs). rows: one per unique text {id, kind, refs, context, original}."""
    pe = pefile.PE(exe)
    img = pe.get_memory_mapped_image()
    text_s = next(s for s in pe.sections if s.Name.startswith(b'.text'))
    rdata = next(s for s in pe.sections if s.Name.startswith(b'.rdata'))
    data = next(s for s in pe.sections if s.Name.startswith(b'.data'))
    r_lo, r_hi = rdata.VirtualAddress, rdata.VirtualAddress + rdata.Misc_VirtualSize

    syms = pdb_publics(pdb, pe)
    t_lo, t_hi = text_s.VirtualAddress, text_s.VirtualAddress + text_s.Misc_VirtualSize
    funcs = sorted({v for v in syms.values() if BASE + t_lo <= v < BASE + t_hi})
    fname = {}
    for k, v in syms.items():
        if v in fname and not fname[v].startswith('?'):
            continue
        fname[v] = k

    cache = {}

    def wstr(va):
        if va not in cache:
            rva = va - BASE
            cache[va] = read_wstr(img, rva) if r_lo <= rva < r_hi and rva % 2 == 0 else None
        return cache[va]

    # 1) raw scan of .text for dwords that point at a UTF-16 literal
    code = img[t_lo:t_hi]
    cand = {}
    for off in range(len(code) - 3):
        v = struct.unpack_from('<I', code, off)[0]
        if BASE + r_lo <= v < BASE + r_hi and wstr(v):
            cand[BASE + t_lo + off] = v

    # 2) confirm with a disassembly of the containing function (operand must sit exactly there)
    import capstone  # only for scanning; the patcher does not need it
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.skipdata = True
    refs, unconfirmed = [], []
    by_func = {}
    for site, v in cand.items():
        i = bisect.bisect_right(funcs, site) - 1
        by_func.setdefault(funcs[i] if i >= 0 else None, []).append(site)
    for fstart, sites in by_func.items():
        if fstart is None:
            unconfirmed += sites
            continue
        j = funcs.index(fstart)
        fend = funcs[j + 1] if j + 1 < len(funcs) else BASE + t_hi
        insns = list(md.disasm(img[fstart - BASE:fend - BASE], fstart))
        starts = {ins.address: k for k, ins in enumerate(insns)}
        for site in sites:
            hit = None
            for back in range(1, 8):  # operand is within the last bytes of an instruction
                k = starts.get(site - back)
                if k is not None and insns[k].address + insns[k].size >= site + 4:
                    hit = k
                    break
            if hit is None:
                unconfirmed.append(site)
                continue
            calls = []
            for ins in insns[hit:hit + 25]:
                if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
                    c = demangle_short(fname.get(int(ins.op_str, 16), ins.op_str))
                    if c not in ('gml::PGMLVar::ctor', 'gml::PGMLVar::dtor'):
                        calls.append(c)
                    if len(calls) == 2:
                        break
            refs.append({'site': site, 'str': cand[site], 'func': demangle_short(fname[fstart]),
                         'calls': calls})

    # 3) pointers stored in .data tables (4-byte aligned): key names for the controls menu.
    #    (.rdata only gives coincidental matches)
    lo = data.VirtualAddress
    blob = img[lo:lo + data.Misc_VirtualSize]
    for off in range(0, len(blob) - 3, 4):
        v = struct.unpack_from('<I', blob, off)[0]
        if BASE + r_lo <= v < BASE + r_hi and wstr(v):
            refs.append({'site': BASE + lo + off, 'str': v, 'func': '<.data table>', 'calls': []})

    print(f'exe: {len(cand)} raw hits in .text, {len(cand) - len(unconfirmed)} confirmed as operands; '
          f'{len(refs)} references total')

    groups = {}
    for r in sorted(refs, key=lambda r: r['str']):
        r['text'] = cache[r['str']]
        g = groups.setdefault(r['text'], {'id': f'exe:{r["str"]:06x}', 'refs': 0, 'ctx': [], 'calls': []})
        g['refs'] += 1
        ctx = r['func'] + (' -> ' + ', '.join(r['calls']) if r['calls'] else '')
        if ctx not in g['ctx']:
            g['ctx'].append(ctx)
        if GML_CTX.match(r['func']):
            g['calls'] += r['calls']
    rows = [{'id': g['id'], 'kind': classify(t, g['calls'], g['ctx']), 'refs': g['refs'],
             'context': ' | '.join(g['ctx'][:3]), 'original': t} for t, g in groups.items()]
    refs = [{'site': r['site'], 'str': r['str'], 'func': r['func'], 'text': r['text']} for r in refs]
    return rows, refs


def align(x, a):
    return (x + a - 1) // a * a


# file_text_read_string widens each byte with movsx (0xC0 -> U+FFC0). The stub replaces the
# widening call with UTF-8 decoding via MultiByteToWideChar, resolved at runtime (the exe
# imports LoadLibraryExA/GetProcAddress but not MultiByteToWideChar). If decoding fails it
# falls back to the original widening. Readers: .gpc scripts, levels, settings (ASCII).
UTF8_CALL_SITE = 0x583612       # call _Construct<string::iterator> (wstring from a char range)
WIDEN_FN = 0x41e600
IMP_LOADLIBRARYEXA = 0x719074
IMP_GETPROCADDRESS = 0x7190a0
OP_NEW, OP_DELETE = 0x670bac, 0x670a6a
WSTR_ASSIGN = 0x427630          # wstring::assign(const wchar_t *, size_t)
UTF8_STUB = """
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    mov esi, ecx
    mov ebx, dword ptr [ebp+8]
    mov edi, dword ptr [ebp+0xc]
    sub edi, ebx
    jle done
    mov eax, dword ptr [{cache}]
    test eax, eax
    jnz have
    push 0
    push 0
    push {kernel32}
    call dword ptr [{loadlib}]
    push {fname}
    push eax
    call dword ptr [{getproc}]
    mov dword ptr [{cache}], eax
    test eax, eax
    jz legacy
have:
    lea eax, [edi+edi+2]
    push eax
    call {new}
    add esp, 4
    push eax
    push edi
    push eax
    push edi
    push ebx
    push 0
    push 65001
    call dword ptr [{cache}]
    test eax, eax
    jz fail
    mov edx, dword ptr [esp]
    push eax
    push edx
    mov ecx, esi
    call {assign}
    call {delete}
    add esp, 4
    jmp done
fail:
    call {delete}
    add esp, 4
legacy:
    push dword ptr [ebp+0x10]
    push dword ptr [ebp+0xc]
    push dword ptr [ebp+8]
    mov ecx, esi
    call {widen}
done:
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret 0xc
"""


def patch(exe, translations, refs, out, utf8_files=True):
    """translations: {original text: translated text}; refs: from scan()."""
    import keystone

    pe = pefile.PE(exe)
    oh = pe.OPTIONAL_HEADER
    last = pe.sections[-1]
    new_rva = align(last.VirtualAddress + last.Misc_VirtualSize, oh.SectionAlignment)
    new_raw = align(last.PointerToRawData + last.SizeOfRawData, oh.FileAlignment)
    sec_va = BASE + new_rva
    data = bytearray(open(exe, 'rb').read())
    assert len(data) == new_raw, 'unexpected overlay after the last section'

    blob = bytearray()
    if utf8_files:
        # section start: [cache dword][b"kernel32.dll"][b"MultiByteToWideChar"][stub]
        blob += bytes(4) + b'kernel32.dll\0'.ljust(16, b'\0') + b'MultiByteToWideChar\0'.ljust(24, b'\0')
        stub_va = sec_va + len(blob)
        asm = UTF8_STUB.format(cache=hex(sec_va), kernel32=hex(sec_va + 4), fname=hex(sec_va + 20),
                               loadlib=hex(IMP_LOADLIBRARYEXA), getproc=hex(IMP_GETPROCADDRESS),
                               new=hex(OP_NEW), delete=hex(OP_DELETE), assign=hex(WSTR_ASSIGN),
                               widen=hex(WIDEN_FN))
        code, _ = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32).asm(asm, stub_va)
        blob += bytes(code)
        blob += b'\0' * (align(len(blob), 16) - len(blob))
        site = pe.get_offset_from_rva(UTF8_CALL_SITE - BASE)
        assert data[site] == 0xE8 and struct.unpack_from('<i', data, site + 1)[0] == WIDEN_FN - UTF8_CALL_SITE - 5, \
            'unexpected code at the UTF-8 call site (different exe version?)'
        struct.pack_into('<i', data, site + 1, stub_va - UTF8_CALL_SITE - 5)

    where = {}
    for orig, t in translations.items():
        where[orig] = sec_va + len(blob)
        blob += t.encode('utf-16le') + b'\0\0'
        blob += b'\0' * (align(len(blob), 4) - len(blob))
    if not blob:
        blob = bytearray(4)
    vsize = len(blob)
    rawsize = align(vsize, oh.FileAlignment)

    # section header: code + initialized data, read/write/execute (the stub caches a pointer)
    hdr_off = last.get_file_offset() + 40
    assert hdr_off + 40 <= oh.SizeOfHeaders, 'no room for another section header'
    assert not any(data[hdr_off:hdr_off + 40]), 'section header slot is not empty'
    data[hdr_off:hdr_off + 40] = struct.pack('<8sIIIIIIHHI', b'.rutext', vsize, new_rva, rawsize, new_raw,
                                             0, 0, 0, 0, 0xE0000060)
    struct.pack_into('<H', data, pe.FILE_HEADER.get_file_offset() + 2, pe.FILE_HEADER.NumberOfSections + 1)
    struct.pack_into('<I', data, oh.get_file_offset() + 56, align(new_rva + vsize, oh.SectionAlignment))  # SizeOfImage

    n = skipped = 0
    for r in refs:
        if r['text'] not in where:
            continue
        if not GML_CTX.match(r['func']):
            skipped += 1  # engine code (font parser, Lua, Phyre) uses the same literal: keep English
            continue
        off = pe.get_offset_from_rva(r['site'] - BASE)
        cur, = struct.unpack_from('<I', data, off)
        assert cur == r['str'], f'reference at {r["site"]:#x} does not match (exe already patched?)'
        struct.pack_into('<I', data, off, where[r['text']])
        n += 1

    data += blob + b'\0' * (rawsize - vsize)
    tmp = out + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, out)
    print(f'exe: {len(translations)} strings translated, {n} references repointed, '
          f'{skipped} engine references kept, UTF-8 file reading {"on" if utf8_files else "off"} -> {out}')

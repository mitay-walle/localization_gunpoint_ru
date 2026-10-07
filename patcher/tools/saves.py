"""Translate strings stored inside existing save games.

Saves (Savegames/*.gun) are a snapshot of the GML state: objects created before the
translation keep the English text they were created with (mission descriptions, names...).
The file is a sequential tagged stream without sizes or checksums:
  [u32 var id][u32 type] value;  type 1 = int32, 2 = double, 3 = string, 4 = array
  string: [u32 length in chars][UTF-16 chars][u16 0]
so a string can be replaced by one of a different length.

Strings equal to an exe original (or to a previously applied translation) are replaced
with the current translation. The last applied mapping is kept next to the game
(Gunpoint.saves.json), so editing a translation updates already translated saves, and an
empty mapping (patcher --restore) turns them back into English.
A backup of the folder is made before the first change: Savegames_backup_<date>.
"""
import datetime, json, os, re, shutil, struct, subprocess

STR = re.compile(rb'\x03\x00\x00\x00(.{4})', re.S)


def game_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Gunpoint.exe', '/NH'],
                             capture_output=True, text=True).stdout
        return 'Gunpoint.exe' in out
    except OSError:
        return False


def replace_strings(data, mapping):
    out, pos, n = bytearray(), 0, 0
    for m in STR.finditer(data):
        if m.start() < pos:
            continue
        length, = struct.unpack('<I', m.group(1))
        start = m.end()
        end = start + length * 2
        if length == 0 or length > 100000 or data[end:end + 2] != b'\0\0':
            continue
        try:
            text = data[start:end].decode('utf-16le')
        except UnicodeDecodeError:
            continue
        new = mapping.get(text)
        if new is None or new == text:
            continue
        out += data[pos:m.start()] + b'\x03\x00\x00\x00' + struct.pack('<I', len(new)) + new.encode('utf-16le')
        pos = end
        n += 1
    out += data[pos:]
    return bytes(out), n


def apply(exe_tr, save_dir, state_path):
    """exe_tr: {original text: translation}."""
    if game_running():
        print('saves: the game is running, skipped (close it and run again)')
        return
    applied = json.load(open(state_path, encoding='utf-8')) if os.path.exists(state_path) else {}
    mapping = dict(exe_tr)
    for orig, old in applied.items():  # previously applied translation -> current (or back to original)
        mapping.setdefault(old, exe_tr.get(orig, orig))
    files, total, backup = 0, 0, None
    for fn in sorted(os.listdir(save_dir)):
        if not fn.endswith('.gun'):
            continue
        p = os.path.join(save_dir, fn)
        data = open(p, 'rb').read()
        if not data.startswith(b'__GUNPOINT__'):
            continue
        new, n = replace_strings(data, mapping)
        if not n:
            continue
        if backup is None:
            backup = save_dir.rstrip('\\/') + '_backup_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copytree(save_dir, backup)
        with open(p + '.tmp', 'wb') as f:
            f.write(new)
        os.replace(p + '.tmp', p)
        files += 1
        total += n
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(exe_tr, f, ensure_ascii=False, indent=0)
    print(f'saves: {total} strings in {files} files translated' + (f' (backup: {backup})' if backup else ''))

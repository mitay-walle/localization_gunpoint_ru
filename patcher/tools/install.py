"""Install a translation into the game folder (shared by build.py and the standalone patcher).

Translations: CSV files with the table columns (id, ..., original, translation). The text of a
row is `translation`, or `original` when `translation` is empty; rows whose text equals the
English original are skipped. So both translation/<lang>.csv (English in `original`) and a file
exported by LocalizationForum (the translation written over `original`) work. Rows are matched
by id against the reference table (en.csv + exe_refs.json); later files override earlier ones.

Every run starts from the originals kept next to the game files (Gunpoint.exe.orig,
Gunpoint.wad.orig, Scripts.orig/, made by the first run), so installing again or installing
another language never stacks patches. restore() puts the originals back.
"""
import csv, json, os, shutil

import config, exestrings, fontpack, gpcstrings, saves, wadtool

STEPS = ['gpc', 'exe', 'wad', 'saves']


def reference():
    """-> ({id: row of en.csv}, exe refs)"""
    with open(os.path.join(config.DATA, 'en.csv'), encoding='utf-8-sig', newline='') as f:
        rows = {r['id']: r for r in csv.DictReader(f)}
    with open(os.path.join(config.DATA, 'exe_refs.json'), encoding='utf-8') as f:
        refs = json.load(f)
    return rows, refs


def load(files, ref):
    """-> ({gpc id: text}, {exe original: text})"""
    gpc, exe = {}, {}
    for path in files:
        n = 0
        with open(path, encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if not {'id', 'original'} <= set(reader.fieldnames or ()):
                print(f'{path}: no id/original columns, skipped')
                continue
            for r in reader:
                base = ref.get(r['id'])
                if not base or base['kind'] == 'tech':
                    continue
                t = r.get('translation') or ''
                if not t.strip():
                    t = r['original'] or ''
                if not t.strip() or t == base['original']:
                    continue
                if base['id'].startswith('gpc:'):
                    gpc[base['id']] = t
                else:
                    exe[base['original']] = t
                n += 1
        print(f'{path}: {n} translated strings')
    return gpc, exe


def count(path, ref):
    """Number of translated rows in a CSV (0 for an English or foreign table)."""
    try:
        with open(path, encoding='utf-8-sig', newline='') as f:
            n = 0
            for r in csv.DictReader(f):
                base = ref.get(r.get('id') or '')
                t = (r.get('translation') or '').strip() and r['translation'] or r.get('original') or ''
                n += bool(base and base['kind'] != 'tech' and t.strip() and t != base['original'])
            return n
    except (OSError, UnicodeDecodeError, csv.Error):
        return 0


SKIP_DIRS = {'fonts', 'ttf', '_internal', 'build', 'dist', 'Scripts', 'Scripts.orig', 'Savegames'}


def find_tables(base, ref):
    found = []
    for root, dirs, files in os.walk(base):
        depth = os.path.relpath(root, base).count(os.sep) + (root != base)
        dirs[:] = [] if depth >= 2 else [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        found += [os.path.join(root, f) for f in files if f.lower().endswith('.csv')]
    counted = [(p, count(p, ref)) for p in sorted(found)]
    return [(p, n) for p, n in counted if n]


# --- originals -------------------------------------------------------------------------------

def _game(name):
    return os.path.join(config.GAME, name)


def original(name, check=None):
    """Path of the original copy of a game file/folder, made on the first run."""
    src, orig = _game(name), _game(name + '.orig')
    if not os.path.exists(orig):
        if check:
            check(src)
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, orig)
        print(f'backup: {orig}')
    return orig


def _exe_untouched(path):
    with open(path, 'rb') as f:
        if b'.rutext\0' in f.read(4096):
            raise SystemExit(f'{path} is already patched and there is no Gunpoint.exe.orig. '
                             'Restore the original files (Steam: Properties > Installed Files > Verify) and run again.')


def _scripts_untouched(ref):
    def check(path):
        rows = [r for r in ref.values() if r['id'].startswith('gpc:')]
        same = 0
        for r in rows:
            _, fn, n = r['id'].split(':')
            try:
                lines = gpcstrings._lines(os.path.join(path, fn))
            except (OSError, UnicodeDecodeError):
                continue
            same += int(n) <= len(lines) and lines[int(n) - 1] == r['original']
        if same < len(rows) * 0.9:
            raise SystemExit(f'{path}: the scripts are not the English originals ({same} of {len(rows)} lines match) '
                             'and there is no Scripts.orig. Restore the original files (Steam: Properties > '
                             'Installed Files > Verify) and run again.')
    return check


# --- steps -----------------------------------------------------------------------------------

def missing_chars(fonts_dir, wad, texts):
    used = set()
    for t in texts:
        used.update(ord(c) for c in t if ord(c) >= 0x80)
    for name, have in fontpack.chars(fonts_dir, wad).items():
        missing = sorted(used - have)
        if missing:
            print(f'  WARNING {name}: {len(missing)} characters missing from the font '
                  f'({"".join(map(chr, missing[:30]))})')


def install(files, fonts_dir, steps=STEPS):
    ref, refs = reference()
    gpc_tr, exe_tr = load(files, ref)
    print(f'game: {config.GAME}')
    print(f'saves: {config.SAVES or "-"}')
    print(f'{len(gpc_tr)} conversation lines, {len(exe_tr)} exe strings translated')
    if 'gpc' in steps:
        src = original('Scripts', _scripts_untouched(ref))
        gpcstrings.write(src, gpc_tr, _game('Scripts'), 'utf-8')
    if 'exe' in steps:
        src = original('Gunpoint.exe', _exe_untouched)
        exestrings.patch(src, exe_tr, refs, _game('Gunpoint.exe'), utf8_files=True)
    if 'wad' in steps:
        src = original('Gunpoint.wad')
        missing_chars(fonts_dir, src, list(gpc_tr.values()) + list(exe_tr.values()))
        wadtool.repack(src, _game('Gunpoint.wad'), fontpack.build(fonts_dir, src))
    if 'saves' in steps and config.SAVES:
        saves.apply(exe_tr, config.SAVES, _game('Gunpoint.saves.json'))


def restore():
    for name in ('Gunpoint.exe', 'Gunpoint.wad'):
        if os.path.exists(_game(name + '.orig')):
            shutil.copy2(_game(name + '.orig'), _game(name))
            print(f'restored {name}')
    if os.path.isdir(_game('Scripts.orig')):
        shutil.rmtree(_game('Scripts'))
        shutil.copytree(_game('Scripts.orig'), _game('Scripts'))
        print('restored Scripts')
    if config.SAVES and os.path.exists(_game('Gunpoint.saves.json')):
        saves.apply({}, config.SAVES, _game('Gunpoint.saves.json'))

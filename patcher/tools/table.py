"""The translation table: one CSV per language with every translatable string.

  python tools/table.py extract <lang> [--import-gpc DIR]   # create / refresh translation/<lang>.csv
  python tools/table.py stats [<lang>]

Rows come from the conversation scripts (<game>/Scripts.orig, or Scripts before the first
install) and from Gunpoint.exe (.orig).
Refreshing keeps the `translation` column (matched by id, for exe rows also by original text).
--import-gpc fills empty translations from an already translated Scripts folder.

Columns: id, kind, refs, context, original, translation
  gpc rows: kind line (Them) / choice (Me); id gpc:<file>:<line>
  exe rows: kind text / word / check / tech (see README); id exe:<address of the literal>
Empty translation = original text.
"""
import csv, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import exestrings
import gpcstrings

FIELDS = ['id', 'kind', 'refs', 'context', 'original', 'translation']


def path(lang):
    return os.path.join(config.TRANSLATION, f'{lang}.csv')


def load(lang):
    p = path(lang)
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def save(lang, rows):
    os.makedirs(config.TRANSLATION, exist_ok=True)
    tmp = path(lang) + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)  # every field quoted: one regex parses any row (forum format)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in FIELDS})
    os.replace(tmp, path(lang))


def load_refs():
    return json.load(open(os.path.join(config.TRANSLATION, 'exe_refs.json'), encoding='utf-8'))


def translations(lang):
    """-> ({gpc id: text}, {exe original: text}) for non-empty translations."""
    gpc, exe = {}, {}
    for r in load(lang):
        t = r['translation']
        if not t.strip():
            continue
        if r['id'].startswith('gpc:'):
            gpc[r['id']] = t
        else:
            exe[r['original']] = t
    return gpc, exe


def extract(lang, import_gpc=None):
    config.init()  # needs Gunpoint.exe.orig and Gunpoint.exe.pdb from the game folder
    gpc_rows = gpcstrings.scan(config.SOURCE_GPC)
    exe_rows, refs = exestrings.scan(config.EXE_ORIG, config.PDB)
    os.makedirs(config.TRANSLATION, exist_ok=True)
    with open(os.path.join(config.TRANSLATION, 'exe_refs.json'), 'w', encoding='utf-8') as f:
        json.dump(refs, f, ensure_ascii=False, indent=0)

    old = load(lang)
    by_id = {r['id']: r['translation'] for r in old}
    by_text = {r['original']: r['translation'] for r in old if not r['id'].startswith('gpc:')}
    imported = gpcstrings.import_dir(config.SOURCE_GPC, import_gpc) if import_gpc else {}

    rows = gpc_rows + exe_rows
    for r in rows:
        t = by_id.get(r['id']) or (by_text.get(r['original'], '') if r['id'].startswith('exe:') else '')
        r['translation'] = t or imported.get(r['id'], '')
    save(lang, rows)
    stats(lang)


def stats(lang=None):
    langs = [lang] if lang else sorted(f[:-4] for f in os.listdir(config.TRANSLATION) if f.endswith('.csv'))
    for lg in langs:
        by_kind = {}
        for r in load(lg):
            k = by_kind.setdefault(r['kind'], [0, 0])
            k[0] += 1
            k[1] += bool(r['translation'].strip())
        print(f'{path(lg)}: ' + ', '.join(f'{k} {d}/{n}' for k, (n, d) in by_kind.items()))


if __name__ == '__main__':
    args = [config.winpath(a) for a in sys.argv[1:]]
    if args[0] == 'extract':
        imp = args[args.index('--import-gpc') + 1] if '--import-gpc' in args else None
        extract(args[1], imp)
    elif args[0] == 'stats':
        stats(args[1] if len(args) > 1 else None)

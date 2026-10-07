"""The translation table <-> LocalizationForum: one file, en.csv.

  python tools/forum.py files ru         # translation/forum/: en.csv (source) + ru/approve.csv, ru/propose.csv
  python tools/forum.py import ru <file> # file exported by the forum -> translation/ru.csv

On the forum the game has one source file, en.csv, parsed by the custom data format
`gunpoint-csv` (config: translation/forum/format-gunpoint-csv.json): a regex over one CSV row
with all fields quoted; key = id, text = original; the header and `tech` rows are skipped.
The forum copy leaves out `tech` rows and the context column (the format cannot show it).
The forum writes a translation in place of the `original` field, so a translated file is
en.csv with the translation in that column. Quotes inside text stay doubled ("") as in CSV.
approve.csv: conversation lines (already approved earlier); propose.csv: exe strings (AI drafts).
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import table

FORUM = os.path.join(config.TRANSLATION, 'forum')


def _write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=table.FIELDS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in table.FIELDS})
    print(f'forum: {len(rows)} rows -> {path}')


def files(lang):
    src = [r for r in table.load('en') if r['kind'] != 'tech']
    _write(os.path.join(FORUM, 'en.csv'), [{**r, 'context': '', 'translation': ''} for r in src])
    done = [r for r in table.load(lang) if r['kind'] != 'tech' and r['translation'].strip()]
    as_file = lambda rs: [{**r, 'context': '', 'original': r['translation'], 'translation': ''} for r in rs]
    _write(os.path.join(FORUM, lang, 'approve.csv'), as_file(r for r in done if r['id'].startswith('gpc:')))
    _write(os.path.join(FORUM, lang, 'propose.csv'), as_file(r for r in done if not r['id'].startswith('gpc:')))


def import_file(lang, path):
    got = {r['id']: r['original'] for r in csv.DictReader(open(path, encoding='utf-8-sig', newline=''))}
    rows = table.load(lang)
    n = 0
    for r in rows:
        t = got.get(r['id'])
        if t is not None and t != r['original'] and t.strip() and t != r['translation']:
            r['translation'] = t
            n += 1
    table.save(lang, rows)
    print(f'forum: {n} translations updated in {table.path(lang)}')


if __name__ == '__main__':
    args = [config.winpath(a) for a in sys.argv[1:]]
    if args[0] == 'files':
        files(args[1])
    elif args[0] == 'import':
        import_file(args[1], args[2])

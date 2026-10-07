"""Conversation scripts (Scripts/*.gpc): table rows <-> files.

Format (CRLF): blocks separated by empty lines; a block starts with a header
(`Them:`, `Me:`, `After:`), then text lines, each followed by a line with the number
of the line to jump to. The file ends with `END SCENE`. Only text lines are translated;
headers, numbers and empty lines are copied from the original, so line numbers stay valid.

Row ids: gpc:<file>:<line number, 1-based>.
"""
import os
import re

HEADERS = {'Them:', 'Me:', 'After:', 'END SCENE'}
NUM = re.compile(r'^-?\d+$')


def _lines(path):
    return open(path, 'rb').read().decode('utf-8-sig').split('\r\n')


def _is_text(line):
    s = line.strip()
    return bool(s) and s not in HEADERS and not NUM.match(s)


def scan(src_dir):
    rows = []
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith('.gpc'):
            continue
        speaker = ''
        for n, line in enumerate(_lines(os.path.join(src_dir, fn)), 1):
            s = line.strip()
            if s in HEADERS:
                speaker = s[:-1] if s.endswith(':') else s
                continue
            if not _is_text(line):
                continue
            kind = 'choice' if speaker == 'Me' else 'line'
            rows.append({'id': f'gpc:{fn}:{n}', 'kind': kind, 'refs': 1,
                         'context': f'{fn[:-4]} / {speaker}', 'original': line})
    print(f'gpc: {len(rows)} text lines in {src_dir}')
    return rows


def import_dir(src_dir, tr_dir):
    """Read an already translated copy of the scripts (same line layout) -> {id: text}."""
    out = {}
    for fn in sorted(os.listdir(src_dir)):
        p = os.path.join(tr_dir, fn)
        if not fn.endswith('.gpc') or not os.path.exists(p):
            continue
        a, b = _lines(os.path.join(src_dir, fn)), _lines(p)
        if len(a) != len(b):
            print(f'  skip {fn}: {len(a)} vs {len(b)} lines')
            continue
        for n, (x, y) in enumerate(zip(a, b), 1):
            if _is_text(x):
                if x != y:
                    out[f'gpc:{fn}:{n}'] = y
            elif x.strip() != y.strip():
                print(f'  {fn}:{n}: structure differs ({x!r} vs {y!r})')
    return out


def write(src_dir, translations, out_dir, encoding='utf-8'):
    """Copy the original scripts into out_dir with translated text lines."""
    files = 0
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith('.gpc'):
            continue
        lines = _lines(os.path.join(src_dir, fn))
        for n, line in enumerate(lines, 1):
            t = translations.get(f'gpc:{fn}:{n}')
            if t and _is_text(line):
                lines[n - 1] = t.replace('\r', ' ').replace('\n', ' ')
        with open(os.path.join(out_dir, fn), 'wb') as f:
            f.write('\r\n'.join(lines).encode(encoding, errors='replace'))
        files += 1
    print(f'gpc: {files} files ({encoding}) -> {out_dir}')

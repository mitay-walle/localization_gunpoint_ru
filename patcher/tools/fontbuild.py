"""Generate the editable fonts (fonts/<name>.fnt + fonts/<name>_0.png) with the glyphs
the translations need.

  python tools/fontbuild.py [lang ...]          # default: every translation/<lang>.csv

For each of the 12 game fonts: the original glyphs are copied from the original atlas
unchanged; every character used by the translations that the font lacks (plus basic
Cyrillic and typographic punctuation) is rendered from a Windows TTF at a pixel size
calibrated against the original Latin glyphs. Scripts the original face does not cover
(Hangul, CJK, kana) come from a fallback font. The atlas grows (power of two) when the
glyphs do not fit. Previews: fonts/_preview/<name>.png.

The result is plain BMFont (XML .fnt + 8-bit PNG, top-down) — replace any of these files
with your own (e.g. from AngelCode BMFont, single page) and build.py packs it into the game.
"""
import os, sys
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTCollection, TTFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import fontpack
import wadtool
import table

WINFONTS = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')

# (face, bold, italic) -> TTF used for new glyphs
TTF = {
    ('Arial', 0, 0): 'arial.ttf',
    ('Arial', 1, 0): 'arialbd.ttf',
    ('Georgia', 0, 0): 'georgia.ttf',
    ('Georgia', 1, 1): 'georgiaz.ttf',
    # Estrangelo Edessa has no Cyrillic and is not shipped with Windows 10/11;
    # its Latin is a geometric sans, Century Gothic Bold is the closest match.
    ('Estrangelo Edessa', 1, 0): 'GOTHICB.TTF',
}
SAME_FACE = {'GOTHICB.TTF': False}  # substitute faces are calibrated by glyph height only

# script fallbacks: (first, last, regular, bold)
FALLBACK = [
    (0x1100, 0x11FF, 'malgun.ttf', 'malgunbd.ttf'),     # Hangul Jamo
    (0x3130, 0x318F, 'malgun.ttf', 'malgunbd.ttf'),     # Hangul compatibility Jamo
    (0xAC00, 0xD7A3, 'malgun.ttf', 'malgunbd.ttf'),     # Hangul syllables
    (0x3040, 0x30FF, 'YuGothM.ttc', 'YuGothB.ttc'),     # kana
    (0x3000, 0x303F, 'msyh.ttc', 'msyhbd.ttc'),         # CJK punctuation
    (0x4E00, 0x9FFF, 'msyh.ttc', 'msyhbd.ttc'),         # CJK ideographs
    (0xFF00, 0xFFEF, 'msyh.ttc', 'msyhbd.ttc'),         # full-width forms
]

BASE_CHARS = [0x401, 0x451] + list(range(0x410, 0x450)) + \
             [0x2013, 0x2014, 0x2026, 0x2018, 0x2019, 0x201A, 0x201C, 0x201D, 0x201E, 0x2116, 0x2022]
SPACING = 1
MAX_ATLAS = 4096

_cmaps = {}


def has_glyph(ttf, cp):
    if ttf not in _cmaps:
        p = os.path.join(WINFONTS, ttf)
        f = TTCollection(p).fonts[0] if p.lower().endswith('.ttc') else TTFont(p, lazy=True)
        _cmaps[ttf] = set(f.getBestCmap())
    return cp in _cmaps[ttf]


def fallback_ttf(cp, bold):
    for a, b, reg, bd in FALLBACK:
        if a <= cp <= b:
            return bd if bold else reg
    return None


def render(font, ch):
    l, t, r, b = font.getbbox(ch, anchor='ls')
    img = Image.new('L', (max(r - l, 0), max(b - t, 0)))
    if r > l and b > t:
        ImageDraw.Draw(img).text((-l, -t), ch, font=font, fill=255, anchor='ls')
    return img, l, t, round(font.getlength(ch))


def calibrate(ttf, size, chars, base, same_face):
    """Pick the TTF pixel size that best reproduces the original Latin glyphs."""
    ref = [c for c in range(0x21, 0x7f) if chr(c).isalpha() and c in chars]
    best = None
    s = size * 0.5
    while s <= size * 1.2:
        f = ImageFont.truetype(ttf, s)
        err = 0
        for c in ref:
            l, t, r, b = f.getbbox(chr(c), anchor='ls')
            o = chars[c]
            err += abs((b - t) - o['height']) * 2
            if same_face:
                err += abs(round(f.getlength(chr(c))) - o['xadvance']) + abs((r - l) - o['width'])
        if best is None or err < best[0]:
            best = (err, s)
        s += 0.05
    f = ImageFont.truetype(ttf, best[1])
    # align offsets with the original rasteriser (GDI) using median deltas
    dx, dy = [], []
    for c in ref:
        _, l, t, _ = render(f, chr(c))
        dx.append(chars[c]['xoffset'] - l)
        dy.append(chars[c]['yoffset'] - (base + t))
    med = lambda v: sorted(v)[len(v) // 2]
    return best[1], med(dx) if same_face else 0, med(dy)


def pack(glyphs, W, H):
    """Shelf packer. glyphs: {id: Image}. Returns {id: (x, y)} or None."""
    order = sorted(glyphs, key=lambda i: (-glyphs[i].height, -glyphs[i].width, i))
    pos, x, y, shelf = {}, 0, 0, 0
    for i in order:
        w, h = glyphs[i].size
        if x + w > W:
            x, y, shelf = 0, y + shelf + SPACING, 0
        if y + h > H:
            return None
        pos[i] = (x, y)
        x += w + SPACING
        shelf = max(shelf, h)
    return pos


def build(name, wanted):
    fnt = fontpack.read_fnt(os.path.join(config.WAD_ORIG, 'Fonts', name + '.fnt'))
    info, common, chars, kern = fnt['info'], fnt['common'], fnt['chars'], fnt['kernings']
    W, H = int(common['scaleW']), int(common['scaleH'])
    base = int(common['base'])
    atlas = fontpack.read_phyre_texture(os.path.join(config.WAD_ORIG, 'GL', 'Fonts', name + '_0.png.phyre'))

    bold = int(info['bold'])
    ttf = TTF[(info['face'], bold, int(info['italic']))]
    px, dx, dy = calibrate(os.path.join(WINFONTS, ttf), int(info['size']), chars, base, SAME_FACE.get(ttf, True))
    fonts = {}

    def font_for(cp):
        f = ttf if has_glyph(ttf, cp) else fallback_ttf(cp, bold)
        if f is None or not has_glyph(f, cp):
            return None, None
        if f not in fonts:
            fonts[f] = ImageFont.truetype(os.path.join(WINFONTS, f), px)
        return fonts[f], f

    bitmaps, meta = {}, {}
    for cid, c in chars.items():
        bitmaps[cid] = atlas.crop((c['x'], c['y'], c['x'] + c['width'], c['y'] + c['height']))
        meta[cid] = (c['xoffset'], c['yoffset'], c['xadvance'])
    added, missing, used = 0, [], set()
    for cp in sorted(wanted):
        if cp in chars:
            continue
        f, fname = font_for(cp)
        if f is None:
            missing.append(cp)
            continue
        used.add(fname)
        img, l, t, adv = render(f, chr(cp))
        same = fname == ttf
        bitmaps[cp] = img
        meta[cp] = (l + (dx if same else 0), base + t + dy, adv)
        added += 1

    pos = pack(bitmaps, W, H)
    while pos is None:
        if W == H:
            W *= 2
        else:
            H *= 2
        if max(W, H) > MAX_ATLAS:
            raise SystemExit(f'{name}: glyphs do not fit into {MAX_ATLAS}x{MAX_ATLAS}')
        pos = pack(bitmaps, W, H)
    new_atlas = Image.new('L', (W, H))
    for cid, img in bitmaps.items():
        new_atlas.paste(img, pos[cid])

    common['scaleW'], common['scaleH'] = str(W), str(H)
    out_chars = {cid: {'id': cid, 'x': pos[cid][0], 'y': pos[cid][1], 'width': bitmaps[cid].width,
                       'height': bitmaps[cid].height, 'xoffset': meta[cid][0], 'yoffset': meta[cid][1],
                       'xadvance': meta[cid][2], 'page': 0, 'chnl': 15} for cid in bitmaps}
    os.makedirs(config.FONTS, exist_ok=True)
    fontpack.write_fnt(os.path.join(config.FONTS, name + '.fnt'),
                       {'info': info, 'common': common, 'pages': {0: name + '_0.png'},
                        'chars': out_chars, 'kernings': kern})
    new_atlas.save(os.path.join(config.FONTS, name + '_0.png'))
    fontpack.preview(name, out_chars, new_atlas, int(common['lineHeight']), kern,
                     os.path.join(config.FONTS, '_preview', name + '.png'), SAMPLES)
    print(f'{name:14} {ttf:12} px={px:5.2f} +{added:4} glyphs {W}x{H}'
          + (f' fallback: {", ".join(sorted(used - {ttf}))}' if used - {ttf} else '')
          + (f' MISSING {len(missing)}: {"".join(map(chr, missing[:20]))}' if missing else ''))


SAMPLES = ['Съешь же ещё этих мягких французских булок, да выпей чаю.',
           'ЭХ, ЧУЖАК! ОБЩИЙ СЪЁМ ЦЕН ШЛЯП (ЮФТЬ) — ВДРЫЗГ! №5 «ок»',
           'The quick brown fox jumps over the lazy dog. 0123456789']


def main(langs):
    if not os.path.isdir(os.path.join(config.WAD_ORIG, 'Fonts')):  # original glyphs come from the unpacked wad
        config.init()
        wad = config.WAD_ORIG_FILE if os.path.exists(config.WAD_ORIG_FILE) else os.path.join(config.GAME, 'Gunpoint.wad')
        wadtool.unpack(wad, config.WAD_ORIG)
    wanted = set(BASE_CHARS)
    for lang in langs:
        rows = table.load(lang)
        sample = [r['translation'] for r in rows if r['translation'].strip()][:2]
        SAMPLES.extend(s for s in sample if s not in SAMPLES)
        for r in rows:
            wanted.update(ord(c) for c in r['translation'] if ord(c) >= 0x80)
    print(f'{len(wanted)} non-ASCII characters wanted (languages: {", ".join(langs)})')
    for fn in sorted(os.listdir(os.path.join(config.WAD_ORIG, 'Fonts'))):
        if fn.endswith('.fnt'):
            build(fn[:-4], wanted)


if __name__ == '__main__':
    langs = sys.argv[1:] or sorted(f[:-4] for f in os.listdir(config.TRANSLATION) if f.endswith('.csv'))
    main(langs)

"""BMFont <-> game format.

  python tools/fontpack.py export [out_dir]   # original game fonts -> BMFont .fnt + .png (reference)
build() turns fonts/*.fnt + *_0.png into wad entries (used by tools/install.py).

Game format: Fonts/<name>.fnt — BMFont XML (parsed with TinyXML), a single page;
GL/Fonts/<name>_0.png.phyre — PhyreEngine PTexture2D, format L8, no mipmaps, rows bottom-up.
The texture header is taken from the original file of the same font; width, height,
max mip level and data size are rewritten, so any atlas size works.
Accepted input: .fnt in XML or text format; PNG 8-bit, gray+alpha or RGBA (glyphs in
alpha, or white-on-black). The atlas is packed back into the wad: the game loads textures
only from the archive, never from loose files.
"""
import os, re, struct, sys
import xml.etree.ElementTree as ET
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import wadtool

CHAR_KEYS = ['id', 'x', 'y', 'width', 'height', 'xoffset', 'yoffset', 'xadvance', 'page', 'chnl']


# --- .fnt -------------------------------------------------------------------------------

def read_fnt(src):
    """src: path or file bytes."""
    raw = (src if isinstance(src, bytes) else open(src, 'rb').read()).decode('utf-8-sig')
    out = {'info': {}, 'common': {}, 'pages': {}, 'chars': {}, 'kernings': []}
    if raw.lstrip().startswith('<'):
        root = ET.fromstring(raw)
        out['info'] = dict(root.find('info').attrib)
        out['common'] = dict(root.find('common').attrib)
        for p in root.iter('page'):
            out['pages'][int(p.get('id'))] = p.get('file')
        for c in root.iter('char'):
            d = {k: int(v) for k, v in c.attrib.items() if k in CHAR_KEYS}
            out['chars'][d['id']] = d
        for k in root.iter('kerning'):
            out['kernings'].append((int(k.get('first')), int(k.get('second')), int(k.get('amount'))))
        return out
    for line in raw.splitlines():  # BMFont text format
        parts = line.split(None, 1)
        if not parts:
            continue
        tag = parts[0]
        attrs = {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|\S+)', parts[1] if len(parts) > 1 else '')}
        if tag in ('info', 'common'):
            out[tag] = attrs
        elif tag == 'page':
            out['pages'][int(attrs['id'])] = attrs['file']
        elif tag == 'char':
            d = {k: int(v) for k, v in attrs.items() if k in CHAR_KEYS}
            out['chars'][d['id']] = d
        elif tag == 'kerning':
            out['kernings'].append((int(attrs['first']), int(attrs['second']), int(attrs['amount'])))
    return out


def fnt_bytes(fnt):
    def attrs(d):
        return ' '.join(f'{k}="{v}"' for k, v in d.items())
    lines = ['<?xml version="1.0"?>', '<font>',
             f'  <info {attrs(fnt["info"])}/>',
             f'  <common {attrs(fnt["common"])}/>',
             '  <pages>'] + [f'    <page id="{i}" file="{f}" />' for i, f in sorted(fnt['pages'].items())] + \
            ['  </pages>', f'  <chars count="{len(fnt["chars"])}">']
    for cid in sorted(fnt['chars']):
        c = fnt['chars'][cid]
        lines.append('    <char ' + ' '.join(f'{k}="{c.get(k, 0 if k != "chnl" else 15)}"' for k in CHAR_KEYS) + ' />')
    lines.append('  </chars>')
    if fnt['kernings']:
        lines.append(f'  <kernings count="{len(fnt["kernings"])}">')
        lines += [f'    <kerning first="{a}" second="{b}" amount="{n}" />' for a, b, n in fnt['kernings']]
        lines.append('  </kernings>')
    lines.append('</font>')
    return ('\r\n'.join(lines) + '\r\n').encode('utf-8')


def write_fnt(path, fnt):
    with open(path, 'wb') as f:
        f.write(fnt_bytes(fnt))


# --- .phyre texture -----------------------------------------------------------------------

def _texture_fields(data):
    """-> (header length, offset of the width/height pair, width, height)."""
    w, h = None, None
    size, = struct.unpack_from('<I', data, 0x50)
    hdr = len(data) - size
    name_end = data.index(b'\0', data.index(b'Fonts/'))
    for k in range(name_end, hdr - 8):
        w, h = struct.unpack_from('<II', data, k)
        if w * h == size and w and h and struct.unpack_from('<I', data, k - 12)[0] == max(w, h).bit_length() - 1:
            return hdr, k, w, h
    raise ValueError('texture header not recognised')


def read_phyre_texture(src):
    """src: path or file bytes."""
    data = src if isinstance(src, bytes) else open(src, 'rb').read()
    hdr, _, w, h = _texture_fields(data)
    return Image.frombytes('L', (w, h), data[hdr:]).transpose(Image.FLIP_TOP_BOTTOM)


def texture_bytes(template, img):
    """template: bytes of the original texture of the font (its header is reused)."""
    hdr, k, _, _ = _texture_fields(template)
    head = bytearray(template[:hdr])
    W, H = img.size
    struct.pack_into('<II', head, k, W, H)
    struct.pack_into('<I', head, k - 12, max(W, H).bit_length() - 1)
    struct.pack_into('<I', head, 0x50, W * H)
    return bytes(head) + img.transpose(Image.FLIP_TOP_BOTTOM).tobytes()


def to_l8(img):
    """BMFont page -> 8-bit coverage."""
    if img.mode == 'P':
        img = img.convert('RGBA')
    if img.mode in ('RGBA', 'LA'):
        a = img.getchannel('A')
        if a.getextrema() != (255, 255):
            return a  # glyphs in the alpha channel
        img = img.convert('RGB')
    return img.convert('L')


# --- preview --------------------------------------------------------------------------------

def preview(name, chars, atlas, line_h, kern, out, samples):
    kmap = {(a, b): n for a, b, n in kern}
    img = Image.new('L', (1400, line_h * len(samples) + 8), 24)
    for row, text in enumerate(samples):
        x, y, prev = 4, 4 + row * line_h, None
        for ch in text:
            cid = ord(ch) if ord(ch) in chars else ord('?')
            c = chars[cid]
            if prev is not None:
                x += kmap.get((prev, cid), 0)
            if c['width'] and c['height']:
                g = atlas.crop((c['x'], c['y'], c['x'] + c['width'], c['y'] + c['height']))
                img.paste(255, (x + c['xoffset'], y + c['yoffset']), g)
            x += c['xadvance']
            prev = cid
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)


# --- commands -------------------------------------------------------------------------------

def names():
    return sorted(f[:-4] for f in os.listdir(os.path.join(config.WAD_ORIG, 'Fonts')) if f.endswith('.fnt'))


def export(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name in names():
        fnt = read_fnt(os.path.join(config.WAD_ORIG, 'Fonts', name + '.fnt'))
        write_fnt(os.path.join(out_dir, name + '.fnt'), fnt)
        read_phyre_texture(os.path.join(config.WAD_ORIG, 'GL', 'Fonts', name + '_0.png.phyre')).save(
            os.path.join(out_dir, name + '_0.png'))
    print(f'{len(names())} original fonts -> {out_dir}')


def wad_names(wad):
    return sorted(n[6:-4] for n, _, _ in wadtool.entries(wad) if n.startswith('Fonts/') and n.endswith('.fnt'))


def build(fonts_dir, wad):
    """fonts_dir/<name>.fnt + page -> {wad entry: bytes}; fonts missing from fonts_dir stay original."""
    out, done = {}, []
    for name in wad_names(wad):
        src = os.path.join(fonts_dir, name + '.fnt')
        if not os.path.exists(src):
            continue
        fnt = read_fnt(src)
        if len(fnt['pages']) != 1:
            raise SystemExit(f'{src}: {len(fnt["pages"])} pages, the game reads only one (make the texture bigger)')
        page = os.path.join(fonts_dir, fnt['pages'].get(0) or name + '_0.png')
        if not os.path.exists(page):
            page = os.path.join(fonts_dir, name + '_0.png')
        img = to_l8(Image.open(page))
        W, H = img.size
        bad = [c['id'] for c in fnt['chars'].values() if c['x'] + c['width'] > W or c['y'] + c['height'] > H]
        if bad:
            raise SystemExit(f'{src}: {len(bad)} glyphs outside the {W}x{H} texture')
        fnt['common'].update(scaleW=str(W), scaleH=str(H), pages='1')
        fnt['pages'] = {0: name + '_0.png'}
        for c in fnt['chars'].values():
            c['page'] = 0
        tex = f'GL/Fonts/{name}_0.png.phyre'
        out[f'Fonts/{name}.fnt'] = fnt_bytes(fnt)
        out[tex] = texture_bytes(wadtool.read(wad, tex), img)
        done.append(f'{name} {W}x{H}')
    print(f'fonts: {len(done)} from {fonts_dir}' + (f' ({", ".join(done)})' if done else ''))
    return out


def chars(fonts_dir, wad):
    """{font name: set of character codes} for the fonts the game will use."""
    out = {}
    for name in wad_names(wad):
        p = os.path.join(fonts_dir, name + '.fnt')
        out[name] = set(read_fnt(p if os.path.exists(p) else wadtool.read(wad, f'Fonts/{name}.fnt'))['chars'])
    return out


if __name__ == '__main__':
    args = [config.winpath(a) for a in sys.argv[1:]]
    if args[0] == 'export':
        export(args[1] if len(args) > 1 else os.path.join(config.PROJECT, 'fonts_original'))

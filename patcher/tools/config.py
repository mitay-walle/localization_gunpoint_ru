"""Paths shared by the tools.

The game folder and the save folder are chosen by the player (build.py --game / --saves,
or a folder dialog) and remembered in settings.json. Nothing is looked up in Steam.
In the standalone patcher (PyInstaller) PROJECT is the folder of GunpointPatcher.exe and
the reference table (en.csv + exe_refs.json) is bundled inside the exe.
"""
import json
import os
import re
import sys

FROZEN = getattr(sys, 'frozen', False)
PROJECT = os.path.dirname(os.path.abspath(sys.executable if FROZEN else os.path.dirname(os.path.abspath(__file__))))

TRANSLATION = os.path.join(PROJECT, 'translation')         # <lang>.csv + exe_refs.json
DATA = os.path.join(sys._MEIPASS, 'data') if FROZEN else TRANSLATION  # en.csv + exe_refs.json
FONTS = os.path.join(PROJECT, 'fonts')                     # editable BMFont .fnt + _0.png
WAD_ORIG = os.path.join(PROJECT, 'wad_orig')               # unpacked original Gunpoint.wad (fontbuild, export)
SETTINGS = os.path.join(PROJECT, 'settings.json')

GAME = None      # set by set_game()
SAVES = None     # optional, set by set_saves()
EXE_ORIG = WAD_ORIG_FILE = PDB = SOURCE_GPC = None


def winpath(p):
    """Accept Git Bash style /g/dir as well as G:/dir."""
    m = re.match(r'^/([a-zA-Z])(/.*)?$', p)
    return f'{m.group(1).upper()}:{m.group(2) or "/"}' if m else p


def load_settings():
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(**values):
    s = load_settings()
    s.update(values)
    try:
        with open(SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # read-only folder: just ask again next time


def is_game(path):
    return all(os.path.exists(os.path.join(path, f)) for f in ('Gunpoint.exe', 'Gunpoint.wad'))


def same_path(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(winpath(a))) == os.path.normcase(os.path.abspath(winpath(b)))


def check_game(path):
    if not is_game(path):
        raise SystemExit(f'"{path}" is not the Gunpoint folder: Gunpoint.exe / Gunpoint.wad not found')


def set_game(path):
    global GAME, EXE_ORIG, WAD_ORIG_FILE, PDB, SOURCE_GPC
    path = os.path.abspath(winpath(path))
    check_game(path)
    GAME = path
    EXE_ORIG = os.path.join(GAME, 'Gunpoint.exe.orig')
    WAD_ORIG_FILE = os.path.join(GAME, 'Gunpoint.wad.orig')
    PDB = os.path.join(GAME, 'Gunpoint.exe.pdb')
    # original English scripts: the backup made by the first install, or the untouched folder
    SOURCE_GPC = os.path.join(GAME, 'Scripts.orig')
    if not os.path.isdir(SOURCE_GPC):
        SOURCE_GPC = os.path.join(GAME, 'Scripts')


def set_saves(path):
    global SAVES
    path = os.path.abspath(winpath(path))
    if not os.path.isdir(path):
        raise SystemExit(f'save folder "{path}" does not exist')
    SAVES = path


def init(game=None, saves=None, ask=True, with_saves=True):
    """Resolve the folders: command line > settings.json > the folder of the patcher > dialog.
    saves: None = from settings / default <game>/Savegames, '' = leave saves alone."""
    s = load_settings()
    if not game:
        if s.get('game') and is_game(s['game']):
            game = s['game']
        elif is_game(PROJECT):
            game = PROJECT
        elif ask:
            game = ask_folder('Выберите папку с игрой Gunpoint (где лежит Gunpoint.exe)')
    if not game:
        raise SystemExit('game folder not set: --game "<path to Gunpoint>"')
    set_game(game)
    if not with_saves:
        save_settings(game=GAME)
        return
    if saves is None:
        saves = s.get('saves') if same_path(s.get('game'), GAME) else None  # saves of another game folder: no
        if saves is None or (saves and not os.path.isdir(saves)):
            default = os.path.join(GAME, 'Savegames')
            saves = default if os.path.isdir(default) else ''
    if saves:
        set_saves(saves)
    save_settings(game=GAME, saves=SAVES or '')


def ask_folder(title, initial=None):
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title=title, initialdir=initial, mustexist=True)
        root.destroy()
        return path or None
    except Exception:
        try:
            return input(title + ': ').strip().strip('"') or None
        except EOFError:
            return None

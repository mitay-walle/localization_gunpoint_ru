r"""Build a language from translation/<lang>.csv and install it into the game folder.

  python build.py --game "D:\Games\Gunpoint" [--saves "D:\Games\Gunpoint\Savegames"]
  python build.py                 # folders from the previous run (settings.json) or a dialog
  python build.py --lang ko       # another table
  python build.py gpc exe         # only some steps: gpc, exe, wad, saves
  python build.py --no-saves      # leave save games alone
  python build.py --restore       # put the original game files back

The game folder is chosen by the player (nothing is looked up in Steam); the save folder
defaults to <game>/Savegames. Both are remembered in settings.json.

gpc: Scripts.orig + translations -> <game>/Scripts (UTF-8)
exe: Gunpoint.exe.orig + translations -> <game>/Gunpoint.exe (also teaches the game to read
     .gpc as UTF-8, see tools/exestrings.py)
wad: Gunpoint.wad.orig + fonts/*.fnt + *_0.png -> <game>/Gunpoint.wad
saves: translates the text already stored in existing save games (see tools/saves.py)

Fonts are not regenerated here: fonts/ is the editable source. After adding text with new
characters run `python tools/fontbuild.py` (or put your own BMFont files into fonts/).
The same install runs in the standalone patcher (patcher.py), see tools/install.py.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))
import config, install


def option(args, name):
    if name in args:
        i = args.index(name)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return None


if __name__ == '__main__':
    args = sys.argv[1:]
    lang = option(args, '--lang') or 'ru'
    game, save_dir = option(args, '--game'), option(args, '--saves')
    if '--no-saves' in args:
        args.remove('--no-saves')
        save_dir = ''
    restore = '--restore' in args
    if restore:
        args.remove('--restore')
    config.init(game, save_dir)
    if restore:
        install.restore()
    else:
        install.install([os.path.join(config.TRANSLATION, f'{lang}.csv')], config.FONTS, args or install.STEPS)

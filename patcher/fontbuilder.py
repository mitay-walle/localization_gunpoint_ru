r"""Standalone font builder: GunpointFontBuilder.exe (built by make_release.py with PyInstaller).

Put it next to the translation tables (any *.csv here or one or two folders deeper, same as
GunpointPatcher.exe) and run it: for each of the 12 game fonts it copies the original glyphs
from the game archive and renders every character the translations use that the font lacks
(see tools/fontbuild.py). Result: fonts/<name>.fnt + fonts/<name>_0.png, previews in
fonts/_preview/. GunpointPatcher.exe in the same folder then installs them.

  GunpointFontBuilder.exe                      # asks for the game folder once (or sits in it)
  GunpointFontBuilder.exe --game "D:\Games\Gunpoint" [file.csv ...]

TTFs come from ttf/ next to the exe (put your own there to override), then from the Windows
font folder; Hangul, CJK and kana use Malgun Gothic, Microsoft YaHei and Yu Gothic.
"""
import os, sys, traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))
import config, fontbuild, install
from patcher import ask, option


def main(args):
    print('Gunpoint — генератор шрифтов\n')
    config.init(option(args, '--game'), with_saves=False)
    print(f'Игра: {config.GAME}')
    ref, _ = install.reference()
    tables = [os.path.abspath(config.winpath(a)) for a in args] or \
        [p for p, _ in install.find_tables(config.PROJECT, ref)]
    if not tables:
        raise SystemExit(f'Рядом с программой ({config.PROJECT}) нет файла перевода *.csv')
    gpc, exe = install.load(tables, ref)
    print()
    fontbuild.main(list(gpc.values()) + list(exe.values()), fontbuild.original_wad(), config.FONTS)
    print('\nГотово. Проверьте превью в fonts/_preview и запустите GunpointPatcher.exe.')


if __name__ == '__main__':
    code = 0
    try:
        main(sys.argv[1:])
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f'\nОшибка: {e.code}')
            code = 1
    except Exception:
        traceback.print_exc()
        code = 1
    if config.FROZEN and sys.stdin and sys.stdin.isatty():
        ask('\nНажмите Enter, чтобы закрыть окно...')
    sys.exit(code)

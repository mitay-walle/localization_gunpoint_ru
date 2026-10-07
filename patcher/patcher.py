r"""Standalone patcher: GunpointPatcher.exe (built by make_release.py with PyInstaller).

Everything it installs lies next to it, so a translation or a font is updated by replacing a file:
  GunpointPatcher.exe
  ru.csv            translation table: translation/<lang>.csv of this project or the file
                    exported by LocalizationForum (any *.csv here or one or two folders deeper)
  fonts/            BMFont <name>.fnt + <name>_0.png (fonts missing here stay original)

  GunpointPatcher.exe                         # asks for the game folder once (or sits in it)
  GunpointPatcher.exe --game "D:\Games\Gunpoint" [--saves DIR | --no-saves] [file.csv ...]
  GunpointPatcher.exe --restore               # put the original game files back

New characters in a translation (another language)? Run GunpointFontBuilder.exe (fontbuilder.py)
in the same folder first: it renders fonts/ for every *.csv here.
"""
import os, sys, traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))
import config, install


def ask(prompt, default=''):
    try:
        return input(prompt).strip() or default
    except EOFError:
        return default


def option(args, name):
    if name in args:
        i = args.index(name)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return None


def main(args):
    print('Gunpoint — установка перевода\n')
    game, save_dir = option(args, '--game'), option(args, '--saves')
    if '--no-saves' in args:
        args.remove('--no-saves')
        save_dir = ''
    restore = '--restore' in args
    if restore:
        args.remove('--restore')
    old = config.load_settings()
    config.init(game, save_dir)
    had_saves = 'saves' in old and config.same_path(old.get('game'), config.GAME)
    print(f'Игра: {config.GAME}')

    interactive = not args and not restore and sys.stdin and sys.stdin.isatty()
    if interactive:
        restore = ask('Enter — установить перевод, R + Enter — вернуть оригинальные файлы игры: ').lower() in ('r', 'к')
    if restore:
        install.restore()
        return

    ref, _ = install.reference()
    if args:
        tables = [os.path.abspath(config.winpath(a)) for a in args]
    else:
        found = install.find_tables(config.PROJECT, ref)
        if not found:
            raise SystemExit(f'Рядом с патчером ({config.PROJECT}) нет файла перевода *.csv')
        if len(found) > 1:
            for i, (p, n) in enumerate(found, 1):
                print(f'  {i}. {os.path.relpath(p, config.PROJECT)} — {n} строк')
            k = ask(f'Какой перевод установить (1-{len(found)}, Enter — 1): ', '1')
            if not k.isdigit() or not 1 <= int(k) <= len(found):
                raise SystemExit('Нет такого номера')
            found = [found[int(k) - 1]]
        tables = [found[0][0]]

    if config.SAVES and save_dir is None and not had_saves and interactive:
        if ask(f'Перевести тексты в сохранениях ({config.SAVES})? Будет сделана копия папки. [Y/n]: ',
               'y').lower() not in ('y', 'yes', 'д', 'да', 'н'):
            config.SAVES = None
            config.save_settings(saves='')
    print(f'Сохранения: {config.SAVES or "не трогать"}\n')

    install.install(tables, config.FONTS)
    print('\nГотово. Запускайте игру.')


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

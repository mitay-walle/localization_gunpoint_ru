"""Build the player packages.

  python make_release.py [lang]       # -> dist/Gunpoint-<lang>-patcher.zip (GunpointPatcher.exe + table + fonts)
  python make_release.py fontbuilder  # -> dist/GunpointFontBuilder.zip (GunpointFontBuilder.exe + README)

Needs PyInstaller (pip install pyinstaller). Both exes bundle the reference table
(translation/en.csv + exe_refs.json); translations and fonts stay next to them as files.
"""
import os, shutil, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(ROOT, 'translation')

README = """Gunpoint — перевод ({lang})

1. Распакуйте архив куда угодно (можно прямо в папку игры).
2. Запустите GunpointPatcher.exe и при первом запуске укажите папку игры
   (Steam: Gunpoint > Управление > Просмотреть локальные файлы).
3. Enter — установить перевод. Запускайте игру.

Что лежит рядом с патчером и подхватывается при каждом запуске:
  {lang}.csv   — таблица перевода. Можно заменить новой версией с форума
               (файл из релиза на GitHub или выгрузка с LocalizationForum, имя любое).
  fonts/       — шрифты BMFont (.fnt + _0.png). Нет файла — остаётся оригинальный шрифт.

Оригиналы сохраняются рядом с игрой: Gunpoint.exe.orig, Gunpoint.wad.orig, Scripts.orig.
Вернуть оригинал: запустить патчер и нажать R + Enter (или GunpointPatcher.exe --restore).
Тексты, уже записанные в сохранения, тоже переводятся (перед этим делается копия папки
Savegames_backup_<дата>); игра при этом должна быть закрыта.

После обновления игры в Steam запустите патчер ещё раз.
Командная строка: GunpointPatcher.exe --game "<папка игры>" [--saves <папка> | --no-saves] [файл.csv]

Форум перевода: https://localization-forum.vercel.app/#/g/gunpoint/{lang}
Исходники: https://github.com/mitay-walle/localization_gunpoint_ru/tree/master/patcher
"""

README_FONTS = """Gunpoint — генератор шрифтов

Рендерит набор шрифтов игры (12 BMFont-шрифтов) со всеми символами, которые есть в переводе.
Нужен, если перевод использует символы, которых нет в готовых шрифтах (другой язык,
редкие знаки). Для русского перевода шрифты уже лежат в архиве патчера.

1. Положите GunpointFontBuilder.exe в папку с GunpointPatcher.exe и таблицей перевода (*.csv).
2. Запустите, при первом запуске укажите папку игры.
3. Шрифты появятся в fonts/, превью — в fonts/_preview/. Затем запустите GunpointPatcher.exe.

Оригинальные глифы копируются из архива игры без изменений, недостающие рендерятся из TTF
того же начертания (Arial, Georgia, Century Gothic) с размером, подобранным по латинице;
хангыль — Malgun Gothic, иероглифы — Microsoft YaHei, кана — Yu Gothic.
Свой TTF с тем же именем файла можно положить в папку ttf/ рядом с программой.
Командная строка: GunpointFontBuilder.exe --game "<папка игры>" [файл.csv ...]

Исходники: https://github.com/mitay-walle/localization_gunpoint_ru/tree/master/patcher
"""


def pyinstaller(name, script, *extra):
    build = os.path.join(ROOT, 'build')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--console',
                    '--name', name, '--paths', os.path.join(ROOT, 'tools'),
                    '--add-data', f'{os.path.join(TR, "en.csv")}{os.pathsep}data',
                    '--add-data', f'{os.path.join(TR, "exe_refs.json")}{os.pathsep}data',
                    '--exclude-module', 'capstone', '--exclude-module', 'numpy', *extra,
                    '--distpath', os.path.join(build, 'dist'), '--workpath', os.path.join(build, 'work'),
                    '--specpath', build, os.path.join(ROOT, script)], check=True)
    return os.path.join(build, 'dist', name + '.exe')


def zip_dir(pkg, top, out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(pkg):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.join(top, os.path.relpath(p, pkg)))
    print(f'{out} ({os.path.getsize(out) // 1024} KB)')


def package(name):
    pkg = os.path.join(ROOT, 'dist', name)
    shutil.rmtree(pkg, ignore_errors=True)
    os.makedirs(pkg)
    return pkg


def patcher(lang):
    exe = pyinstaller('GunpointPatcher', 'patcher.py', '--collect-binaries', 'keystone', '--exclude-module', 'fontTools')
    pkg = package(f'Gunpoint-{lang}')
    os.makedirs(os.path.join(pkg, 'fonts'))
    shutil.copy2(exe, pkg)
    shutil.copy2(os.path.join(TR, f'{lang}.csv'), pkg)
    for f in sorted(os.listdir(os.path.join(ROOT, 'fonts'))):
        if f.endswith(('.fnt', '.png')):
            shutil.copy2(os.path.join(ROOT, 'fonts', f), os.path.join(pkg, 'fonts'))
    with open(os.path.join(pkg, 'README.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(README.format(lang=lang))
    zip_dir(pkg, f'Gunpoint-{lang}', os.path.join(ROOT, 'dist', f'Gunpoint-{lang}-patcher.zip'))


def fontbuilder():
    exe = pyinstaller('GunpointFontBuilder', 'fontbuilder.py', '--exclude-module', 'keystone')
    pkg = package('GunpointFontBuilder')
    shutil.copy2(exe, pkg)
    with open(os.path.join(pkg, 'README.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(README_FONTS)
    zip_dir(pkg, 'GunpointFontBuilder', os.path.join(ROOT, 'dist', 'GunpointFontBuilder.zip'))


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'ru'
    fontbuilder() if arg == 'fontbuilder' else patcher(arg)

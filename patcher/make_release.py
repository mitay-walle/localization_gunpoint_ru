"""Build the player package: GunpointPatcher.exe + translation + fonts in one zip.

  python make_release.py [lang]     # -> dist/Gunpoint-<lang>-patcher.zip

Needs PyInstaller (pip install pyinstaller). The exe bundles the reference table
(translation/en.csv + exe_refs.json); the translation and the fonts stay next to it as files.
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


def main(lang):
    build = os.path.join(ROOT, 'build')
    dist = os.path.join(ROOT, 'dist')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--console',
                    '--name', 'GunpointPatcher', '--paths', os.path.join(ROOT, 'tools'),
                    '--add-data', f'{os.path.join(TR, "en.csv")}{os.pathsep}data',
                    '--add-data', f'{os.path.join(TR, "exe_refs.json")}{os.pathsep}data',
                    '--collect-binaries', 'keystone',
                    '--exclude-module', 'capstone', '--exclude-module', 'fontTools', '--exclude-module', 'numpy',
                    '--distpath', os.path.join(build, 'dist'), '--workpath', os.path.join(build, 'work'),
                    '--specpath', build, os.path.join(ROOT, 'patcher.py')], check=True)

    pkg = os.path.join(dist, f'Gunpoint-{lang}')
    shutil.rmtree(pkg, ignore_errors=True)
    os.makedirs(os.path.join(pkg, 'fonts'))
    shutil.copy2(os.path.join(build, 'dist', 'GunpointPatcher.exe'), pkg)
    shutil.copy2(os.path.join(TR, f'{lang}.csv'), pkg)
    for f in sorted(os.listdir(os.path.join(ROOT, 'fonts'))):
        if f.endswith(('.fnt', '.png')):
            shutil.copy2(os.path.join(ROOT, 'fonts', f), os.path.join(pkg, 'fonts'))
    with open(os.path.join(pkg, 'README.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(README.format(lang=lang))

    out = os.path.join(dist, f'Gunpoint-{lang}-patcher.zip')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(pkg):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.join(f'Gunpoint-{lang}', os.path.relpath(p, pkg)))
    print(f'{out} ({os.path.getsize(out) // 1024} KB)')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'ru')

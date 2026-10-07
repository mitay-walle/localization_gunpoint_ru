# Gunpoint — перевод

Весь переводимый текст в одной таблице на язык: `translation/<lang>.csv`
(разговоры из `Scripts/*.gpc` + строки, зашитые в `Gunpoint.exe`).

## Патчер для игроков
`GunpointPatcher.exe` — установка без Python. Всё, что он ставит, лежит рядом с ним файлами:
```
Gunpoint-ru/
  GunpointPatcher.exe
  ru.csv        таблица перевода (эта же translation/ru.csv или выгрузка с LocalizationForum — имя любое)
  fonts/        шрифты BMFont (.fnt + _0.png)
  README.txt
```
Запуск двойным щелчком: при первом запуске спрашивает папку игры (или берёт свою, если лежит в ней),
Enter — установить, R + Enter — вернуть оригинал. Подхватывает любые `*.csv` рядом (и на 1–2 уровня глубже);
если подходящих несколько — спрашивает, какой ставить. Командная строка:
`GunpointPatcher.exe --game "<папка игры>" [--saves <папка> | --no-saves] [--restore] [файл.csv]`.

Таблица читается по `id`: текст строки — `translation`, а если он пуст — `original`; строки, совпадающие
с английским оригиналом, пропускаются. Поэтому годится и наша таблица (английский в `original`),
и файл с форума (перевод записан поверх `original`). Эталон (`en.csv` + `exe_refs.json`) зашит в exe.

Собрать архив для релиза (нужен `pip install pyinstaller`):
```bash
python make_release.py ru
```
→ `dist/Gunpoint-ru-patcher.zip`.

## Генератор шрифтов
`GunpointFontBuilder.exe` (`fontbuilder.py`) — отдельное приложение, рендерит набор шрифтов под перевод.
Кладётся рядом с патчером и таблицами (`*.csv`), берёт оригинальные шрифты из `Gunpoint.wad.orig`
(или `Gunpoint.wad` до первой установки) и пишет `fonts/<имя>.fnt` + `_0.png` и превью `fonts/_preview/`.
Символы берутся из всех найденных таблиц; TTF — из папки `ttf/` рядом с программой, затем из
`C:\Windows\Fonts`. Командная строка: `GunpointFontBuilder.exe --game "<папка игры>" [файл.csv ...]`.
Сборка: `python make_release.py fontbuilder` → `dist/GunpointFontBuilder.zip`.

## Сборка и установка из исходников
Из папки проекта. Папку с игрой указывает игрок (в Steam ничего не ищется); сохранения по умолчанию —
`<игра>/Savegames`:
```bash
python build.py --game "D:\Games\Gunpoint" --saves "D:\Games\Gunpoint\Savegames"
```
Папки запоминаются в `settings.json`, дальше достаточно `python build.py`. Без `--game` при первом
запуске откроется диалог выбора папки.
- `python build.py --lang ko` — другой язык
- `python build.py gpc exe` — только часть шагов (`gpc`, `exe`, `wad`, `saves`)
- `python build.py --no-saves` — не трогать сохранения
- `python build.py --restore` — вернуть оригинальные файлы игры

Что делает (общий код с патчером — `tools/install.py`):
- первый запуск сохраняет оригиналы рядом с игрой: `Gunpoint.exe.orig`, `Gunpoint.wad.orig`, `Scripts.orig/`;
  каждая установка начинается с них, так что повторная установка (или другой язык) не накладывается.
  Если файлы игры уже изменены, а копий нет — просит проверить целостность файлов в Steam
- `gpc` — `Scripts.orig/*.gpc` + переводы → `<игра>/Scripts` в UTF-8
- `exe` — `Gunpoint.exe.orig` + переводы → `<игра>/Gunpoint.exe`; заодно игра начинает читать `.gpc` как UTF-8
- `wad` — `Gunpoint.wad.orig` + шрифты из `fonts/` → `<игра>/Gunpoint.wad` (без распаковки архива);
  предупреждает, если в переводе есть символы, которых нет в шрифтах
- `saves` — переводит текст, уже записанный в сохранения. Сейв — снимок состояния GML: задания, имена и т. п.,
  созданные до перевода, хранятся в нём по-английски. Строка в `.gun`: `[u32 id][u32 тип=3][u32 длина][UTF-16][00 00]`,
  размеров и контрольных сумм нет. Перед первым изменением — копия `Savegames_backup_<дата>`;
  при запущенной игре шаг пропускается. Что было применено — `<игра>/Gunpoint.saves.json`
  (по нему `--restore` возвращает английский текст)

Нужны Python 3 и пакеты: `pip install pefile capstone keystone-engine pillow fonttools`.

## Таблица `translation/<lang>.csv`
UTF-8 с BOM, открывается в Excel / LibreOffice / Google Sheets. Пустой `translation` — остаётся оригинал.

| kind | что это | переводить? |
|---|---|---|
| `line` | реплика собеседника в разговоре (`.gpc`, `Them:`) | да |
| `choice` | вариант ответа Конвэя (`.gpc`, `Me:`) | да |
| `text` | брифинги, письма, заметки, подсказки, меню, реплики в уровнях | да |
| `word` | одно слово / метка (`Credits`, `BULLFROG`, `F5`) | да, глядя на `context` |
| `check` | строка сравнивается в логике или служит ключом (`Patrol`, `Dead`, `Up`) | только если видна игроку |
| `tech` | файлы, id достижений Steam, функции FMOD, код движка | нет |

- `id`: `gpc:<файл>:<номер строки>` или `exe:<адрес строки в exe>`
- `context`: для `.gpc` — сцена и говорящий; для exe — GML-функция и куда строка передаётся дальше
  (`SetCaseNotes`, `SetLaptopText`, `AddLine`, `ChoiceBubble`, `GuidanceBubble`…)
- `#` в строках exe — перенос строки, сохранять. В `.gpc` перевод — одна строка.
- Строка exe переводится сразу во всех местах, где встречается этот текст.

Обновить таблицу (новая версия игры / новые строки), переводы сохраняются:
```bash
python tools/table.py extract ru
python tools/table.py extract ru --import-gpc <папка с переведёнными .gpc>
python tools/table.py stats
```

## Шрифты `fonts/`
Обычный BMFont: `<имя>.fnt` (XML или текстовый) + `<имя>_0.png` (8 бит, серый+альфа или RGBA).
Любой файл можно заменить своим (например, из AngelCode BMFont), `build.py` упакует его в игру.
Ограничения игры: **одна страница** на шрифт (делайте текстуру больше — размер любой, до 4096),
имена файлов — как у оригинала (12 шрифтов: `fArial8`, `fArial10`, `fChoiceText`, `fConsolas`,
`fGeorgia`, `fGeorgia16`, `fLarge`, `fMissionText`, `fRatings`, `fTutorial`, `fTutorialBold`, `font10`).
Шрифт, которого нет в `fonts/`, остаётся оригинальным.

Сгенерировать заново (после добавления текста с новыми символами):
```bash
python tools/fontbuild.py          # по всем таблицам translation/*.csv
python tools/fontbuild.py ru       # только по одной
```
Оригинальные глифы переносятся из атласа без изменений; недостающие символы рендерятся из того же
TTF с размером, подобранным по совпадению с латиницей. Хангыль — Malgun Gothic, иероглифы — Microsoft
YaHei, кана — Yu Gothic. `fLarge` (Estrangelo Edessa, нет в Windows 11) — Century Gothic Bold.
Атлас растёт сам. Превью — `fonts/_preview/`. Оригинальные шрифты читаются прямо из архива игры.
Свой TTF с тем же именем файла можно положить в `ttf/`. Оригиналы в формате BMFont — `fonts_original/`
(`python tools/fontpack.py export`).

## Как устроена игра (найдено дизассемблированием, PDB лежит рядом с exe)
- `Scripts/*.gpc` читает `gml::ReadInScriptFile` → `file_text_read_string`: строка читается байтами
  и расширяется `movsx` (байт `0xC0` → `U+FFC0`). Патч `exe` заменяет это на декодирование UTF-8
  (`MultiByteToWideChar`, адрес берётся через `LoadLibraryExA`/`GetProcAddress` при первом вызове).
- Строки в exe — UTF-16 литералы в `.rdata`, на них указывает `push offset` → `PGMLVar(const wchar_t*)`.
  Патч кладёт переводы в новую секцию `.rutext` и перенаправляет указатели. ASLR и релокаций нет.
  Ссылки из кода движка (парсер шрифтов, Lua, Phyre) не трогаются: например, `x` — ещё и XML-атрибут шрифта.
- `Gunpoint.wad`: `u32 начало данных, u32 кол-во, {u32 длина имени, имя, u32 размер, u32 смещение}`.
  Файлы ищутся сначала в архиве, с диска — только если в архиве нет; текстуры (`.phyre`) — только из архива.
- Текстуры шрифтов: PhyreEngine `PTexture2D`, `L8`, строки снизу вверх; размер — пара `u32` после имени
  файла, `maxMipLevel` за 12 байт до неё, размер данных — `u32` по смещению `0x50`.
- `GL/gunpoint_localization.bin` загружается, но строки из него никто не читает;
  `CLocalization::GetCurrentLanguage` всегда `"English"`.

## Папки
- `translation/` — таблицы, `en.csv` (эталон) и `exe_refs.json` (где в exe ссылки на строки)
- `fonts/` — шрифты для игры (редактируемые), `fonts_original/` — оригиналы для справки
- `wad_orig/` — распакованный оригинальный wad (нужен только `fontbuild.py` и `fontpack.py export`)
- `tools/` — `install.py`, `table.py`, `exestrings.py`, `gpcstrings.py`, `fontbuild.py`, `fontpack.py`,
  `wadtool.py`, `saves.py`, `forum.py`, `config.py`
- `build.py` — установка из исходников, `patcher.py` / `fontbuilder.py` + `make_release.py` — приложения для игроков

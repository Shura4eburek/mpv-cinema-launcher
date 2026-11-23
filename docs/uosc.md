# uosc: справка для проекта

Версия в проекте: **5.13.0**, каталог `mpv-profiles/player/uosc/`, лицензия LGPL-2.1 (`mpv-profiles/player/LICENSE-uosc.txt`).

Источники версии 5.13.0: [README](https://github.com/tomasklaen/uosc/blob/5.13.0/README.md), [все опции `uosc.conf`](https://github.com/tomasklaen/uosc/blob/5.13.0/src/uosc.conf), [API для скриптов](https://github.com/tomasklaen/uosc/wiki), [API меню](https://github.com/tomasklaen/uosc/wiki/Menu-API). Вики общая для всех версий: при сомнении сверяться с `main.lua`.

## Как uosc подключён

`presets.py` передаёт всё аргументами запуска, глобальный конфиг mpv не меняется:

- `--script=.../uosc`, `--script=.../cinema.lua`, `--osd-fonts-dir=.../fonts`, `--no-osc`, `--osd-bar=no`, `--border=no`;
- опции: `--script-opts-append=uosc-<опция>=<значение>`;
- сейчас заданы `languages=ru`, `controls` (`UOSC_CONTROLS`), `autohide=yes`, огромные `proximity_in` и `proximity_out`: панель показывается при любом движении мыши и скрывается вместе с курсором через `cursor-autohide`.

Запятая в `controls` часть значения, поэтому эта опция идёт только через `--script-opts-append`.

## Опции, важные для проекта

| Опция | По умолчанию | Смысл |
|-------|--------------|-------|
| `controls` | длинный список | Кнопки над шкалой, см. ниже |
| `top_bar` | `no-border` | Верхняя полоса: `never`, `no-border`, `always` |
| `top_bar_controls` | `right` | Кнопки окна в верхней полосе: `no`, `left`, `right` |
| `top_bar_title` | `yes` | Заголовок: `no`, `yes` или шаблон |
| `disable_elements` | пусто | Отключить: `window_border`, `top_bar`, `timeline`, `controls`, `volume`, `idle_indicator`, `audio_indicator`, `buffering_indicator`, `pause_indicator` |
| `volume` | `right` | Шкала громкости: `none`, `left`, `right` |
| `progress` | `windowed` | Тонкая постоянная шкала: `windowed`, `fullscreen`, `always`, `never` |
| `{элемент}_persistency` | пусто | Всегда показывать при состояниях `paused`, `audio`, `image`, `video`, `idle`, `windowed`, `fullscreen` |
| `scale`, `scale_fullscreen` | `1`, `1.3` | Масштаб интерфейса в окне и в полном экране |
| `autoload` | `no` | При `yes` сам задаёт `keep-open=yes` и `keep-open-pause=no` и открывает следующий файл каталога. Для потоков не подходит |
| `timeline_step` | `5` | Перемотка колесом над шкалой, секунды |
| `chapter_ranges` | заставки и реклама | Подсветка диапазонов глав на шкале |

## Кнопки панели (`controls`)

Формат элемента: `[<условия>]элемент[:параметры][#значок[>порог]][?подсказка]`.

- Готовые: `play-pause`, `menu`, `subtitles`, `audio`, `video`, `playlist`, `chapters`, `editions`, `stream-quality`, `open-file`, `items`, `next`, `prev`, `first`, `last`, `audio-device`, `fullscreen`, `loop-playlist`, `loop-file`, `shuffle`, `autoload`.
- `command:{значок}:{команда}`: кнопка с командой. Так сделана «Качество картинки» в `UOSC_CONTROLS`.
- `toggle:{значок}:{свойство}[@владелец]` и `cycle:{значок}:{свойство}[@владелец]:{значение}[={значок}][!]/...`: переключатель свойства; `!` выделяет кнопку активной.
- `button:{имя}`: кнопка, которой управляет скрипт через `set-button`.
- `speed[:масштаб]`, `gap[:масштаб]`, `space`.
- Условия: `<a,b+!c>` значит `a ИЛИ (b И НЕ c)`. Доступны `idle`, `image`, `audio`, `video`, `has_many_video`, `has_image`, `has_audio`, `has_many_audio`, `has_sub`, `has_many_sub`, `has_many_edition`, `has_chapter`, `stream`, `has_playlist` и любое свойство mpv, включая `user-data/...` из скрипта.
- Значки: [Material Icons Rounded](https://fonts.google.com/icons?icon.platform=web&icon.set=Material+Icons&icon.style=Rounded).

## Сообщения скриптов

Отправка: `mp.commandv('script-message-to', 'uosc', <сообщение>, ...)`. Так же работает через канал управления mpv.

| Сообщение | Смысл |
|-----------|-------|
| `set-button <имя> <json>` | Создать или обновить кнопку: `{icon, active?, badge?, command?, tooltip?, hide?}` |
| `set <свойство> <значение>` | Внешнее свойство для `toggle`, `cycle` и значков с `@скрипт` |
| `open-menu <json> [подменю]` | Открыть своё меню |
| `update-menu <json>` | Обновить открытое меню с тем же `type` |
| `close-menu [type]` | Закрыть меню |
| `disable-elements <скрипт> <элементы>` | Скрипт отключает элементы; пустая строка возвращает |
| `toggle-elements <элементы>` | Переключить постоянный показ: `timeline`, `controls`, `volume`, `top_bar`, `speed` |
| `set-min-visibility <0-1> [элементы]` | Минимальная видимость: держать элементы показанными |
| `flash-elements <элементы>` | Показать ненадолго: также `progress`, `pause_indicator` |
| `overwrite-binding <команда> [своя команда]` | Заменить встроенную команду uosc |

uosc рассылает `uosc-version <версия>` при запуске.

Меню: `{type, title, items: [{title, hint, icon, value, active, keep_open, ...}], search_style, ...}`. `value` строка идёт в `mp.command`, массив в `mp.commandv`. Иконка `spinner` показывает загрузку. Есть режим `callback` для кнопок у пунктов меню. Именно так `cinema.lua` рисует меню «Качество картинки».

## Команды для клавиш

`script-binding uosc/<команда>`: `menu`, `menu-blurred`, `subtitles`, `audio`, `video`, `playlist`, `chapters`, `next`, `prev`, `toggle-ui`, `toggle-progress`, `flash-ui`, `flash-timeline`, `flash-volume`, `flash-pause-indicator`, `keybinds` и другие. По умолчанию не назначены, кроме навигации в открытом меню.

## Применение в проекте

**Плеер на странице (`--wid`)**:
- Кнопки окна не нужны: `top_bar_controls=no`, при необходимости `top_bar=never`. Закрытие заменяется кнопкой `command:close:quit`.
- `--keep-open=yes` оставляет плеер после конца фильма. mpv по умолчанию ставит его на паузу: это и нужно.
- При `--wid` окно mpv отключено (`WS_DISABLED`), и uosc не видит мышь, пока приложение не включит окно. См. `player_surface.rs`.

**Кнопка «Следующая серия»** (ещё не сделана):
- В `controls` добавить `button:next_episode`.
- Из `cinema.lua` следить за `time-remaining`, вызывать `set-button` с `hide=false` ближе к концу и с `command` в виде `script-message-to cinema next-episode`.
- Панель видна только при движении мыши, поэтому у конца серии нужны `set-min-visibility 1 controls` или своё уведомление: иначе кнопку не заметят.
- Команду получает backend через канал управления и запускает следующую серию.

**Обновление uosc**: заменить каталог и лицензию, сверить этот файл и список опций с новым `uosc.conf`. Встроенную команду `uosc/update` не использовать: она обновляет копию в конфиге пользователя.

# Implementation Plan: Мой список со статусами просмотра

**Branch**: `010-watchlist-statuses` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-watchlist-statuses/spec.md`

## Summary

Список хранится в `watchlist.json` рядом с `settings.json` и пишется атомарно, тем же способом. Логика списка (ключи, статусы, серии, пометки удаления, слияние записей) живёт в новом модуле Python `watchlist.py`. Интерфейс обращается к нему через новые методы протокола `backend.py`. Страница kinogo не содержит id IMDb и КиноПоиска, поэтому id IMDb находится отдельно, через сервис подсказок IMDb, по оригинальному названию, году и типу. Пока id не найден, работает запасной ключ. Конец просмотра отслеживается через канал управления mpv: сейчас он есть только у встроенного плеера, теперь он подключается для обоих режимов.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.9, Svelte 5, Rust 1.77+ (без изменений)

**Primary Dependencies**: Tauri 2, mpv, `requests` (уже есть); новых зависимостей нет

**Storage**: `watchlist.json` в `settings.data_dir()`, атомарная запись через временный файл и `os.replace`

**Testing**: pytest (модуль списка, методы протокола, разбор ответа IMDb, конец просмотра), Vitest (логика фильтров и счётчиков), `npm run check`; ручная проверка по [quickstart.md](quickstart.md)

**Target Platform**: Windows 11 x64, macOS (без встроенного плеера)

**Project Type**: настольное приложение

**Performance Goals**: «Мой список» с 500 тайтлами открывается и фильтруется менее чем за 1 с; изменение статуса сохраняется менее чем за 100 мс

**Constraints**: работа без сети и без аккаунта; поиск id не задерживает открытие страницы; формат файла готов к будущей синхронизации (`updated_at`, пометки удаления)

**Scale/Scope**: новый `watchlist.py`, новый `imdb.py`; правки `backend.py`, `player_ipc.py`, `presets.py` (канал управления для отдельного окна), `api.ts`, `App.svelte`, `Movie.svelte`; новые `screens/Watchlist.svelte`, `components/StatusPicker.svelte`

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет. После дизайна без изменений.

## Project Structure

### Documentation (this feature)

```text
specs/010-watchlist-statuses/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/backend-watchlist.md
└── tasks.md             # создаёт /speckit-tasks
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── watchlist.py         # новый: записи, ключи, статусы, серии, пометки удаления, атомарная запись
├── imdb.py              # новый: поиск id IMDb по названию, году и типу
├── backend.py           # методы watchlist_*, параметр watch в play, событие watch_completed
├── player_ipc.py        # наблюдение duration и eof-reached
└── presets.py           # канал управления и для отдельного окна

app/src/
├── lib/api.ts           # типы и методы списка
├── lib/logic.ts         # фильтр, счётчики, сортировка
├── components/StatusPicker.svelte   # новый: выпадающий список статуса под постером
├── screens/Watchlist.svelte         # новый: «Мой список»
├── screens/Movie.svelte # статус, отметки серий, N / M
└── App.svelte           # кнопка «Мой список» в шапке, предложение «Просмотрено»

tests/unit/
├── test_watchlist.py    # новый
├── test_imdb.py         # новый
├── test_backend.py
└── test_player_ipc.py
```

**Structure Decision**: Предметная логика остаётся в Python, как и раньше. Интерфейс только показывает данные и отправляет действия. Сеть для поиска id выполняется в очереди `io`, страница фильма её не ждёт.

## Этапы

1. **Хранилище (основа)**: `watchlist.py`: модель, ключи, атомарная запись, повреждённый файл, пометки удаления, перенос записи с запасного ключа.
2. **Статус на странице (US1)**: методы `watchlist_get` / `watchlist_set_status` / `watchlist_remove`, `StatusPicker` под постером.
3. **«Мой список» (US2)**: `watchlist_list`, экран с фильтрами, переход на страницу тайтла.
4. **id IMDb**: `imdb.py`, `watchlist_resolve` в фоне после открытия страницы, перенос записи.
5. **Серии (US3)**: `watchlist_set_episode`, отметки в списке серий, N / M.
6. **Автоматика (US4)**: параметр `watch` в `play`, канал управления для обоих режимов, событие `watch_completed`, предложение «Просмотрено».

# Implementation Plan: Новый интерфейс приложения и плеера

**Branch**: `003-app-player-ui` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-app-player-ui/spec.md`

## Summary

Окно приложения переписывается на Tauri 2: интерфейс на Svelte и TypeScript, тонкий слой на Rust
управляет окном и Python-процессом. Python остаётся единственным местом логики: скрапер, зеркала,
профили, запуск mpv и настройки доступны через JSON-протокол по stdin и stdout. Плеер остаётся
отдельным окном mpv с `uosc` и собственным скриптом `cinema.lua`. CLI `mpvplay` не меняется.

## Technical Context

**Language/Version**: Rust 1.97, TypeScript 5.9 (`svelte-check` не поддерживает 7), Svelte 5, Python 3.10+, Lua (скрипты mpv)

**Primary Dependencies**: Tauri 2.12 (стабильная ветка, не 3.0-alpha), Vite 8, Selenium, requests, BeautifulSoup, PyInstaller, mpv 0.41, uosc 5.13.0

**Storage**: JSON-файл настроек и кэш постеров в каталогах пользователя

**Testing**: pytest (логика и протокол), `cargo test` (разбор сообщений и маршрутизация), Vitest (логика интерфейса); экраны и плеер проверяются вручную по [quickstart.md](./quickstart.md)

**Target Platform**: Windows 11 (основная, проверяется); macOS не должна сломаться, но проверить её на этой машине нельзя

**Project Type**: desktop-app

**Performance Goals**: реакция окна ≤ 200 мс во время загрузок (SC-003)

**Constraints**: не менять `%APPDATA%\mpv`; логика не дублируется между Python и Rust; профили апскейла, зеркала и CLI работают как раньше; текст с сайта считается недоверенным

**Scale/Scope**: один пользователь; 4 экрана; выдача — десятки карточек

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Конституция проекта — незаполненный шаблон, формальных гейтов нет. Как и в 001/002: ядро
переиспользуется, новая логика покрывается тестами. Отступление от простоты описано ниже.

## Project Structure

### Documentation (this feature)

```text
specs/003-app-player-ui/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/ui-and-player.md · contracts/backend-protocol.md
└── tasks.md             # следующий шаг: /speckit-tasks
```

### Source Code (repository root)

```text
app/                          # новое: приложение Tauri
├── package.json · vite.config.ts · index.html
├── src/
│   ├── App.svelte            # навигация между экранами
│   ├── screens/              # Home, Results, Movie, Settings
│   ├── components/           # карточка, сетка, сообщения о состоянии
│   ├── lib/api.ts            # типизированные вызовы протокола
│   ├── lib/logic.ts          # колонки, обрезка названий, тексты ошибок
│   └── styles/theme.css      # цвета, шрифты, отступы
└── src-tauri/
    ├── tauri.conf.json · capabilities/main.json
    └── src/
        ├── main.rs           # окно и команды
        └── backend.rs        # запуск Python, сообщения, перезапуск

mpv-profiles/player/          # новое
├── uosc/                     # uosc 5.13.0 без bin/
├── fonts/                    # шрифты uosc
├── cinema.lua                # меню «Качество картинки», состояние апскейла
└── LICENSE-uosc.txt

src/mpv_launcher/
├── backend.py                # новое: сервер протокола
├── settings.py               # новое: настройки
├── jobs.py                   # новое: очередь Selenium и потоки
├── presets.py                # аргументы скина и название
├── cli.py                    # Options.title
└── gui.py                    # удаляется CinemaApp, остаётся запуск из буфера

packaging/backend.spec · backend_entry.py             # заменяют mpvplay-*.spec и app.py
build/build_windows.ps1 · build_macos.sh              # сборка backend, затем Tauri

tests/unit/
├── test_backend.py · test_settings.py · test_jobs.py # новые
└── test_presets.py · test_gui.py                     # обновить
```

**Structure Decision**: Python-пакет остаётся в `src/`, а приложение Tauri изолировано в `app/`,
поэтому CLI и тесты Python не зависят от Node и Rust. В Rust нет логики предметной области: только
окно, запуск процесса и передача сообщений.

## Порядок реализации

1. **Проверка uosc**: запуск на тестовом видео и скриншоты. Если не заработает из отдельного
   каталога — вернуться к плану.
2. **Сквозной срез**: backend, каркас Tauri, поиск текстом на экране. Без него остальное не начинать.
3. **US1 — плеер**: uosc, название, запуск через `play`.
4. **US2 — каталог**: тема, сетка, постеры, страница фильма, состояния и ошибки.
5. **US3 — настройки и апскейл**: `settings.py`, экран настроек, `cinema.lua`.
6. **Замена старого GUI**: после проверки удалить `CinemaApp`, `customtkinter`, `pillow` и старые спеки.
7. **Сборка**: установщик Windows и проверка на нём, затем `README.md` и `AI_DEVELOPER_GUIDE.md`.

## Риски

| Риск | Что делаем |
|------|------------|
| uosc не заработает из отдельного каталога | проверка первым шагом; запасной вариант — отдельный каталог конфигурации mpv только для лаунчера |
| Запуск uosc заблокирован защитой Claude Code | нужно разрешение пользователя, иначе проверку запускает пользователь |
| Посторонний вывод ломает протокол | backend при старте забирает настоящий stdout себе и перенаправляет fd 1 в stderr, поэтому `print`, Chrome и mpv в протокол не попадают |
| Selenium Manager не найдётся в собранном backend | собрать данные пакета в спеке и проверить на установленном приложении |
| Завис stderr-канал или остался Chrome | Rust постоянно читает stderr в файл журнала; закрытие stdin завершает драйвер, через 3 секунды процесс снимается принудительно |
| Вредоносный текст с сайта | только экранированный вывод Svelte без `{@html}`, строгий CSP, проверка URL в backend |
| Установщик без подписи | Windows SmartScreen покажет предупреждение; для личного использования допустимо |
| macOS не проверить | сборочный скрипт обновляется, но работа не гарантируется до проверки на Mac |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Три среды выполнения: Rust, TypeScript, Python | выбор пользователя: интерфейс на Tauri при сохранении проверенного скрапера | CustomTkinter не даёт нужного вида; переписывание скрапера на Rust откладывается в отдельную фичу |

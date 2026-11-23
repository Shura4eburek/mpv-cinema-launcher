# Implementation Plan: Источники Lampac

**Branch**: `007-lampac-sources` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

## Summary

Lampac 1.87.6 входит в установщик и запускается приложением как отдельный локальный сервер, только по включению в настройках. Backend опрашивает его HTTP-интерфейс и показывает на странице фильма дополнительные источники, которые запускаются в существующем плеере.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.9, Svelte 5; Lampac как готовая программа на .NET 10

**Primary Dependencies**: Lampac NextGen 1.87.6, ASP.NET Core Runtime 10.0.14; в проекте новых библиотек нет

**Storage**: копия Lampac в каталоге данных приложения; настройка `lampac_enabled`

**Testing**: pytest, Vitest, `npm run check`; проверка собранного установщика в песочнице

**Target Platform**: Windows x64. На macOS блок и настройка не показываются.

**Project Type**: настольное приложение

**Performance Goals**: первые источники за 10 с; страница фильма не медленнее прежнего

**Constraints**: только `127.0.0.1`; без браузера и платных аккаунтов; при выключенной настройке нет ни процессов, ни запросов

**Scale/Scope**: 2 новых модуля Python, 1 компонент, правки сборки, настроек и страницы фильма

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет.

## Project Structure

```text
src/mpv_launcher/
├── lampac_server.py     # копирование, init.conf, порт, запуск, Job Object, состояние
├── lampac.py            # источники и варианты, разбор и отбор ответов
└── backend.py           # методы и события

app/src/
├── components/LampacSources.svelte
├── screens/Movie.svelte, Settings.svelte, MirrorCheck.svelte
└── lib/api.ts, logic.ts

build/build_windows.ps1  # загрузка с проверкой сумм, обрезка, ресурсы
app/src-tauri/tauri.bundle.json
packaging/lampac/        # init.conf, текст лицензии, ссылка на исходный код
```

## Этапы

1. **Проверка обрезки**: запуск без `.playwright` и чужих `runtimes`, подтверждение состава модулей по журналу. Результат определяет размер установщика.
2. **Сервер**: включение, состояние, остановка, закрытие вместе с приложением.
3. **Источники фильма**: блок на странице, озвучка, качество, запуск в плеере.
4. **Сборка**: установщик с Lampac, проверка из собранного установщика в песочнице.
5. **Сериалы**: сначала проба формата, затем выбор сезона и серии.

## Decisions

Подробности и данные пробы: [research.md](research.md).

## Complexity Tracking

| Отступление | Зачем | Почему проще не подошло |
|-------------|-------|-------------------------|
| Второй сервер и рантайм .NET в установщике | Выбор пользователя: всё работает сразу | Отдельная установка требует действий от зрителя |

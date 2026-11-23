# Implementation Plan: Подробная загрузка фильма и пресеты производительности

**Branch**: `005-load-progress-presets` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-load-progress-presets/spec.md`

## Summary

Backend сообщает о реальных шагах загрузки событиями `load_progress`, а экран фильма показывает их списком с таймером и действиями при долгой загрузке. Новый метод `cancel` прерывает ожидание в плеере, а если операция Selenium не реагирует, через 3 секунды закрывает Chrome. В настройках вместо качества и типа компьютера появляется пресет; вариант «Авто» определяется по названию видеокарты без запуска сторонних программ на Windows.

## Technical Context

**Language/Version**: Python 3.10+, TypeScript 5.9, Svelte 5

**Primary Dependencies**: без новых зависимостей; `ctypes` для списка видеокарт на Windows

**Storage**: поле `preset` в настройках вместо `upscale_quality` и `profile`, с переносом значений

**Testing**: pytest, Vitest; экран и плеер проверяются в установленном приложении по [quickstart.md](./quickstart.md)

**Target Platform**: Windows 11 (основная), macOS без регрессий и без проверки на устройстве

**Project Type**: desktop-app

**Performance Goals**: определение видеокарты ≤ 1 секунды, новая загрузка после отмены ≤ 5 секунд

**Constraints**: только реальные шаги, без выдуманного процента; CLI и его флаги не меняются

**Scale/Scope**: 2 новых модуля Python, 2 новых профиля mpv, новый компонент интерфейса

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Конституция проекта — незаполненный шаблон, формальных гейтов нет. После проектирования нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/005-load-progress-presets/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/backend-changes.md
└── tasks.md
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── progress.py      # новое: шаги и отмена
├── machine.py       # определение видеокарты и класс пресета
├── kinogo.py · sources.py · backend.py · settings.py · presets.py

mpv-profiles/mid.conf · low.conf   # новые профили

app/src/
├── components/LoadProgress.svelte  # новое
├── lib/logic.ts · lib/api.ts
├── screens/Movie.svelte · Settings.svelte
└── App.svelte

tests/unit/test_progress.py · test_machine_presets.py  # новые
```

**Structure Decision**: шаги передаются объектом `Progress`, поэтому `kinogo.py` не знает о протоколе, а CLI работает без него.

## Риски

| Риск | Что делаем |
|------|------------|
| Операцию Selenium нельзя прервать | через 3 секунды после отмены Chrome закрывается, следующая загрузка запускает новый |
| Таблица видеокарт устареет | неизвестная модель получает Low, а пользователь может выбрать пресет вручную |
| Mid и Low на macOS не проверены | профили без привязки к платформе, отмечено в документации |

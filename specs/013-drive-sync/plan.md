# Implementation Plan: Синхронизация «Моего списка» через Google Drive

**Branch**: `013-drive-sync` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-drive-sync/spec.md`

## Summary

Новый модуль backend `drive_sync.py`: клиент Drive v3 для файла `watchlist.json` в `appDataFolder` (через `requests` и `Backend.access_token()`) и `Syncer` — один фоновый поток, который выполняет цикл «скачать → слить → записать локально → отправить». Слияние по записи (LWW по `updated_at`, tombstones `deleted_at`) — в `watchlist.py` (`export_items()`, `merge()`), оно коммутативно, поэтому потерянная гонкой запись возвращается при следующей синхронизации устройства, где она осталась. Триггеры: переход аккаунта в `signed_in` (старт и вход), изменение списка (debounce 3 с), кнопка «Синхронизировать», повтор раз в 60 с, пока есть неотправленные изменения и нет связи. Признак неотправленных изменений и время последней синхронизации — в `sync.json` рядом со списком. Frontend: методы `sync_get` / `sync_now`, события `sync_changed` и `watchlist_reloaded`; индикатор `SyncStatus.svelte` на экране «Мой список» и в блоке «Аккаунт Google».

## Technical Context

**Language/Version**: Python 3.10+ (backend), TypeScript 5.9 + Svelte 5 (frontend)

**Primary Dependencies**: `requests` (есть); новых зависимостей нет

**Storage**: облако — `appDataFolder/watchlist.json` (формат как локальный, без `lookups`); локально — `watchlist.json` (без изменений формата) и новый `sync.json` (`pending`, `last_synced_at`, `email`)

**Testing**: pytest — слияние (LWW, tombstones, неизвестные поля, равные времена), очистка tombstones > 90 дней, `Syncer` с подменённым Drive (первый вход, офлайн-очередь, гонка с изменённым файлом, битый облачный файл, 401 → `expired`, дубли файлов), методы backend; Vitest — `describeSync`; ручная проверка на двух устройствах

**Target Platform**: Windows 11 x64, macOS

**Project Type**: настольное приложение (Tauri + Python sidecar)

**Performance Goals**: отправка ≤ 10 с после последнего изменения (debounce 3 с + запрос); 500 записей ≈ 150 КБ — слияние < 50 мс, интерфейс не ждёт синхронизации

**Constraints**: без входа — ни одного запроса к Drive; синхронизация не занимает пул `io` надолго (свой поток); битый облачный файл ничего не перезаписывает; Rust не меняется

**Scale/Scope**: `src/mpv_launcher/drive_sync.py` (новый), `watchlist.py`, `backend.py`, `app/src/lib/api.ts`, `app/src/lib/logic.ts`, `app/src/components/SyncStatus.svelte` (новый), `app/src/components/AccountCard.svelte`, `app/src/screens/Watchlist.svelte`

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет. После дизайна без изменений.

## Project Structure

### Documentation (this feature)

```text
specs/013-drive-sync/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/sync-protocol.md
└── tasks.md             # создаёт /speckit-tasks
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── drive_sync.py         # новый: Drive-клиент, Syncer, SyncState, sync.json
├── watchlist.py          # export_items(), merge(), prune_tombstones(), on_change
└── backend.py            # sync_get / sync_now, события sync_changed / watchlist_reloaded, триггеры
tests/unit/
├── test_watchlist_merge.py  # новый
├── test_drive_sync.py       # новый
└── test_backend.py          # sync_*
app/src/
├── lib/api.ts            # SyncState, методы и события
├── lib/logic.ts          # describeSync()
├── components/SyncStatus.svelte   # новый: индикатор + «Синхронизировать»
├── components/AccountCard.svelte  # индикатор под аккаунтом
└── screens/Watchlist.svelte       # индикатор в шапке, перезагрузка по watchlist_reloaded
```

**Structure Decision**: Вся работа с Drive — в backend рядом с `google_auth.py` и списком; frontend только показывает состояние и шлёт команды, как на этапе 1.

## Этапы

1. **Слияние (основа)**: `Watchlist.export_items()`, `merge(remote) -> changed`, очистка tombstones, колбэк `on_change` после каждого `_commit`.
2. **Drive и Syncer (US1)**: поиск/скачивание/создание/обновление файла, цикл синхронизации с проверкой `modifiedTime` перед записью, триггеры старт/вход/изменение, событие `watchlist_reloaded`.
3. **Состояние и индикатор (US2)**: `SyncState`, `sync_changed`, `sync_get`, `sync_now`, `SyncStatus.svelte`, «Нужно войти заново».
4. **Офлайн и первый вход (US3)**: `sync.json` с `pending`, повтор раз в 60 с, смена аккаунта, выход без изменения данных.
5. **README и quickstart**: раздел о синхронизации.

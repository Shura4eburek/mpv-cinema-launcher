# Tasks: Синхронизация «Моего списка» через Google Drive

**Input**: Design documents from `specs/013-drive-sync/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/sync-protocol.md, quickstart.md

**Tests**: pytest для слияния, `Syncer` (Drive подменяется) и методов backend; Vitest для `describeSync`.

## Phase 1: Setup

- [X] T001 Добавить `sync_path()` (рядом с `watchlist.json` в каталоге данных, `sync.json`) в `src/mpv_launcher/settings.py`

## Phase 2: Foundational (слияние)

- [X] T002 `Watchlist.export_items() -> dict` в `src/mpv_launcher/watchlist.py`: глубокая копия всех `items` (включая tombstones), без `lookups`
- [X] T003 Функция `merge_items(local, remote, now) -> dict` в `src/mpv_launcher/watchlist.py` по таблице data-model.md: LWW по `updated_at` (строки ISO), при равенстве — большая по `json.dumps(sort_keys=True)`; запись без строки `updated_at` или не-dict отбрасывается; запись берётся целиком (неизвестные поля сохраняются); затем удалить tombstones с `deleted_at` старше 90 дней
- [X] T004 `Watchlist.merge(remote_items) -> bool` в `src/mpv_launcher/watchlist.py` через `_commit`: применяет `merge_items`, возвращает `True`, если локальные `items` изменились; файл не перезаписывается, если изменений нет
- [X] T005 `Watchlist(on_change=...)` в `src/mpv_launcher/watchlist.py`: колбэк вызывается после каждого успешного `_commit` пользовательского изменения (`set_status`, `remove`, `on_play_started`, `set_episode`, `apply_id`), но не после `merge`; вызывается вне лока; исключение колбэка не ломает изменение
- [X] T006 [P] Тесты T002–T005 в `tests/unit/test_watchlist_merge.py`: только local / только remote, LWW в обе стороны, равное время детерминированно (merge(a,b)==merge(b,a)), tombstone побеждает старую запись и проигрывает новой, неизвестные поля сохраняются, мусорные записи отбрасываются, очистка tombstones > 90 дней, идемпотентность, `merge` возвращает `False` без изменений, `on_change` вызывается на изменения и не вызывается на `merge`

## Phase 3: User Story 1 - Один список на всех устройствах (P1) 🎯 MVP

**Goal**: список уходит в облако и подтягивается при старте и входе.

**Independent Test**: сценарии 1–3 и 6 из quickstart.md.

- [X] T007 [US1] Drive-клиент в `src/mpv_launcher/drive_sync.py`: `Drive(token, http)` с методами `find()` (список `[{id, modifiedTime}]` по `createdTime`), `download(id) -> bytes`, `create(body) -> {id, modifiedTime}` (multipart, `parents: ["appDataFolder"]`), `update(id, body)`, `modified(id) -> str`, `delete(id)`; URL и параметры из research.md; таймаут 15 с; исключения `DriveOffline` (ConnectionError, Timeout, 429, 5xx), `DriveUnauthorized` (401), `DriveRejected(reason)` (403/прочие 4xx с `error.message`)
- [X] T008 [US1] Формат облачного файла в `src/mpv_launcher/drive_sync.py`: `encode(items, now)` → `{"version": 1, "items": …, "written_at": now}`; `decode(bytes)` → `items`; неверный JSON, не-dict, нет `items` или `version` > 1 → `BadRemote`
- [X] T009 [US1] `SyncStore` в `src/mpv_launcher/drive_sync.py`: `sync.json` `{pending, last_synced_at, email}`, атомарная запись; нет файла / битый → `{pending: true, last_synced_at: null, email: null}`
- [X] T010 [US1] Цикл синхронизации `Syncer._run_once()` в `src/mpv_launcher/drive_sync.py` по research.md «Гонка двух устройств»: `find` → скачать все найденные, `decode`, слить их между собой → `watchlist.merge()` (если `True` — колбэк `on_reloaded`) → запомнить счётчик локальных изменений → `modified()` самого старого файла; изменился с момента скачивания — повторить (до 3 раз, потом `DriveOffline`-подобный повтор позже) → `update` (или `create`, если файлов нет) из `watchlist.export_items()` → удалить лишние дубли → `pending = False` только если счётчик изменений не вырос → сохранить `last_synced_at`, `email`
- [X] T011 [US1] Поток `Syncer` в `src/mpv_launcher/drive_sync.py`: один daemon-поток `"drive-sync"`, `request()` ставит флаг и будит поток (запросы во время цикла схлопываются в один следующий); `start()` / `stop()`; `access_token` — функция из backend; при `DriveUnauthorized` один раз запросить новый токен и повторить
- [X] T012 [US1] Сброс access token в `src/mpv_launcher/google_auth.py`: `Account.drop_access_token()` (под локом `_access = None`), чтобы повтор после 401 получил новый токен; `Backend.drop_access_token()` в `src/mpv_launcher/backend.py`
- [X] T013 [US1] Подключение в `src/mpv_launcher/backend.py`: параметр `syncer_factory` (для тестов); `Watchlist(on_change=self._syncer.local_changed)`; в обработчике `account_changed` при `state == "signed_in"` → `syncer.enable(email)` + `request()`; `on_reloaded` → `self._emit("watchlist_reloaded", {})`; `close()` → `syncer.stop()`
- [X] T014 [US1] Debounce в `src/mpv_launcher/drive_sync.py`: `local_changed()` увеличивает счётчик изменений, сразу сохраняет `pending: true`, (пере)запускает `threading.Timer(3, request)`; без включённой синхронизации — только `pending`
- [X] T015 [P] [US1] Тесты в `tests/unit/test_drive_sync.py` с FakeDrive (хранит файлы и `modifiedTime`, умеет падать): создание файла при пустом облаке (US3/AC3), слияние с облаком (US1/AC2–5), гонка — `modifiedTime` изменился между скачиванием и записью → повтор и итог содержит обе стороны, дубли файлов сливаются и удаляются, `pending` остаётся при изменении во время цикла, `on_reloaded` только при изменении, 401 → новый токен → успех, debounce схлопывает серию изменений в одну запись
- [X] T016 [US1] Frontend: `watchlist_reloaded` в списке событий `app/src/lib/api.ts`; `app/src/screens/Watchlist.svelte` и `app/src/screens/Movie.svelte` перечитывают данные по этому событию

## Phase 4: User Story 2 - Видно, что происходит с синхронизацией (P2)

**Goal**: индикатор состояния, ручной запуск, «Нужно войти заново».

**Independent Test**: сценарии 4 и 5 из quickstart.md.

- [X] T017 [US2] `SyncState` в `src/mpv_launcher/drive_sync.py`: `snapshot()` → `{state, pending, last_synced_at, message}`; состояния и переходы из data-model.md; `on_state` колбэк при каждом изменении; сообщения из `contracts/sync-protocol.md`: `DriveOffline` / `ApiError("offline")` → `offline`, `ApiError("expired")` / второй 401 → `auth_required`, `BadRemote` и `DriveRejected` → `error` (ничего не пишется, FR-012), `ApiError("signed_out")` → `disabled`
- [X] T018 [US2] Методы `sync_get` (сразу) и `sync_now` (сразу; без входа — `ApiError("signed_out")`) и событие `sync_changed` в `src/mpv_launcher/backend.py`
- [X] T019 [P] [US2] Тесты в `tests/unit/test_drive_sync.py` и `tests/unit/test_backend.py`: переходы `syncing → idle/offline/auth_required/error`, битый облачный файл не перезаписан и локальный список не изменён, `sync_get`/`sync_now`, `sync_changed` эмитится
- [X] T020 [US2] Типы `SyncStateId`, `SyncState`, методы `syncGet`, `syncNow`, событие `sync_changed` и `syncFromEvent()` в `app/src/lib/api.ts`
- [X] T021 [US2] `describeSync(state, now)` в `app/src/lib/logic.ts` по таблице `contracts/sync-protocol.md` (время — «только что», «N мин назад», иначе ЧЧ:ММ) и тесты в `app/src/lib/logic.test.ts`
- [X] T022 [US2] `app/src/components/SyncStatus.svelte`: иконка + текст `describeSync`, кнопка «Синхронизировать» в `idle`/`offline`/`error`, в `auth_required` — ссылка в Настройки; состояние из `syncGet()` и событий `sync_changed` (с отбрасыванием устаревших ответов, как в `AccountCard.svelte`)
- [X] T023 [US2] Встроить `SyncStatus` в шапку `app/src/screens/Watchlist.svelte` и под аккаунтом в `app/src/components/AccountCard.svelte` (только в `signed_in`/`offline`/`expired`)

## Phase 5: User Story 3 - Работа без сети и первый вход (P3)

**Goal**: офлайн-изменения уходят сами, первый вход объединяет, выход ничего не удаляет.

**Independent Test**: сценарии 4, 6, 7, 8 из quickstart.md.

- [X] T024 [US3] Повтор в `src/mpv_launcher/drive_sync.py`: в `offline` при `pending` — `threading.Timer(60, request)`; отменяется при выходе, успешной синхронизации и `stop()`
- [X] T025 [US3] Старт с `pending: true` из `sync.json`: после `signed_in` при запуске изменения отправляются без действий пользователя (через обычный `request()` T013)
- [X] T026 [US3] Выход в `src/mpv_launcher/backend.py` / `drive_sync.py`: `account_changed` с `signed_out` (и `expired`) → `syncer.disable()`: таймеры отменены, состояние `disabled` (для `expired` — `auth_required`), локальный список и облако не трогаются; `email` в `sync.json` сброшен
- [X] T027 [US3] Без входа ни одного запроса к Drive: `request()` и таймеры ничего не делают, пока синхронизация не включена (FR-009)
- [X] T028 [P] [US3] Тесты в `tests/unit/test_drive_sync.py`: офлайн → изменения копятся → повтор → отправлены; `pending` переживает перезапуск; выход не меняет список и облако, после выхода FakeDrive не получает запросов; вход другим аккаунтом сливает локальный список с его облаком

## Phase 6: Polish

- [X] T029 [P] Раздел «Синхронизация списка» в `README.md`: что синхронизируется, где лежит, индикатор, офлайн
- [X] T030 Прогнать pytest, `npx vitest run`, `npm run check`, `npm run build`
- [X] T031 Визуальная проверка `SyncStatus` во всех состояниях через dev-сервер с моком `__TAURI_INTERNALS__`
- [ ] T032 Ручная проверка quickstart.md на двух устройствах с настоящим клиентом (владелец)

## Dependencies

- Phase 1 → Phase 2 → US1 → US2 → US3 → Polish
- US2 опирается на `Syncer` из US1; US3 — на состояния US2

## Parallel Opportunities

- T006 параллельно с T007–T009 (разные файлы)
- T015, T019, T028 — тесты в отдельных файлах
- T020–T022 (frontend) параллельно с T017–T018 (backend)

## Implementation Strategy

- MVP: Phase 1–3 (синхронизация при старте, входе и после изменений, без индикатора)
- Затем US2 (индикатор), US3 (офлайн-повтор и выход)

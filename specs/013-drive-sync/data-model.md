# Data Model: Синхронизация через Google Drive

## Облачный файл `appDataFolder/watchlist.json`

```json
{ "version": 1, "items": { "<key>": { "key": "…", "status": "planned", "episodes": {}, "deleted_at": null, "updated_at": "2026-11-16T10:00:00.000000Z", "…": "…" } }, "written_at": "2026-11-16T10:00:03.000000Z" }
```

- `items` — те же записи, что в локальном `watchlist.json` (включая tombstones), без `lookups`.
- `version` > 1 или неверная структура → ошибка синхронизации, файл не перезаписывается.
- Запись без строки `updated_at` при слиянии отбрасывается.

## Локальный `sync.json` (рядом с `watchlist.json`)

```json
{ "pending": true, "last_synced_at": "2026-11-16T10:00:03.000000Z", "email": "user@example.com" }
```

- `pending` — есть изменения, не отправленные в облако. Ставится при каждом изменении списка, снимается после записи в облако, если список не менялся во время цикла.
- Нет файла или битый → `{pending: true, last_synced_at: null, email: null}` (безопасно: лишняя синхронизация).
- Пишется атомарно.

## Слияние записи

| local | remote | результат |
|-------|--------|-----------|
| есть | нет | local |
| нет | есть | remote |
| `updated_at` больше | | local |
| | `updated_at` больше | remote |
| равны | равны | большая по `json.dumps(sort_keys=True)` |

После слияния удаляются tombstones с `deleted_at` старше 90 дней.

## Состояние синхронизации (`SyncState`, в памяти)

| Поле | Тип | Описание |
|------|-----|----------|
| `state` | `"disabled" \| "idle" \| "syncing" \| "offline" \| "auth_required" \| "error"` | |
| `pending` | `bool` | есть неотправленные изменения |
| `last_synced_at` | `string \| null` | ISO UTC последней успешной синхронизации |
| `message` | `string \| null` | текст ошибки на русском |

Переходы:

- без входа / `unconfigured` → `disabled`
- `signed_in` → `syncing` → `idle` | `offline` | `auth_required` | `error`
- `idle` | `offline` | `error` → `syncing` (изменение списка после debounce, `sync_now`, повтор 60 с из `offline`)
- `auth_required` → `syncing` после нового входа
- `signed_out` → `disabled` из любого состояния

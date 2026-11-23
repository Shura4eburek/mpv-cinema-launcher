# Contract: методы протокола backend для списка

Формат запросов и ответов прежний (`{id, method, params}` → `{id, result}` / `{id, error}`). Запись в ответах — объект из [data-model.md](../data-model.md) без `fallback_key`.

## Описание тайтла (`title`)

Передаётся в методы, которые могут создать запись:

```json
{ "title": "Битва моторов", "orig_title": null, "year": "2026", "kind": "film",
  "url": "https://uakinogo.io/filmy/109870-bitva-motorov.html", "poster_url": "https://…", "source": "kinogo" }
```

`title` и `url` обязательны, `kind` ∈ `film|series`, `source` ∈ `kinogo|hdrezka|lampac` или null; иначе `invalid_params`.

## Методы

| Метод | Очередь | params | result |
|-------|---------|--------|--------|
| `watchlist_list` | сразу | — | `{ items: Entry[], warning?: "watchlist_reset" }`; без удалённых, по `updated_at` убыв. |
| `watchlist_get` | сразу | `{ title }` | `{ entry: Entry \| null }` |
| `watchlist_set_status` | сразу | `{ title, status: "watching"\|"planned"\|"completed" }` | `{ entry }` |
| `watchlist_remove` | сразу | `{ title }` | `{ entry: null }` |
| `watchlist_set_episode` | сразу | `{ title, season, episode, watched: bool }` | `{ entry }`; только для `series` |
| `watchlist_resolve` | io | `{ title }` | `{ entry: Entry \| null, key }`; ищет id IMDb, переносит запись; сбой сети → `{ entry, key }` с прежним ключом, без ошибки |

## Параметр `watch` в `play`

```json
{ "watch": { "title": { "…": "как выше" }, "season": "1", "episode": "6", "final": false } }
```

- Без `watch` поведение `play` прежнее. Неверный `watch` не мешает запуску: он пропускается, просмотр идёт без списка.
- Когда видео пошло (первая позиция > 0 из канала управления): статус по таблице переходов, событие `watchlist_changed { entry }`. Сбой загрузки статус не меняет.
- При досмотре — позиция ≥ 95% длительности (по концу файла, при закрытии mpv или встроенного плеера); конец файла без известной длительности тоже засчитывается, а обрыв потока раньше 95% — нет: отметка серии (если есть), событие `watchlist_changed`, затем `watch_completed { key, title, final }`.
- `final: true` для фильма и последней серии последнего сезона, если тайтл ещё не «Просмотрено».

## События

| Событие | data | Кто слушает |
|---------|------|-------------|
| `watchlist_changed` | `{ entry }`; после `play` с `watch`, `watchlist_set_status`, `watchlist_remove`, `watchlist_set_episode` | `Movie.svelte` (обновить статус и отметки), `Watchlist.svelte` |
| `watch_completed` | `{ key, title, final }` | `App.svelte`: при `final` — предложение «Отметить как просмотренное?» → `watchlist_set_status completed` |

## Ошибки

`invalid_params` — неверный `title`, статус, сезон/серия; `internal` — сбой записи файла (прежний файл не меняется).

## Платформы

Канал управления mpv — именованный канал на Windows и Unix-сокет `/tmp/mpv-cinema-<id>.sock` на macOS (удаляется после завершения mpv); поведение `watch` одинаково.

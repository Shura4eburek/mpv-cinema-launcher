# Дополнения к протоколу backend

Основной протокол: `specs/003-app-player-ui/contracts/backend-protocol.md`.

## `movie`

В ответ добавляются `actors: string[]` и `related: MovieCard[]`.

## `trailer`

Запрос: `{ "title": string, "year": string | null }`.

Ответ: `{ "videos": [{ "id": string, "title": string }] }`, до 5 элементов.

Ошибки: `network` — YouTube недоступен; `not_found` — роликов нет.

## `open_trailer_search`

Запрос: `{ "title": string, "year": string | null }`.

Ответ: `{ "ok": true }`. Адрес поиска YouTube строит backend; произвольный адрес передать нельзя.

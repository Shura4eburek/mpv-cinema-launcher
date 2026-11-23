# Contract: протокол между Tauri и Python

Одна строка — одно сообщение JSON в UTF-8. Python читает stdin и пишет в свой настоящий stdout.
Диагностика идёт только в stderr, который Rust сохраняет в файл журнала.

## Сообщения

```text
запрос:  {"id": 7, "method": "search", "params": {"query": "Тенет"}}
успех:   {"id": 7, "result": {...}}
ошибка:  {"id": 7, "error": {"code": "network", "message": "..."}}
событие: {"event": "playback_finished", "data": {...}}
```

`id` назначает Rust. Ответы могут приходить не в порядке запросов.

## Методы

| Метод | Параметры | Результат | Где выполняется |
|-------|-----------|-----------|-----------------|
| `status` | — | `mpv_found`, `upscale_ready` | сразу |
| `search` | `query` | список карточек | очередь Selenium |
| `movie` | `url` | данные страницы, озвучки, потоки | очередь Selenium |
| `translator_streams` | `url`, `translator_id` | потоки фильма | очередь Selenium |
| `episode` | `url`, `source`, `translator_id`, `season`, `episode` | потоки серии, озвучки, сезоны и серии ([контракт](../../008-series-support/contracts/backend-protocol.md)) | очередь Selenium |
| `poster` | `url` | путь к файлу в кэше | пул потоков |
| `play` | `title`, `urls`, настройки | `started` | поток запуска |
| `play_clipboard` | настройки | `started` | поток запуска |
| `player_stop` | — | `ok`, завершает плеер на странице ([контракт](../../009-embedded-player/contracts/player-surface.md)) | сразу |
| `copy_text` | `text` | `ok` | сразу |
| `get_settings` | — | `UserSettings` | сразу |
| `set_settings` | изменённые поля | `UserSettings` | сразу |

## События

| Событие | Данные | Смысл |
|---------|--------|-------|
| `playback_finished` | `code` | mpv закрыт |
| `playback_failed` | `code` ошибки | ни одно зеркало не загрузилось |
| `upscale_ready` | `ready` | загрузка шейдеров завершена |
| `playback_fallback` | `code` | запущен запасной адрес, качество может быть ниже |

Rust дополнительно отправляет в интерфейс `backend_down`, если процесс завершился.

## Коды ошибок

`network`, `not_found`, `no_streams`, `no_mpv`, `no_url`, `all_mirrors_failed`, `player_failed`,
`invalid_params`, `internal`. Rust добавляет `backend_down`, если процесс недоступен.
Текст для пользователя выбирает интерфейс по коду ([ui-and-player.md](./ui-and-player.md)).

## Жизненный цикл

- Окно открывается сразу, не дожидаясь backend. До готовности поиск показывает состояние загрузки.
- Процесс завершился неожиданно: Rust завершает ошибкой все открытые запросы и один раз
  перезапускает backend. Если снова неудачно — интерфейс показывает ошибку и «Повторить».
- Закрытие окна: Rust закрывает stdin, backend сразу завершает драйвер Chrome и выходит. Через
  5 секунд процесс снимается принудительно. Открытый mpv продолжает играть.
- Ошибка разбора строки или неизвестный метод не завершают backend.

## Проверка входных данных

- `url` и `poster.url`: только `http` и `https`.
- `play.urls`: непустой список, каждый адрес проходит `url.validate`.
- Настройки: допустимые значения из [data-model.md](../data-model.md).

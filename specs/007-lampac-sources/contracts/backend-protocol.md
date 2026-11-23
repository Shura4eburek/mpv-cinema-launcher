# Дополнения к протоколу backend

## Методы

- `lampac_state`: `{}` → `LampacState`.
- `lampac_sources`: `{ progress_id, title, original_title, year, serial }` → `{ found }`; источники приходят событиями, отмена через `cancel`.
- `lampac_variants`: `{ url }` → `LampacVariants`. Адрес ДОЛЖЕН указывать на локальный сервер Lampac.
- `play`: дополнительно `source: "lampac"`; обновление ссылок KinoGo к нему не применяется.

Включение и выключение идёт через `set_settings` с `lampac_enabled`.

## События

- `lampac_state`: `{ lampac: LampacState }`.
- `lampac_source`: `{ id, source: LampacSource }`.

## Ошибки

- `lampac_off`: сервер не запущен.
- `not_found`: у источника нет вариантов.
- `network`: сервер не ответил.

# Contract: изменения протокола backend

Дополняет контракты 003 и 004.

| Метод | Изменение |
|-------|-----------|
| `movie`, `translator_streams`, `play` | необязательное поле `progress_id` |
| `cancel` | новый: `{id}` → `{ok: true}`, выполняется сразу |
| `device` | новый: `{preset, gpu}` |
| `get_settings`, `set_settings` | поле `preset` вместо `upscale_quality` и `profile` |

## Событие

`{"event": "load_progress", "data": {"id": "...", "step": "player", "state": "running"}}`

`state`: `running`, `done`, `error`.

## Код ошибки

`cancelled`: загрузка отменена; интерфейс не показывает это как сбой.

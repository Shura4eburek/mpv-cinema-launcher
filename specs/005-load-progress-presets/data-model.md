# Data Model: загрузка и пресеты

## UserSettings (изменения)

| Поле | Значения | По умолчанию | Правило |
|------|----------|--------------|---------|
| `preset` | `auto` \| `high` \| `mid` \| `low` | `auto` | неверное значение заменяется на `auto` |

Поля `upscale_quality` и `profile` больше не хранятся. Перенос, если `preset` ещё нет: `upscale_quality=basic` → `low`; иначе `desktop-4070ti` → `high`, `air-m1` → `mid`, `generic` → `low`; иначе `auto`.

## Шаг загрузки (в памяти интерфейса)

`{id, label, state}`, где `state`: `pending` → `running` → `done` или `error`.

## Device

`{preset: high|mid|low, gpu: строка|null}`. Определяется один раз за запуск.

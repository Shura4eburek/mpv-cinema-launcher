# Data Model — mpv HLS Launcher (Phase 1)

Сущности здесь — это внутренние структуры данных лаунчера (не БД). Состояние не
персистится между запусками.

## Options (разобранные аргументы CLI)

Результат разбора командной строки.

| Поле | Тип | Правила |
|------|-----|---------|
| `url` | `str \| None` | ссылка из аргумента; `None`, если не передана (тогда берётся из буфера) |
| `profile` | `str` | один из `auto` (default), `desktop-4070ti`, `air-m1`, `generic` |
| `content` | `str` | `film` (default) или `anime`; задаётся `--film`/`--anime` (взаимоисключающие) |
| `referer` | `str \| None` | значение для заголовка Referer |
| `user_agent` | `str \| None` | значение для заголовка User-Agent |
| `headers` | `list[str]` | произвольные `"Name: Value"` из повторяемого `--header` |
| `dry_run` | `bool` | если `True` — вывести собранную команду mpv и не запускать |

**Правила валидации**: `--film` и `--anime` вместе → ошибка разбора (код ≠ 0).

## Stream (поток к воспроизведению)

| Поле | Тип | Правила |
|------|-----|---------|
| `url` | `str` | непустой, парсится как `http`/`https` с непустым host |
| `looks_like_hls` | `bool` | эвристика: в URL встречается `.m3u8` или `hls` |

**Источник**: `Options.url`, иначе буфер обмена. Пустой/непригодный → ошибка (FR-003).

## MachineProfile (класс машины → конфиг апскейла)

| Поле | Тип | Правила |
|------|-----|---------|
| `name` | `str` | `desktop-4070ti` \| `air-m1` \| `generic` |
| `conf_file` | `str \| None` | путь к `mpv-profiles/<name>.conf`; `None` для `generic` (встроенный апскейл) |

**Определение**: `machine.detect()` → имя по эвристике R3; `Options.profile != auto`
переопределяет. Отсутствие `conf_file` на диске → деградация к встроенному апскейлу (R6).

## ContentPreset (пресет контента → имя mpv-профиля)

| Поле | Тип | Правила |
|------|-----|---------|
| `name` | `str` | `film` \| `anime` |
| `mpv_profile` | `str` | имя секции профиля внутри `.conf` (`film` / `anime`) |

## LaunchPlan (итог сборки → вход для runner)

Чистый результат `presets.build_plan(options, machine_profile)` — то, что проверяется
юнит-тестами без запуска mpv.

| Поле | Тип | Описание |
|------|-----|----------|
| `mpv_args` | `list[str]` | полный argv для mpv: `--include=`, `--profile=`, `--http-header-fields=` (если есть), затем `url` |
| `warnings` | `list[str]` | например, «конфиг профиля не найден — базовый апскейл» |

**Инварианты**:
- `url` — всегда последний элемент `mpv_args`.
- Если заголовков нет — опции `--http-header-fields` в `mpv_args` нет вовсе.
- `warnings` не влияют на код выхода (это не ошибки).

## Поток данных (happy path)

```text
argv ─▶ cli.parse() ─▶ Options
                         │ (url пуст?) ─▶ clipboard.read() ─▶ url
                         ▼
                 url.validate() ─▶ Stream
                         ▼
   machine.resolve(Options.profile) ─▶ MachineProfile
                         ▼
   presets.build_plan(Options, MachineProfile) ─▶ LaunchPlan
                         ▼
          runner.run(LaunchPlan)  ─▶ subprocess mpv  (или печать при dry_run)
```

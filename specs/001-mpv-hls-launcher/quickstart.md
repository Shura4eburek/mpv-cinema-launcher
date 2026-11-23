# Quickstart — mpv HLS Launcher

Руководство по запуску и проверке фичи end-to-end. Детали интерфейса — в
[contracts/cli.md](./contracts/cli.md), структуры — в [data-model.md](./data-model.md).

## Prerequisites

- Python 3.10+
- mpv в PATH (`mpv --version`)
  - macOS: `brew install mpv`
  - Windows: `winget install mpv` (или сборка mpv.net / shinchiro)
- (для максимального качества) файлы шейдеров FSRCNNX и Anime4K в каталоге шейдеров mpv —
  см. `mpv-profiles/README.md`. Без них лаунчер деградирует к встроенному апскейлу.

## Установка (dev)

```bash
cd mpv-cinema-launcher
python -m pip install -e ".[dev]"     # ставит пакет + pytest; даёт команду `mpvplay`
# либо запуск без установки:
python -m mpv_launcher --help
```

Разложить профили апскейла (однократно на каждой машине) — по инструкции
`mpv-profiles/README.md`.

## Прогон тестов

```bash
pytest -q
```

Ожидаемо: все юнит-тесты зелёные; mpv в тестах не запускается (мокается).

## Валидация по user stories

### US1 — просмотр одной командой (P1, MVP)

```bash
# 1. ссылка аргументом
mpvplay "https://<cdn>/.../hls-v1-a4.m3u8"
#   → открывается mpv и играет поток

# 2. ссылка из буфера: скопировать .m3u8, затем
mpvplay
#   → лаунчер берёт ссылку из буфера и запускает воспроизведение

# 3. нет ссылки нигде
mpvplay            # с пустым буфером
#   → понятное сообщение на stderr, код выхода 3
```

### US2 — профиль под железо (P2)

```bash
mpvplay "https://..." --dry-run
#   → на M1 Air в команде фигурирует air-m1.conf;
#     на Windows+NVIDIA — desktop-4070ti.conf

mpvplay "https://..." --profile air-m1 --dry-run
#   → форсированный профиль перекрывает автоопределение
```

### US3 — пресеты контента (P3)

```bash
mpvplay "https://..." --film  --dry-run    # → --profile=film
mpvplay "https://..." --anime --dry-run    # → --profile=anime
mpvplay "https://..." --film --anime       # → ошибка разбора, код 2
```

### Заголовки (FR-009)

```bash
mpvplay "https://..." --referer "https://site/" --user-agent "Mozilla/5.0" --dry-run
#   → в команде есть --http-header-fields="Referer: https://site/,User-Agent: Mozilla/5.0"
```

### Отсутствие mpv (FR-011)

```bash
# временно убрать mpv из PATH и запустить
mpvplay "https://..."
#   → подсказка по установке на stderr, код 4, mpv не вызывается
```

## Критерии приёмки (связь со спекой)

- SC-001 — US1 выполняется одной командой/одним запуском.
- SC-002 — US2: разные профили на разных машинах без правок конфигов.
- SC-004 — все ошибки (нет ссылки/mpv/шейдеров/поток недоступен) дают понятное
  сообщение за секунды, а не зависание.
- SC-005 — US3: `--film` и `--anime` дают разный собранный апскейл (видно в `--dry-run`).

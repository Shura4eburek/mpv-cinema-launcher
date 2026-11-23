# mpv-профили апскейла

Эти `.conf` — визуальные настройки апскейла, которые лаунчер подключает к mpv
(`--include=<файл> --profile=film|anime`). Логика лаунчера их не редактирует —
качество настраивается здесь.

| Файл | Машина |
|------|--------|
| `desktop-4070ti.conf` | Windows, RTX 4070 Ti, 1440p — тяжёлые шейдеры |
| `air-m1.conf` | MacBook Air M1 — облегчённый профиль |

`generic` (неизвестная машина) профиля не имеет — лаунчер использует встроенный
`--profile=gpu-hq` без внешних шейдеров.

## Где лаунчер ищет профили

По умолчанию — этот каталог (`mpv-profiles/` в корне репозитория). Переопределить
можно переменной окружения `MPV_LAUNCHER_PROFILES_DIR`.

## Шейдеры (нужно поставить вручную)

Шейдеры в репозиторий не входят. Положи их в каталог шейдеров mpv, на который
указывает `~~/shaders/` в конфигах:

- macOS: `~/.config/mpv/shaders/`
- Windows: `%APPDATA%\mpv\shaders\`

Откуда взять:

- **FSRCNNX** (`FSRCNNX_x2_16-0-4-1.glsl`, `FSRCNNX_x2_8-0-4-1.glsl`) —
  https://github.com/igv/FSRCNN-TensorFlow/releases
- **KrigBilateral** (`KrigBilateral.glsl`) — https://gist.github.com/igv
- **Anime4K** (`Anime4K_*.glsl`) — https://github.com/bloc97/Anime4K/releases

> Если нужного шейдера нет — mpv сообщит об этом при запуске. Если нет самого
> `.conf`-профиля, лаунчер предупредит и переключится на встроенный апскейл.

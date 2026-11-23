# Data Model

**Настройка**: `lampac_enabled: bool`, по умолчанию `false`.

**LampacState**: `state`: `off | starting | running | error`; `detail: str`.

**LampacSource**: `id: str`, `name: str`, `url: str`. Показывается только после ответа с `type: movie`.

**LampacVariants**: `url`, `kind: movie | episode`, `voices: [{ name, url, active }]`, `seasons: [{ name, url }]`, `items: [{ voice, qualities: [{ label, url }], subtitles: [{ label, url }], episode: { season, number, name } | null }]`.

Отбрасывается: адрес с `abuse`, ответ не JSON, `similar` без точного совпадения названия и года.

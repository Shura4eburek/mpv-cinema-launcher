# Data Model: Вход через Google

## `account.json` (каталог настроек)

```json
{ "name": "Имя Фамилия", "email": "user@example.com", "picture": "https://…", "signed_in_at": 1763300000.0 }
```

- Только для показа; секретов нет. Нет файла или он битый — считается «не вошёл» (битый файл удаляется).
- Пишется атомарно (`mkstemp` + `os.replace`), как `watchlist.json`.

## Системное хранилище

| Сервис | Имя | Значение |
|--------|-----|----------|
| `mpv-cinema-launcher` | `google-refresh-token` | refresh token |

## Состояние в памяти (`AccountState`)

| Поле | Тип | Описание |
|------|-----|----------|
| `state` | `"unconfigured" \| "signed_out" \| "pending" \| "restoring" \| "signed_in" \| "offline" \| "expired"` | |
| `account` | `{name, email, avatar} \| null` | `avatar` — локальный путь к файлу или `null` (инициалы) |
| `storage_warning` | `bool` | хранилище недоступно, вход не сохранится |
| `message` | `string \| null` | последнее сообщение для пользователя («Вход отменён», «Нет связи с Google», …) |

Переходы:

- `signed_out` → `pending` (`account_sign_in`) → `signed_in` | `signed_out` + `message`
- старт с токеном: `restoring` → `signed_in` | `offline` | `expired`
- `offline` → `signed_in` при следующем успешном обновлении токена
- `signed_in` | `offline` | `expired` → `signed_out` (`account_sign_out`)
- без client_id всегда `unconfigured`

## Попытка входа (в памяти)

`verifier`, `state`, `redirect_uri`, `server`, `cancel: threading.Event`, `deadline` (сейчас + 300 с). Одна за раз.

## Access token (в памяти)

`token`, `expires_at`; обновляется по refresh token за 60 с до истечения. Наружу только через внутренний `Backend.access_token()` (для этапа 3).

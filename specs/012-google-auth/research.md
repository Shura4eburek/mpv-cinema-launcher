# Research: Вход через Google

## Тип клиента и секрет

- **Decision**: клиент Google «Desktop app». `client_id` и `client_secret` берутся из `MPV_CINEMA_GOOGLE_CLIENT_ID` / `MPV_CINEMA_GOOGLE_CLIENT_SECRET`, иначе из `google_client.json` рядом с исполняемым backend (PyInstaller кладёт его из `packaging/google_client.json`, файл в `.gitignore`). Нет ни того, ни другого — вход недоступен (`state: "unconfigured"`).
- **Rationale**: Google для desktop-клиентов требует `client_secret` при обмене кода даже с PKCE и прямо называет его несекретным. Хранить его вне репозитория — требование ишью.
- **Alternatives**: собственный сервер-посредник (лишняя инфраструктура); device flow (не поддерживает `drive.appdata`).

## Приём ответа

- **Decision**: `http.server` на `127.0.0.1`, порт 0 (свободный), `redirect_uri=http://127.0.0.1:<port>/`. Сервер обрабатывает один запрос с верным `state`, отвечает HTML «Вход выполнен» / «Вход отменён» и закрывается. Чужой `state` — ответ «Устаревшая попытка входа», ожидание продолжается.
- **Rationale**: рекомендованный Google loopback-способ; кастомные схемы для desktop-клиентов устарели.
- **Alternatives**: Tauri deep link (нужны правки Rust и регистрация схемы).

## PKCE и state

- **Decision**: `code_verifier = secrets.token_urlsafe(64)`, `code_challenge = base64url(sha256(verifier))` без `=`, метод S256; `state = secrets.token_urlsafe(24)`, сравнение `hmac.compare_digest`.

## Параметры запроса

- **Decision**: `scope="openid email profile https://www.googleapis.com/auth/drive.appdata"`, `access_type=offline`, `prompt=consent` (иначе refresh token не выдаётся повторно), `response_type=code`.

## Профиль

- **Decision**: `GET https://openidconnect.googleapis.com/v1/userinfo` с access token → `name`, `email`, `picture`. Аватар скачивается в `cache_dir()/avatar.jpg`, frontend показывает через `convertFileSrc`.
- **Rationale**: CSP `img-src` не пускает `googleusercontent.com`; так же уже сделаны постеры. Разбор id_token не нужен.

## Хранилище

- **Decision**: `keyring.set_password("mpv-cinema-launcher", "google-refresh-token", token)`. Ошибка `keyring.errors.KeyringError` или отсутствие backend'а — токен держится в памяти, состояние `storage_warning: true` (FR-012). В PyInstaller — `collect_submodules("keyring.backends")` в `hiddenimports`.
- **Alternatives**: шифрованный файл (свой ключ где-то хранить всё равно надо).

## Восстановление и ошибки

- **Decision**: при первом `account_get` backend показывает профиль из `account.json` (`state: "restoring"`) и в фоне обновляет access token. `invalid_grant` → удалить токен и профиль, `state: "expired"`. Сетевая ошибка → `state: "offline"`, профиль остаётся. Успех → `signed_in`, профиль обновлён.
- **Ошибки входа**: `error=access_denied` → «Вход отменён»; таймаут 300 с → «Время входа истекло»; `requests.ConnectionError`/`Timeout` → «Нет связи с Google»; отмена из приложения → «Вход отменён» без сообщения об ошибке.

## Выход

- **Decision**: сначала удалить токен из `keyring` и `account.json` и аватар, затем `POST https://oauth2.googleapis.com/revoke` с refresh token (таймаут 10 с); неудача → `revoke_failed: true` в событии.

## Поток ожидания

- **Decision**: `account_sign_in` запускает отдельный daemon-поток и сразу отвечает `{"state": "pending"}`; результат — событием `account_changed`. Повторный вызов при живой попытке возвращает `pending` без новой попытки (FR-011).
- **Rationale**: ожидание до 5 минут заняло бы один из четырёх потоков `io`.

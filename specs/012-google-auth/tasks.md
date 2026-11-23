# Tasks: Вход через Google

**Input**: Design documents from `specs/012-google-auth/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/account-protocol.md, quickstart.md

**Tests**: pytest для модуля и методов backend (HTTP Google и keyring подменяются), Vitest для состояний блока.

## Phase 1: Setup

- [X] T001 Добавить `keyring` в `dependencies` в `pyproject.toml` и установить локально (`pip install keyring`)
- [X] T002 [P] Добавить `packaging/google_client.json` в `.gitignore`
- [X] T003 [P] Добавить `account_path()` (каталог настроек, `account.json`) и `avatar_path()` (`cache_dir()/avatar.jpg`) в `src/mpv_launcher/settings.py`

## Phase 2: Foundational

- [X] T004 Создать `src/mpv_launcher/google_auth.py`: константы эндпоинтов (`https://accounts.google.com/o/oauth2/v2/auth`, `https://oauth2.googleapis.com/token`, `https://oauth2.googleapis.com/revoke`, `https://openidconnect.googleapis.com/v1/userinfo`), `SCOPES = "openid email profile https://www.googleapis.com/auth/drive.appdata"`, исключения `Unconfigured`, `Offline`, `Denied`, `Expired`
- [X] T005 `load_client()` в `src/mpv_launcher/google_auth.py`: `MPV_CINEMA_GOOGLE_CLIENT_ID`/`_SECRET`, иначе `google_client.json` рядом с исполняемым файлом (`sys._MEIPASS` при PyInstaller, иначе `packaging/`); нет id → `None`
- [X] T006 `TokenStore` в `src/mpv_launcher/google_auth.py`: `keyring` сервис `mpv-cinema-launcher`, имя `google-refresh-token`; `get/set/delete`; `KeyringError` или отсутствие backend'а → держать токен в памяти и `available = False`
- [X] T007 `ProfileStore` в `src/mpv_launcher/google_auth.py`: `account.json` `{name, email, picture, signed_in_at}`, атомарная запись (`mkstemp` + `os.replace`), битый файл удаляется и считается отсутствием
- [X] T008 [P] Тесты T005–T007 в `tests/unit/test_google_auth.py` (подменённый keyring с ошибкой, битый `account.json`, переменные окружения)

## Phase 3: User Story 1 - Войти через Google (P1) 🎯 MVP

**Goal**: вход через браузер, профиль в Настройках.

**Independent Test**: сценарии 1–4 и 9 из quickstart.md.

- [X] T009 [US1] PKCE и `state` в `src/mpv_launcher/google_auth.py`: `new_verifier()` (`secrets.token_urlsafe(64)`), `challenge(verifier)` (base64url SHA-256 без `=`), `auth_url(client_id, redirect_uri, challenge, state)` с `access_type=offline`, `prompt=consent`, `code_challenge_method=S256`
- [X] T010 [US1] Loopback-сервер в `src/mpv_launcher/google_auth.py`: `http.server` на `127.0.0.1:0`; `wait_for_code(state, cancel, deadline)` — верный `state` + `code` → код; `error=access_denied` → `Denied`; неверный `state` → 400 и ждать дальше; другой путь → 404; страницы ответа по `contracts/account-protocol.md`; сравнение `hmac.compare_digest`; таймаут 300 с → `TimeoutError`; отмена по `threading.Event`
- [X] T011 [US1] `exchange_code(client, code, verifier, redirect_uri)` и `fetch_profile(access_token)` в `src/mpv_launcher/google_auth.py` через `requests` (таймаут 10 с); `ConnectionError`/`Timeout` → `Offline`
- [X] T012 [US1] `download_avatar(url, path)` в `src/mpv_launcher/google_auth.py`; ошибка — без аватара (инициалы)
- [X] T013 [US1] Класс `Account` в `src/mpv_launcher/google_auth.py`: состояние по data-model.md (`unconfigured/signed_out/pending/restoring/signed_in/offline/expired`, `account`, `storage_warning`, `message`), `snapshot()`, колбэк `on_change`; `sign_in()` в daemon-потоке (одна попытка, повторный вызов — `pending`), `cancel()`; сообщения «Вход отменён», «Время входа истекло», «Нет связи с Google»; access token в памяти `{token, expires_at}`
- [X] T014 [US1] Методы `account_get`, `account_sign_in`, `account_cancel` в `src/mpv_launcher/backend.py` (сразу), событие `account_changed`; `unconfigured` → `ApiError("unconfigured", "Вход через Google не настроен в этой сборке")`
- [X] T015 [P] [US1] Тесты в `tests/unit/test_google_auth.py`: challenge по известному вектору RFC 7636, параметры `auth_url`, loopback (настоящий запрос на сервер: верный/неверный `state`, `access_denied`, 404, отмена, таймаут с малым deadline), обмен кода и профиль с подменённым `requests`, повторный `sign_in` не создаёт вторую попытку
- [X] T016 [P] [US1] Тесты `account_*` в `tests/unit/test_backend.py` (подменённый `Account`)
- [X] T017 [US1] Типы `AccountState`, `AccountInfo`, методы `accountGet/accountSignIn/accountCancel/accountSignOut`, событие `account_changed` в `app/src/lib/api.ts`
- [X] T018 [US1] `app/src/components/AccountCard.svelte`: состояния «Войти через Google» / ожидание с «Отмена» / аватар (`convertFileSrc`) или инициалы, имя, email, «Выйти»; `message` и `storage_warning`; недоступная кнопка с пояснением при `unconfigured`
- [X] T019 [US1] Блок «Аккаунт Google» в `app/src/screens/Settings.svelte` с `AccountCard`, подписка на `account_changed`
- [X] T020 [P] [US1] `initials(name, email)` в `app/src/lib/logic.ts` и тест в `app/src/lib/logic.test.ts`

## Phase 4: User Story 2 - Вход сохраняется между запусками (P2)

**Goal**: восстановление без браузера, `expired`/`offline`.

**Independent Test**: сценарии 5–7 из quickstart.md.

- [X] T021 [US2] `refresh(client, refresh_token)` в `src/mpv_launcher/google_auth.py`: `invalid_grant` → `Expired`, сеть → `Offline`
- [X] T022 [US2] `Account.restore()`: профиль из `account.json` → `restoring`, фоновое обновление → `signed_in` (профиль и аватар обновлены) / `offline` (профиль остаётся) / `expired` (токен и профиль удалены, «Нужно войти заново»); первый `account_get` запускает его один раз
- [X] T023 [US2] `Account.access_token()` и `Backend.access_token()` по `contracts/account-protocol.md`: обновление за 60 с до истечения; `offline` → `signed_in` при успехе
- [X] T024 [P] [US2] Тесты T021–T023 в `tests/unit/test_google_auth.py`; тест, что `account.json` не содержит токенов (SC-003)
- [X] T025 [US2] Состояния `restoring` («Проверка входа…»), `offline` («нет связи»), `expired` в `app/src/components/AccountCard.svelte`

## Phase 5: User Story 3 - Выйти из аккаунта (P3)

**Goal**: выход с отзывом.

**Independent Test**: сценарий 8 из quickstart.md.

- [X] T026 [US3] `revoke(token)` и `Account.sign_out()` в `src/mpv_launcher/google_auth.py`: сначала удалить токен, профиль и аватар, затем отзыв (таймаут 10 с); неудача → `message` «Не удалось отозвать доступ в Google»
- [X] T027 [US3] Метод `account_sign_out` (`io`) в `src/mpv_launcher/backend.py`
- [X] T028 [P] [US3] Тесты выхода (успех, сеть недоступна) в `tests/unit/test_google_auth.py` и `tests/unit/test_backend.py`

## Phase 6: Polish

- [X] T029 [P] `packaging/backend.spec`: `collect_submodules("keyring.backends")` в `hiddenimports`, `google_client.json` в `datas`, если файл существует
- [X] T030 [P] README.md: раздел «Вход через Google» (зачем, как завести клиент по quickstart.md, приложение работает без входа)
- [X] T031 Прогнать pytest, `npx vitest run`, `npm run check`, `npm run build`; проверить блок в браузере с заглушкой backend во всех состояниях
- [ ] T032 Ручная проверка с настоящим клиентом по quickstart.md (за владельцем)

## Dependencies

- Phase 1 → Phase 2 → US1 → US2 → US3 → Polish. US2 и US3 зависят от `Account` из US1.
- T017 → T018 → T019; T025 после T018.

## Parallel Example

- После T007: T008 параллельно с T009.
- В US1: T015, T016, T020 параллельно после T014.

## Implementation Strategy

MVP — US1 (вход и показ профиля). Затем восстановление (US2) и выход (US3). T032 — ручная проверка владельцем после заведения клиента в Google Cloud Console.

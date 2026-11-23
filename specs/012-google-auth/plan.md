# Implementation Plan: Вход через Google

**Branch**: `012-google-auth` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-google-auth/spec.md`

## Summary

Вход по OAuth 2.0 для настольных приложений целиком в Python backend: новый модуль `google_auth.py` открывает системный браузер (`webbrowser`), принимает ответ на `http://127.0.0.1:<свободный порт>/` одноразовым HTTP-сервером, проверяет `state` и обменивает код с PKCE (S256) через `requests`. Refresh token кладётся в системное хранилище через `keyring`. Имя, email и аватар — в `account.json` рядом с настройками; аватар скачивается в кэш и показывается через `asset:`, как постеры (CSP не меняется). Frontend получает новые методы протокола `account_*` и событие `account_changed`; в Settings появляется блок «Аккаунт Google». Для этапа 3 backend предоставляет внутренний `access_token()`.

## Technical Context

**Language/Version**: Python 3.10+ (backend), TypeScript 5.9 + Svelte 5 (frontend)

**Primary Dependencies**: `requests` (уже есть), новая `keyring` (Windows Credential Manager, macOS Keychain); стандартные `http.server`, `secrets`, `hashlib`, `webbrowser`

**Storage**: refresh token — `keyring` (сервис `mpv-cinema-launcher`, имя `google-refresh-token`); профиль — `account.json` в каталоге настроек; аватар — `cache_dir()/avatar.<ext>`; access token — только в памяти

**Testing**: pytest (PKCE, разбор ответа loopback, `state`, обмен и обновление токена с подменённым HTTP, отзыв, хранилище с подменённым keyring, методы backend); Vitest (состояния блока); ручной вход с настоящим клиентом

**Target Platform**: Windows 11 x64, macOS

**Project Type**: настольное приложение (Tauri + Python sidecar)

**Performance Goals**: восстановление входа при старте ≤ 3 с (SC-002); без сети — сразу показать сохранённый профиль

**Constraints**: client secret не в репозитории; ожидание входа не занимает пул `io` (отдельный поток); таймаут 5 мин; приложение работает без входа и без настроенного клиента

**Scale/Scope**: `src/mpv_launcher/google_auth.py` (новый), `backend.py`, `settings.py` (пути), `pyproject.toml`, `packaging/backend.spec`, `app/src/lib/api.ts`, `app/src/components/AccountCard.svelte` (новый), `app/src/screens/Settings.svelte`

## Constitution Check

`.specify/memory/constitution.md` не заполнен (шаблон), проверок нет. После дизайна без изменений.

## Project Structure

### Documentation (this feature)

```text
specs/012-google-auth/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/account-protocol.md
└── tasks.md             # создаёт /speckit-tasks
```

### Source Code (repository root)

```text
src/mpv_launcher/
├── google_auth.py        # новый: клиент, PKCE, loopback, токены, хранилище, профиль
├── backend.py            # методы account_*, событие account_changed, access_token()
└── settings.py           # account_path()
packaging/
├── backend.spec          # keyring.backends в hiddenimports; google_client.json, если есть
└── google_client.json    # не в git: client_id/client_secret для сборки
tests/unit/
├── test_google_auth.py   # новый
└── test_backend.py       # account_*
app/src/
├── lib/api.ts            # типы Account, AccountState, методы и событие
├── components/AccountCard.svelte  # новый
└── screens/Settings.svelte        # блок «Аккаунт Google»
```

**Structure Decision**: Всё общение с Google — в backend, где уже есть `requests`, файлы настроек и протокол; Rust не меняется. Frontend только показывает состояние и шлёт команды.

## Этапы

1. **Клиент и хранилище**: загрузка client_id/secret (переменные окружения → `google_client.json` рядом с backend), `keyring`, `account.json`.
2. **Вход (US1)**: PKCE, loopback-сервер, `state`, обмен кода, userinfo, аватар, отмена и таймаут; блок в Settings.
3. **Восстановление (US2)**: обновление access token при старте, состояния `expired` / `offline` / `no_storage`.
4. **Выход (US3)**: удаление из хранилища, отзыв, событие.
5. **Сборка и README**: `backend.spec`, `.gitignore`, инструкция по заведению клиента в Google Cloud Console.

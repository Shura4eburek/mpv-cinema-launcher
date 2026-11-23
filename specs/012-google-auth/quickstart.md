# Quickstart: проверка входа через Google

## Подготовка (владелец)

1. Google Cloud Console → проект → «APIs & Services»: включить Google Drive API.
2. «OAuth consent screen»: тип External, режим Testing, добавить свой аккаунт в тестировщики; scopes `openid`, `email`, `profile`, `.../auth/drive.appdata`.
3. «Credentials» → «Create OAuth client ID» → тип «Desktop app».
4. Положить `packaging/google_client.json`: `{"client_id": "…", "client_secret": "…"}` (в git не попадает) или задать `MPV_CINEMA_GOOGLE_CLIENT_ID` / `MPV_CINEMA_GOOGLE_CLIENT_SECRET` для `npm run tauri dev`.

## Автотесты

```bash
PYTHONPATH=src python -m pytest -o addopts="" -q -W ignore::DeprecationWarning
cd app && npx vitest run && npm run check
```

## Сценарии

1. **Вход (US1)**: Настройки → «Войти через Google» → браузер → разрешить → в браузере «Вход выполнен», в приложении аватар, имя, email.
2. **Отказ**: на странице Google «Отмена» → «Вход отменён».
3. **Отмена/таймаут**: начать вход, нажать «Отмена» в приложении → состояние «не вошёл»; повторить и подождать 5 минут → «Время входа истекло».
4. **Без сети**: отключить сеть, «Войти» → после ответа браузера «Нет связи с Google».
5. **Восстановление (US2)**: перезапустить приложение → аккаунт на месте без браузера. Отключить сеть и перезапустить → аккаунт с пометкой «нет связи».
6. **Отзыв**: myaccount.google.com → «Сторонние приложения» → удалить доступ → перезапуск → «Нужно войти заново».
7. **Секреты (SC-003)**: после входа поиск refresh token по каталогам настроек и кэша — не найден; в Credential Manager есть `mpv-cinema-launcher`.
8. **Выход (US3)**: «Выйти» → «Войти через Google»; в Credential Manager записи нет; в списке сторонних приложений Google доступа нет.
9. **Без клиента**: без `google_client.json` и переменных → кнопка недоступна с пояснением; остальное приложение работает.

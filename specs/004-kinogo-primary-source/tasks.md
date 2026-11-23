---

description: "Task list for KinoGo as the primary source"
---

# Tasks: KinoGo как основной источник фильмов

**Input**: Design documents from `specs/004-kinogo-primary-source/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: логика покрывается pytest и Vitest; реальные сайты проверяются по quickstart.md.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Foundational

- [x] T001 Создать ветку `004-kinogo-primary-source`, исследовать 10 фильмов и записать результат в `specs/004-kinogo-primary-source/research.md`
- [x] T002 Добавить `source` в `MovieSearchResult`, `source`, `referer`, `alternatives` в `MovieDetails`, выключить звук Chrome в `src/mpv_launcher/scraper.py`
- [x] T003 [P] Добавить `kinogo_url` со значением по умолчанию `https://uakinogo.io` и правилом «только `http` и `https` с непустым хостом» в `src/mpv_launcher/settings.py`, тесты в `tests/unit/test_settings.py`
- [x] T004 [P] Добавить `--network-timeout=10` в `src/mpv_launcher/presets.py`, тест в `tests/unit/test_presets.py`

---

## Phase 2: User Story 1 - Настоящий Full HD (Priority: P1) 🎯 MVP

- [x] T005 [P] [US1] Написать `tests/unit/test_kinogo.py`: разбор выдачи и страницы, подписи по ширине, порядок адресов, короткий поток не считается фильмом, недоступный `atlas` даёт «Качество не подтверждено»
- [x] T006 [US1] Реализовать `src/mpv_launcher/kinogo.py`: поиск, страница фильма, получение ссылки из плеера, варианты качества
- [x] T007 [US1] Подключить KinoGo в `src/mpv_launcher/backend.py`, тесты в `tests/unit/test_backend.py`
- [x] T008 [US1] Показать источник и подписи на `app/src/screens/Movie.svelte`, обновить `app/src/lib/api.ts` и `app/src/lib/logic.ts`, тесты в `app/src/lib/logic.test.ts`
- [x] T009 [US1] Пройти раздел «Настоящий Full HD» из `specs/004-kinogo-primary-source/quickstart.md`

---

## Phase 3: User Story 2 - Запасные варианты (Priority: P2)

- [x] T010 [P] [US2] Написать `tests/unit/test_sources.py`: KinoGo → HDRezka, пустая выдача, оба недоступны, альтернативы при отсутствии видео
- [x] T011 [US2] Реализовать `src/mpv_launcher/sources.py` и подключить в `src/mpv_launcher/backend.py`
- [x] T012 [US2] Получать ссылку заново при запуске, если она старше 30 минут или прошлый запуск не удался, в `src/mpv_launcher/backend.py`, тесты в `tests/unit/test_backend.py`
- [x] T013 [US2] Показать сообщение о запасном источнике в `app/src/screens/Results.svelte` и варианты HDRezka в `app/src/screens/Movie.svelte`
- [x] T014 [US2] Перевести `--search` на `sources` в `src/mpv_launcher/cli.py`, тесты в `tests/unit/test_cli.py`
- [x] T015 [US2] Добавить поле адреса в `app/src/screens/Settings.svelte` и пройти раздел «Запасные варианты» из `specs/004-kinogo-primary-source/quickstart.md`

---

## Phase 4: User Story 3 - Озвучка (Priority: P3)

- [x] T016 [US3] Показать название текущей озвучки KinoGo на `app/src/screens/Movie.svelte` без выбора, если вариант один

---

## Phase 4a: Выбор озвучки (пользователю озвучка важна)

- [x] T019 [US3] Читать список озвучек из плеера и переключать выбранную кликом в `src/mpv_launcher/kinogo.py`, тесты в `tests/unit/test_kinogo.py`
- [x] T020 [US3] Подключить выбор в `src/mpv_launcher/backend.py` и `app/src/screens/Movie.svelte`, сохранять озвучку при обновлении ссылки, тесты в `tests/unit/test_backend.py`

---

## Phase 5: Polish

- [x] T017 [P] Обновить `README.md` и `AI_DEVELOPER_GUIDE.md`
- [x] T018 Прогнать `pytest`, `npm test`, `npm run check`, проверить регрессию и SC-001…SC-006 из `specs/004-kinogo-primary-source/spec.md`

---

## Dependencies & Execution Order

Foundational → US1 → US2 → US3 → Polish. Истории идут последовательно, потому что меняют один экран и `backend.py`.

## Implementation Strategy

MVP: Foundational и US1. Затем запасные варианты, без которых нельзя считать KinoGo основным источником.

---

## Phase 6: Convergence

- [x] T021 Сообщать в окне о переходе на сервер плеера с возможным снижением качества per US2/AC1 (partial)
- [x] T022 Писать в журнал только хост потока, без токена, per contracts/backend-changes.md (contradicts)
- [x] T023 Добавить тесты `--search` через источники в `tests/unit/test_cli.py` per T014 (missing)
- [x] T024 Обновить проверку озвучки в `specs/004-kinogo-primary-source/quickstart.md` per US3 (partial)

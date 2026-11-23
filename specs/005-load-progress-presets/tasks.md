---

description: "Task list for detailed loading and performance presets"
---

# Tasks: Подробная загрузка фильма и пресеты производительности

**Input**: Design documents from `specs/005-load-progress-presets/`

**Tests**: логика покрывается pytest и Vitest; экран и плеер проверяются по quickstart.md.

## Phase 1: User Story 1 - Ход загрузки (Priority: P1)

- [x] T001 [P] [US1] Написать `tests/unit/test_progress.py` и реализовать `src/mpv_launcher/progress.py`
- [x] T002 [US1] Передать шаги и отмену через `src/mpv_launcher/kinogo.py` и `src/mpv_launcher/sources.py`
- [x] T003 [US1] Добавить `progress_id`, `cancel` и закрытие Chrome через 3 секунды в `src/mpv_launcher/backend.py`, тесты в `tests/unit/test_backend.py`
- [x] T004 [US1] Добавить логику шагов в `app/src/lib/logic.ts` с тестами в `app/src/lib/logic.test.ts`
- [x] T005 [US1] Создать `app/src/components/LoadProgress.svelte` и подключить в `app/src/screens/Movie.svelte`

## Phase 2: User Story 2 - Пресеты (Priority: P2)

- [x] T006 [US2] Заменить поля настроек на `preset` с переносом значений в `src/mpv_launcher/settings.py`, тесты в `tests/unit/test_settings.py`
- [x] T007 [P] [US2] Создать `mpv-profiles/mid.conf` и `mpv-profiles/low.conf`, подключить в `src/mpv_launcher/presets.py`, тесты в `tests/unit/test_presets.py`
- [x] T008 [US2] Применять пресет при запуске в `src/mpv_launcher/backend.py` и показать выбор в `app/src/screens/Settings.svelte`

## Phase 3: User Story 3 - Автоопределение (Priority: P3)

- [x] T009 [US3] Написать `tests/unit/test_machine_presets.py` с контрольным списком моделей и реализовать определение в `src/mpv_launcher/machine.py`
- [x] T010 [US3] Добавить метод `device` в `src/mpv_launcher/backend.py` и пояснение в `app/src/screens/Settings.svelte`

## Phase 4: Polish

- [x] T011 [P] Обновить `README.md` и `AI_DEVELOPER_GUIDE.md`
- [x] T012 Проверить установленное приложение по `specs/005-load-progress-presets/quickstart.md`

## Dependencies & Execution Order

US1 и US2 не зависят друг от друга; US3 опирается на US2.

---

## Phase 5: Convergence

- [x] T013 Возвращать прежнюю озвучку при отмене её смены в `app/src/screens/Movie.svelte` per FR-006 (partial)

# Tasks: Поддержка сериалов

**Input**: `specs/008-series-support/` (plan.md, spec.md, research.md, data-model.md, contracts/backend-protocol.md, quickstart.md)

**Tests**: новые тесты разбора, плеера и автооткрытия лежат в tests/unit/test_series.py, протокола в tests/unit/test_backend.py. Для разбора страниц, выбора серии, совпадений и протокола, как в прежних функциях проекта; запуск и внешний вид проверяются по quickstart.md. Спецификация тесты отдельно не требует, но без них нельзя менять тесты фильмов осознанно (SC-005).

## Phase 1: Setup

- [X] T001 Создать git-ветку `008-series-support` от текущей `007-lampac-sources` и проверить, что `specs/008-series-support/` и `.specify/feature.json` в рабочем дереве; прогнать `python -m pytest` и `npm test` в app/ и записать исходный результат в specs/008-series-support/research.md

## Phase 2: Foundational

- [X] T002 Добавить `Episode`, `Season`, `SeriesInfo` (поля `seasons`, `season`, `episode`, `moved`) и поля `MovieDetails.series`, `MovieDetails.switched_from` в src/mpv_launcher/scraper.py по specs/008-series-support/data-model.md
- [X] T003 Реализовать `nearest_episode` в src/mpv_launcher/scraper.py: «та же; иначе в том же сезоне серия с ближайшим номером; иначе ближайший по номеру сезон и его первая серия»; `moved = true`, если выбрана не запрошенная; при `episode = None` первая серия и `moved = false`; нечисловые id сравниваются по первому числу в строке, без числа выбирается первая серия; тесты в tests/unit/test_scraper_and_launcher.py
- [X] T004 [P] Добавить типы `Season`, `Episode`, `SeriesInfo`, поля `series`, `switched_from`, `season`, `episode` в `PlayDetails` и метод `api.episode` в app/src/lib/api.ts по specs/008-series-support/contracts/backend-protocol.md
- [X] T005 [P] Добавить `episodeTitle(title, seasonName, episodeName)` («Во все тяжкие — Сезон 2, Серия 3») и шаги `episodeSteps(source)` в app/src/lib/logic.ts с тестами в app/src/lib/logic.test.ts

## Phase 3: User Story 1 - Выбрать серию и смотреть (P1)

**Goal**: на HDRezka можно выбрать сезон и серию и запустить её; фильмы не затронуты.

**Independent Test**: «Во все тяжкие» на HDRezka: сезон 2, серия 3, «Смотреть», в mpv эта серия. «El Camino» без списков.

- [X] T006 [US1] Реализовать `parse_series(soup, seasons_soup=None)` в src/mpv_launcher/scraper.py: сериал только при наличии `.b-simple_episode__item`; сезоны из `data-season_id`, названия из `.b-simple_season__item`, иначе «Сезон N»; текущая серия по классу `active`; тесты с разметкой из research.md §5 в tests/unit/test_scraper_and_launcher.py
- [X] T007 [US1] Заполнять `series` в `fetch_movie_details` и брать `active_translator_id` из `initCDNSeriesEvents`, если списка озвучек нет, в src/mpv_launcher/scraper.py; тест, что у фильма `series is None`
- [X] T008 [US1] Вынести запрос к `/ajax/get_cdn_series/` в общую функцию и добавить `fetch_series_list` (`action=get_episodes`) и `fetch_episode_streams` (`action=get_stream`) в src/mpv_launcher/scraper.py; ответ `success:false` даёт пустые потоки, а не исключение; `fetch_translator_streams` для фильмов сохраняет поведение; тесты в tests/unit/test_scraper_and_launcher.py
- [X] T009 [US1] Добавить метод `episode` в src/mpv_launcher/backend.py для HDRezka: проверка параметров, очередь Selenium, `_tracked`, возврат на страницу сериала, если драйвер ушёл, `nearest_episode`, ошибка `no_streams`, кеш с ключом `(адрес, озвучка, сезон, серия, источник)`; ответ по contracts/backend-protocol.md; тесты в tests/unit/test_backend.py
- [X] T010 [US1] Добавить списки сезона и серии в app/src/screens/Movie.svelte: `Dropdown` при `details.series`; смена сезона передаёт `episode: null`; отбрасывание устаревших ответов через `requestId`; отмена возвращает прежние сезон и серию, как `previousTranslator`; ход загрузки через `LoadProgress`
- [X] T011 [US1] Передавать в `play` название из `episodeTitle` и поля `season`, `episode` в app/src/screens/Movie.svelte; принимать их в `_play` в src/mpv_launcher/backend.py

## Phase 4: User Story 2 - Сменить озвучку сериала (P1)

**Goal**: смена озвучки сериала сохраняет серию и не даёт ложной ошибки.

**Independent Test**: на HDRezka сменить озвучку на сезоне 2, серии 3: серия та же, качество загрузилось; для озвучки без серии выбрана ближайшая и показано сообщение.

- [X] T012 [US2] Для сериала направлять `chooseTranslator` и применение сохранённой озвучки в `load` на `api.episode` в app/src/screens/Movie.svelte, обновлять `translators` и `series` из ответа; `translator_streams` остаётся для фильмов
- [X] T013 [US2] Показывать сообщение при `series.moved` («Выбранной серии в этой озвучке нет, открыта ближайшая») в app/src/screens/Movie.svelte с текстом в app/src/lib/logic.ts и тестом в app/src/lib/logic.test.ts
- [X] T014 [US2] Тест в tests/unit/test_backend.py: сериал HDRezka со сменой озвучки не вызывает `action=get_movie`, отсутствующая серия даёт `moved`, отказ сайта даёт `no_streams`

## Phase 5: User Story 3 - KinoGo как основной источник для сериалов (P2)

**Goal**: сериал открывается на KinoGo; если видео нет и совпадение однозначно, сразу открывается HDRezka.

**Independent Test**: карточка KinoGo «Во все тяжкие» показывает источник KinoGo, сезоны, серии и озвучки; серии «Мини-эпизодов» запускаются.

- [X] T015 [US3] Заменить поиск `/movies/` в `_on_host` на снятие первого сегмента-подписи (`\d+-...`) в src/mpv_launcher/kinogo.py; тесты на `/movies/` и `/tvseries/` в tests/unit/test_kinogo.py
- [X] T016 [US3] Заменить `_READ_VOICES` чтением всех `#player .playlist-group` и добавить чистую `classify_groups` в src/mpv_launcher/kinogo.py: все кнопки `Сезон N` — сезоны, все `Серия N` — серии, первая из остальных — озвучки; группы с одной кнопкой учитываются; без групп прежний `voice_from_text`; тесты на сериал, «Мини-эпизоды», фильм и сериал без группы сезонов в tests/unit/test_kinogo.py
- [X] T017 [US3] Заменить `_CLICK_VOICE` кликом по группе и имени и добавить в `capture_stream` порядок «озвучка → сезон → серия» без нажатия активных кнопок, чтение состояния после кликов и ближайшую серию через `nearest_episode`; вернуть вместо кортежа структуру с потоком, озвучками и `SeriesInfo`; в src/mpv_launcher/kinogo.py, тесты в tests/unit/test_kinogo.py
- [X] T018 [US3] Добавить `min_seconds` в `build_streams`: для сериала 0, для фильма `MIN_MOVIE_SECONDS`; в `fetch_movie` добавить параметры `season`, `episode` и заполнение `details.series` в src/mpv_launcher/kinogo.py; тест, что короткий поток без группы серий отбрасывается, а с группой принимается, в tests/unit/test_kinogo.py
- [X] T019 [US3] Подключить KinoGo в метод `episode` в src/mpv_launcher/backend.py с обновлением `translators`, так как набор озвучек зависит от сезона; тесты в tests/unit/test_backend.py
- [X] T020 [US3] Добавить сезон и серию в `_refreshed_urls` и ключ `_refreshed` `(адрес, озвучка, сезон, серия)` в src/mpv_launcher/backend.py; тест, что устаревшая ссылка обновляется на ту же серию, в tests/unit/test_backend.py
- [X] T021 [US3] Показывать пустые списки серий невыбранных сезонов KinoGo корректно в app/src/screens/Movie.svelte: выбор такого сезона загружает его серии
- [X] T022 [US3] Расширить `clean_title` снятием `(1-5 сезон)` и добавить `single_match` в src/mpv_launcher/sources.py: равенство нормализованного названия или части через ` / `, сравнение типа (HDRezka: `/series/` или диапазон лет в `info`; KinoGo: `/serialy/` или отметка сезона), уточнение по году, при неоднозначности `None`; тесты с выдачей «Во все тяжкие», «Мини-эпизоды», «Медведи», «El Camino» в tests/unit/test_sources.py
- [X] T023 [US3] Автоматически открывать единственное совпадение в `open_movie` с `switched_from = "kinogo"` в src/mpv_launcher/sources.py; пустая страница HDRezka или отсутствие совпадения оставляют список `alternatives`; проверка отмены перед загрузкой; тесты в tests/unit/test_sources.py
- [X] T024 [US3] `_forget_page` должен сравнивать и адрес внутри кешированного ответа в src/mpv_launcher/backend.py; тест в tests/unit/test_backend.py
- [X] T025 [US3] Показывать смену источника при `switched_from` в app/src/screens/Movie.svelte («На KinoGo видео нет, открыто с HDRezka»)
- [X] T026 [US3] Проверить CLI на сериале с `--dry-run` и поправить только падения в src/mpv_launcher/cli.py; тест в tests/unit/test_cli_search.py (падений нет: CLI запускает первую серию, правки и новый тест не понадобились)

## Phase 6: User Story 4 - Сериалы в рекомендациях (P3)

**Goal**: сериалы есть в рекомендациях и открываются со списком серий.

**Independent Test**: фильм с рекомендованным сериалом: карточка открывается с выбором серии.

- [X] T027 [P] [US4] Убрать отсев сериалов из `_related` и `_SEASONS` там, где он больше не нужен, в src/mpv_launcher/kinogo.py; изменить проверяющие его тесты в tests/unit/test_kinogo_extras.py
- [X] T028 [P] [US4] Убрать отсев сериалов из `parse_related` в src/mpv_launcher/scraper.py; изменить проверяющие его тесты в tests/unit/test_scraper_and_launcher.py

## Phase 7: Polish

- [X] T029 [P] Описать сериалы, `episode`, группы плеера, `/tvseries/`, поведение `atlas`, отказ «Время сессии истекло» и автооткрытие в AI_DEVELOPER_GUIDE.md
- [X] T030 [P] Добавить метод `episode` и поля в specs/003-app-player-ui/contracts/backend-protocol.md
- [X] T031 Прогнать `python -m pytest`, `npm test`, `npm run check` и сравнить с результатом T001
- [X] T032 Пройти сценарии specs/008-series-support/quickstart.md на живых сайтах в приложении; записать результат и замеры SC-003 в specs/008-series-support/research.md (проверено через backend и интерфейс в скрытом браузере, см. research.md §9; в настоящем окне с mpv подтвердил пользователь)

## Dependencies

- Phase 2 блокирует все истории; T003 нужен T009 и T017.
- US1 → US2: обе работают с одним `Movie.svelte` и методом `episode`.
- US3 зависит от `episode` и интерфейса из US1 (T009, T010). T022–T025 от остальных задач US3 не зависят.
- US4 независима от остальных кода, но проверяется после US1.

## Parallel Example

```text
T004, T005 — разные файлы интерфейса
T027, T028 — разные источники
T029, T030 — разные документы
```

Правки `Movie.svelte`, `backend.py` и `kinogo.py` идут последовательно: один файл.

## Implementation Strategy

- **MVP**: Phase 1–4: сериалы на HDRezka, включая смену озвучки. Это снимает ошибку из исходной жалобы.
- **Затем**: US3, KinoGo как основной источник с лучшим качеством и автооткрытие.
- **В конце**: US4 и Polish.

## Phase 8: Convergence

- [X] T033 При смене сезона или серии считать текущую озвучку необязательной, а явно выбранную зрителем обязательной, в src/mpv_launcher/backend.py, app/src/screens/Movie.svelte, app/src/lib/api.ts и specs/008-series-support/contracts/backend-protocol.md, с тестом в tests/unit/test_backend.py и проверкой на живом сайте per US1/AC2, FR-005 (contradicts)
- [X] T034 Проверить на живых сайтах третий сериал, аниме или мультсериал, мини-сериал и длинный список серий и записать результат в specs/008-series-support/research.md per SC-002, FR-001, Edge Cases (partial)

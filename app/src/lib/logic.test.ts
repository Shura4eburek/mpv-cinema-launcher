import { describe, expect, it } from "vitest";
import css from "../styles/theme.css?raw";
import type { WatchEntry, WatchStatus } from "./api";
import {
  contrastRatio,
  canSyncNow,
  describeAccount,
  describeSync,
  syncedAgo,
  initials,
  neighbourEpisodes,
  titleFacts,
  countByStatus,
  filterWatchlist,
  rebaseUrl,
  watchedCount,
  applyStep,
  bestQuality,
  describeDevice,
  describeError,
  failedStep,
  formatElapsed,
  movieSteps,
  voiceSteps,
  sortQualities,
  sourceName,
  truncate,
  yearFrom,
} from "./logic";
import { bestLampacSource, describeLampacState, describeStreamError, episodeSteps, episodeTitle, looksLikeSeries, mirrorSummary, mirrorsAsText, pickLampacItem, switchedSourceNotice } from "./logic";
import type { MirrorReport } from "./api";
import type { ErrorCode } from "./api";

describe("truncate", () => {
  it("оставляет короткое название без изменений", () => {
    expect(truncate("Довод", 10)).toBe("Довод");
  });

  it("обрезает длинное название многоточием", () => {
    expect(truncate("Очень длинное название", 10)).toBe("Очень дли…");
  });
});

describe("yearFrom", () => {
  it.each([
    ["2020, США, Фантастика", "2020"],
    ["3 сентября 1999 года", "1999"],
    ["без года", null],
    ["12345", null],
    ["", null],
  ])("%s → %s", (text, year) => {
    expect(yearFrom(text)).toBe(year);
  });
});

describe("качество", () => {
  it("сортирует от высокого к низкому, остальное в конце", () => {
    expect(sortQualities(["360p", "Auto", "1080p", "720p"])).toEqual([
      "1080p",
      "720p",
      "360p",
      "Auto",
    ]);
  });

  it("считает 4K и 2K выше 1080p", () => {
    expect(sortQualities(["1080p", "360p", "2K", "4K"])).toEqual(["4K", "2K", "1080p", "360p"]);
    expect(bestQuality(["1080p", "4K"], null)).toBe("4K");
  });

  it("берёт сохранённое качество, только если оно есть у фильма", () => {
    expect(bestQuality(["1080p", "720p"], "720p")).toBe("720p");
    expect(bestQuality(["1080p", "720p"], "480p")).toBe("1080p");
    expect(bestQuality(["1080p"], null)).toBe("1080p");
    expect(bestQuality([], "720p")).toBeNull();
  });
});

describe("источник и качество KinoGo", () => {
  it("называет источник понятным именем", () => {
    expect(sourceName("kinogo")).toBe("KinoGo");
    expect(sourceName("hdrezka")).toBe("HDRezka");
  });

  it("неподтверждённое качество не обгоняет реальные варианты", () => {
    expect(sortQualities(["Качество не подтверждено", "240p", "1080p"])).toEqual([
      "1080p",
      "240p",
      "Качество не подтверждено",
    ]);
  });
});

describe("ход загрузки", () => {
  it("показывает разные шаги для источников", () => {
    expect(movieSteps("kinogo").map((s) => s.id)).toEqual(["page", "player", "stream", "quality"]);
    expect(movieSteps("hdrezka").map((s) => s.id)).toEqual(["page"]);
    expect(voiceSteps("kinogo").map((s) => s.id)).toContain("voice");
  });

  it("обновляет только нужный шаг", () => {
    const started = applyStep(movieSteps("kinogo"), "page", "done");
    const steps = applyStep(started, "player", "running");
    expect(steps.map((s) => s.state)).toEqual(["done", "running", "pending", "pending"]);
  });

  it("ставит новый шаг перед ещё не начатыми", () => {
    let steps = applyStep(movieSteps("kinogo"), "page", "done");
    steps = applyStep(steps, "player", "done");
    steps = applyStep(steps, "stream", "done");
    steps = applyStep(steps, "voice", "running");
    expect(steps.map((s) => s.id)).toEqual(["page", "player", "stream", "voice", "quality"]);
  });

  it("скрывает шаг, который не понадобился", () => {
    let steps = applyStep(voiceSteps("kinogo"), "stream", "done");
    steps = applyStep(steps, "quality", "running");
    expect(steps.map((s) => s.id)).toEqual(["stream", "quality"]);
  });

  it("добавляет запасной источник с названием", () => {
    const steps = applyStep([], "fallback", "running");
    expect(steps).toEqual([{ id: "fallback", label: "Ищем фильм на HDRezka", state: "running" }]);
  });

  it("находит шаг с ошибкой", () => {
    expect(failedStep(movieSteps("kinogo"))).toBeNull();
    expect(failedStep(applyStep(movieSteps("kinogo"), "stream", "error"))?.id).toBe("stream");
  });

  it.each([
    [0, "0:00"],
    [9.9, "0:09"],
    [65, "1:05"],
    [-1, "0:00"],
  ])("время %s → %s", (seconds, text) => {
    expect(formatElapsed(seconds)).toBe(text);
  });
});

describe("устройство", () => {
  it("показывает пресет и видеокарту", () => {
    expect(describeDevice({ preset: "high", gpu: "RTX 4070 Ti" })).toBe("Сейчас: High, RTX 4070 Ti");
  });

  it("показывает RTX VSR только для High", () => {
    expect(describeDevice({ preset: "high", gpu: "RTX 4070 Ti", vsr: true })).toBe("Сейчас: High, RTX 4070 Ti, для фильмов RTX VSR");
    expect(describeDevice({ preset: "mid", gpu: "RTX 3060", vsr: true })).toBe("Сейчас: Mid, RTX 3060");
  });

  it("честно сообщает, если видеокарта не определена", () => {
    expect(describeDevice({ preset: "low", gpu: null })).toContain("определить не удалось");
  });
});

describe("describeError", () => {
  const codes: ErrorCode[] = [
    "network",
    "not_found",
    "no_streams",
    "no_mpv",
    "no_url",
    "all_mirrors_failed",
    "player_failed",
    "lower_quality",
    "cancelled",
    "invalid_params",
    "backend_down",
    "internal",
  ];

  it.each(codes)("%s: понятное сообщение без кода ошибки", (code) => {
    const view = describeError(code);
    expect(view.title).not.toBe("");
    expect(view.hint).not.toBe("");
    expect(`${view.title} ${view.hint}`).not.toContain(code);
  });

  it("предлагает повтор только там, где он имеет смысл", () => {
    expect(describeError("network").retry).toBe(true);
    expect(describeError("all_mirrors_failed").retry).toBe(true);
    expect(describeError("backend_down").retry).toBe(true);
    expect(describeError("no_mpv").retry).toBe(false);
    expect(describeError("no_url").retry).toBe(false);
  });

  it("объясняет установку mpv", () => {
    expect(describeError("no_mpv").hint).toContain("winget install mpv");
  });
});

describe("проверка зеркал", () => {
  const row = (state: MirrorReport["state"], url: string): MirrorReport => ({
    site: "kinogo",
    url,
    state,
    http: state === "ok" ? 200 : null,
    ms: 120,
    final_host: null,
    server: "nginx",
    count: state === "ok" ? 13 : 0,
    matches: state === "ok" ? 13 : 0,
    first: state === "ok" ? "Довод (2020)" : null,
    first_url: null,
    detail: state === "down" ? "Нет соединения" : "",
  });

  it("считает ход и итог", () => {
    expect(mirrorSummary([row("ok", "a"), row("checking", "b")])).toBe("Проверено 1 из 2");
    expect(mirrorSummary([row("ok", "a"), row("down", "b")])).toBe("Работает 1 из 2");
  });

  it("собирает отчёт текстом", () => {
    const text = mirrorsAsText("Довод", [row("ok", "https://a"), row("down", "https://b")]);
    expect(text).toContain("запрос «Довод»");
    expect(text).toContain("KinoGo https://a: Работает; HTTP 200; 120 мс; сервер nginx; карточек 13; с запросом 13; первая: Довод (2020)");
    expect(text).toContain("KinoGo https://b: Не отвечает; HTTP нет ответа; 120 мс; сервер nginx; карточек 0; с запросом 0; Нет соединения");
  });
});

describe("Lampac", () => {
  const item = (voice: string, episode: string | null = null) => ({
    voice,
    qualities: [{ label: "720p", url: "u" }],
    subtitles: [],
    episode: episode ? { season: 1, number: 1, name: episode } : null,
  });
  const variants = (voices: number, items = [item("А")]) => ({
    url: "s",
    kind: "movie" as const,
    seasons: [],
    voices: Array.from({ length: voices }, (_, i) => ({ name: String(i), url: "v", active: false })),
    items,
  });

  it("выбирает вариант по озвучке, иначе первый", () => {
    const two = variants(0, [item("А"), item("Б")]);
    expect(pickLampacItem(two, "Б")?.voice).toBe("Б");
    expect(pickLampacItem(two, "Нет")?.voice).toBe("А");
    expect(pickLampacItem(variants(0, []), "А")).toBeNull();
  });

  it("выбирает серию по названию", () => {
    const list = variants(0, [item("А", "1 серия"), item("А", "2 серия")]);
    expect(pickLampacItem(list, "А", "2 серия")?.episode?.name).toBe("2 серия");
    const voices = variants(0, [item("А", "1 серия"), item("Б", "1 серия")]);
    expect(pickLampacItem(voices, "Б", "1 серия")?.voice).toBe("Б");
  });

  it("предпочитает источник с большим числом озвучек", () => {
    const sources = [{ id: "a", variants: variants(0) }, { id: "b", variants: variants(7) }, { id: "c", variants: variants(7) }];
    expect(bestLampacSource(sources)?.id).toBe("b");
    expect(bestLampacSource([])).toBeNull();
  });

  it("узнаёт сериал", () => {
    expect(looksLikeSeries("https://k/serialy/1.html", "Т", "")).toBe(true);
    expect(looksLikeSeries("https://r/series/1.html", "Т", "")).toBe(true);
    expect(looksLikeSeries("https://k/1.html", "Проект (1-2 сезон)", "")).toBe(true);
    expect(looksLikeSeries("https://k/1.html", "Т", "Сериалы / Драма")).toBe(true);
    expect(looksLikeSeries("https://k/filmy/1.html", "Сезон охоты (2006)", "Фильмы / Комедия")).toBe(false);
  });

  it("описывает состояние", () => {
    expect(describeLampacState({ state: "running", detail: "Порт 5000", available: true })).toBe("Работает. Порт 5000");
    expect(describeLampacState({ state: "error", detail: "занят порт", available: true })).toBe("Ошибка: занят порт");
    expect(describeLampacState({ state: "off", detail: "", available: true })).toBe("Выключен");
    expect(describeLampacState({ state: "off", detail: "", available: false })).toBe("Не входит в эту сборку");
    expect(describeLampacState(null)).toBe("Не входит в эту сборку");
  });
});

describe("сериалы", () => {
  it("собирает заголовок плеера без отметки сезонов сайта", () => {
    expect(episodeTitle("Во все тяжкие (1-5 сезон)", "Сезон 2", "Серия 3")).toBe("Во все тяжкие — Сезон 2, Серия 3");
    expect(episodeTitle("Во все тяжкие", "Сезон 1", "Серия 1")).toBe("Во все тяжкие — Сезон 1, Серия 1");
    expect(episodeTitle("Сезон охоты", null, null)).toBe("Сезон охоты");
    expect(episodeTitle("Проект (1-5 сезон) (2020)", "Сезон 2", "Серия 3")).toBe("Проект — Сезон 2, Серия 3");
  });

  it("показывает шаги загрузки серии по источнику", () => {
    expect(episodeSteps("kinogo").map((s) => s.id)).toContain("episode");
    expect(episodeSteps("hdrezka").map((s) => s.id)).toEqual(["episode"]);
  });

  it("описывает отсутствие видео по-разному для серии и фильма", () => {
    expect(describeStreamError("no_streams", true).title).toBe("Для этой серии видео не найдено");
    expect(describeStreamError("no_streams", false).title).toBe("Для этой озвучки видео не найдено");
    expect(describeStreamError("network", true).retry).toBe(true);
  });

  it("сообщает о смене источника только при автооткрытии", () => {
    expect(switchedSourceNotice("kinogo", "hdrezka")).toBe("На KinoGo видео нет, открыто с HDRezka.");
    expect(switchedSourceNotice(null, "hdrezka")).toBeNull();
  });

  it("предпочитает неподтверждённый вариант низкому качеству, но не сохранённому", () => {
    const labels = ["Качество не подтверждено", "480p", "360p"];
    expect(bestQuality(labels, "1080p")).toBe("Качество не подтверждено");
    expect(bestQuality(labels, "480p")).toBe("480p");
    expect(bestQuality(["720p", "1080p"], null)).toBe("1080p");
  });
});

function entry(key: string, status: WatchStatus, episodes: Record<string, string[]> = {}): WatchEntry {
  return {
    key, status, episodes, title: key, orig_title: null, year: null, kind: "series",
    url: "https://uakinogo.io/serialy/1.html", poster_url: null, source: "kinogo",
    updated_at: "", deleted_at: null,
  };
}

describe("мой список", () => {
  const items = [entry("a", "watching"), entry("b", "planned"), entry("c", "watching")];

  it("фильтрует по статусу и считает", () => {
    expect(filterWatchlist(items, "all")).toHaveLength(3);
    expect(filterWatchlist(items, "watching").map((i) => i.key)).toEqual(["a", "c"]);
    expect(countByStatus(items)).toEqual({ all: 3, watching: 2, planned: 1, completed: 0 });
  });

  it("быстро справляется с 500 записями", () => {
    const many = Array.from({ length: 500 }, (_, n) => entry(String(n), (["watching", "planned", "completed"] as const)[n % 3]));
    const started = performance.now();
    expect(countByStatus(many).completed).toBe(166);
    expect(filterWatchlist(many, "planned")).toHaveLength(167);
    expect(performance.now() - started).toBeLessThan(50);
  });

  it("переводит адрес на текущее зеркало", () => {
    expect(rebaseUrl("https://old.io/filmy/1-x.html?a=1", "https://uakinogo.io")).toBe("https://uakinogo.io/filmy/1-x.html?a=1");
    expect(rebaseUrl("https://old.io/filmy/1-x.html", null)).toBe("https://old.io/filmy/1-x.html");
    expect(rebaseUrl("не адрес", "https://uakinogo.io")).toBe("не адрес");
  });

  it("считает отмеченные серии только из списка сезона", () => {
    const e = entry("s", "watching", { "1": ["1", "2", "9"] });
    expect(watchedCount(e, "1", ["1", "2", "3"])).toBe(2);
    expect(watchedCount(e, "2", ["1"])).toBe(0);
    expect(watchedCount(null, "1", ["1"])).toBe(0);
  });
});

describe("страница тайтла", () => {
  it("палитра theme.css читаема: контраст текста не ниже 4.5:1 на всех поверхностях", () => {
    const token = (name: string) => css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1] ?? "";
    for (const text of ["text", "muted", "body"]) {
      for (const surface of ["bg", "surface", "surface-2", "hover", "input", "popover"]) {
        expect(contrastRatio(token(text), token(surface)), `${text} на ${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 0);
  });

  it("раскладывает факты KinoGo", () => {
    const facts = titleFacts(
      { "Год": "2022", "Страна": "Великобритания", "Жанр": "Фантастика, Триллер, Фантастика", "Режиссер": "Марк Манден", "Рейтинги": "КиноПоиск: 7.1, IMDb: 6.8" },
      "series",
      8,
    );
    expect(facts.badges).toEqual([
      { label: "КП 7.1", tone: "rating" },
      { label: "Сериал", tone: "plain" },
      { label: "2022", tone: "plain" },
      { label: "8 эп.", tone: "plain" },
    ]);
    expect(facts.chips).toEqual([{ label: "Страна", value: "Великобритания" }, { label: "Режиссёр", value: "Марк Манден" }]);
    expect(facts.genres).toEqual(["Фантастика", "Триллер"]);
    expect(facts.siteQuality).toBeNull();
    expect(facts.year).toBe("2022");
    expect(titleFacts({}, "series", 8, 3).badges.map((b) => b.label)).toEqual(["Сериал", "3 сез."]);
  });

  it("раскладывает факты HDRezka с длительностью и возрастом", () => {
    const facts = titleFacts(
      { "Дата выхода": "31 марта 1999 года", "Рейтинги": "IMDb: 8,7 (2.1M)", "Время": "136 мин.", "Возраст": "16+ только для взрослых", "В качестве": "1080p" },
      "film",
      0,
    );
    expect(facts.badges.map((b) => b.label)).toEqual(["IMDb 8.7", "Фильм", "1999", "136 мин.", "16+"]);
    expect(facts.badges.at(-1)?.tone).toBe("outline");
    expect(facts.chips).toEqual([{ label: "Дата выхода", value: "31 марта 1999 года" }]);
    expect(facts.siteQuality).toBe("1080p");
  });

  it("не показывает пустые факты", () => {
    const facts = titleFacts({ "Страна": " ", "Жанр": "" }, "film", 0);
    expect(facts.badges).toEqual([{ label: "Фильм", tone: "plain" }]);
    expect(facts.chips).toEqual([]);
    expect(facts.genres).toEqual([]);
  });

  it("находит соседние серии", () => {
    const list = [{ id: "1" }, { id: "2" }, { id: "3" }];
    expect(neighbourEpisodes(list, "2")).toEqual({ previous: "1", next: "3" });
    expect(neighbourEpisodes(list, "1")).toEqual({ previous: null, next: "2" });
    expect(neighbourEpisodes(list, "3")).toEqual({ previous: "2", next: null });
    expect(neighbourEpisodes(list, "9")).toEqual({ previous: null, next: null });
  });
});

describe("initials", () => {
  it("берёт первые буквы двух слов имени", () => {
    expect(initials("тест тестов иванович", "a@b.c")).toBe("ТТ");
    expect(initials("Mamoru", "a@b.c")).toBe("M");
  });

  it("без имени — первая буква email", () => {
    expect(initials("  ", "user@example.com")).toBe("U");
    expect(initials("", "")).toBe("?");
  });
});

describe("describeAccount", () => {
  const base = { account: null, storage_warning: false, message: null };

  it("поясняет состояния", () => {
    expect(describeAccount(null)).toBeNull();
    expect(describeAccount({ ...base, state: "signed_in" })).toBeNull();
    expect(describeAccount({ ...base, state: "unconfigured" })).toContain("не настроен");
    expect(describeAccount({ ...base, state: "offline" })).toContain("Нет связи");
    expect(describeAccount({ ...base, state: "expired" })).toBe("Нужно войти заново.");
  });

  it("показывает сообщение backend", () => {
    expect(describeAccount({ ...base, state: "signed_out", message: "Вход отменён" })).toBe("Вход отменён");
  });
});

describe("describeSync", () => {
  const base = { pending: false, last_synced_at: null, message: null };
  const now = new Date("2026-11-16T12:00:00Z");

  it("описывает каждое состояние", () => {
    expect(describeSync(null)).toBeNull();
    expect(describeSync({ ...base, state: "disabled" })).toBe("Только на этом устройстве");
    expect(describeSync({ ...base, state: "syncing" })).toBe("Синхронизация…");
    expect(describeSync({ ...base, state: "offline" })).toBe("Нет связи");
    expect(describeSync({ ...base, state: "offline", pending: true })).toBe("Нет связи — изменения отправятся позже");
    expect(describeSync({ ...base, state: "auth_required" })).toBe("Нужно войти заново");
    expect(describeSync({ ...base, state: "error", message: "Список в облаке не читается" })).toBe("Список в облаке не читается");
    expect(describeSync({ ...base, state: "error" })).toBe("Ошибка синхронизации");
  });

  it("показывает время синхронизации", () => {
    expect(describeSync({ ...base, state: "idle" }, now)).toBe("Синхронизировано");
    expect(describeSync({ ...base, state: "idle", pending: true }, now)).toBe("Изменения ждут отправки");
    expect(describeSync({ ...base, state: "idle", last_synced_at: "2026-11-16T11:59:40Z" }, now)).toBe("Синхронизировано · только что");
    expect(describeSync({ ...base, state: "idle", last_synced_at: "2026-11-16T11:55:00Z" }, now)).toBe("Синхронизировано · 5 мин назад");
    expect(syncedAgo("bad", now)).toBeNull();
    expect(syncedAgo("2026-11-16T09:00:00Z", now)).toMatch(/^\d{2}:\d{2}$/);
  });

  it("ручной запуск только в спокойных состояниях", () => {
    expect(canSyncNow({ ...base, state: "idle" })).toBe(true);
    expect(canSyncNow({ ...base, state: "offline" })).toBe(true);
    expect(canSyncNow({ ...base, state: "error" })).toBe(true);
    expect(canSyncNow({ ...base, state: "syncing" })).toBe(false);
    expect(canSyncNow({ ...base, state: "disabled" })).toBe(false);
    expect(canSyncNow(null)).toBe(false);
  });
});

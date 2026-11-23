// Логика интерфейса без зависимостей от окна, чтобы её можно было тестировать.
import type { AccountState, SyncState, Device, ErrorCode, LampacItem, LampacState, LampacVariants, MirrorReport, MirrorState, SourceId, WatchEntry, WatchStatus } from "./api";

const QUALITY_ORDER = ["4k", "2160p", "2k", "1440p", "1080p", "720p", "480p", "360p", "240p"];

const SOURCE_NAMES: Record<SourceId, string> = { kinogo: "KinoGo", hdrezka: "HDRezka", lampac: "Lampac" };

export function sourceName(source: SourceId): string {
  return SOURCE_NAMES[source] ?? source;
}

export function pickLampacItem(variants: LampacVariants, voice: string, episode: string | null = null): LampacItem | null {
  const sameEpisode = episode ? variants.items.filter((item) => item.episode?.name === episode) : variants.items;
  return sameEpisode.find((item) => item.voice === voice) ?? sameEpisode[0] ?? variants.items[0] ?? null;
}

/** Озвучка важна: источник с одной дорожкой часто отдаёт только оригинал и выбирается последним. */
export function bestLampacSource<T extends { variants: LampacVariants }>(sources: T[]): T | null {
  const voices = (source: T) => source.variants.voices.length;
  return sources.reduce<T | null>((best, source) => (!best || voices(source) > voices(best) ? source : best), null);
}

export function looksLikeSeries(url: string, title: string, genre: string): boolean {
  return /\/(serialy|series|animation)\//i.test(url) || /\d\s*сезон|сезон\s*\d/i.test(title) || /сериал/i.test(genre);
}

export function describeLampacState(state: LampacState | null): string {
  if (!state || !state.available) return "Не входит в эту сборку";
  if (state.state === "running") return state.detail ? `Работает. ${state.detail}` : "Работает";
  if (state.state === "starting") return "Запускается…";
  if (state.state === "error") return `Ошибка: ${state.detail}`;
  return "Выключен";
}

const MIRROR_STATES: Record<MirrorState, { label: string; tone: "" | "good" | "warn" | "bad" }> = {
  checking: { label: "Проверяем…", tone: "" },
  ok: { label: "Работает", tone: "good" },
  empty: { label: "Нет результатов", tone: "warn" },
  blocked: { label: "Закрыт проверкой", tone: "bad" },
  error: { label: "Ошибка сайта", tone: "bad" },
  down: { label: "Не отвечает", tone: "bad" },
};

export function describeMirrorState(state: MirrorState) {
  return MIRROR_STATES[state];
}

export function mirrorSummary(rows: MirrorReport[]): string {
  const left = rows.filter((row) => row.state === "checking").length;
  const working = rows.filter((row) => row.state === "ok").length;
  return left ? `Проверено ${rows.length - left} из ${rows.length}` : `Работает ${working} из ${rows.length}`;
}

export function mirrorsAsText(query: string, rows: MirrorReport[]): string {
  const lines = rows.map((row) =>
    [
      `${sourceName(row.site)} ${row.url}: ${MIRROR_STATES[row.state].label}`,
      `HTTP ${row.http ?? "нет ответа"}`,
      `${row.ms ?? "?"} мс`,
      row.server && `сервер ${row.server}`,
      `карточек ${row.count}`,
      `с запросом ${row.matches}`,
      row.first && `первая: ${row.first}`,
      row.detail,
    ]
      .filter(Boolean)
      .join("; "),
  );
  return [`Проверка зеркал, запрос «${query}»`, mirrorSummary(rows), ...lines].join("\n");
}

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

export function yearFrom(text: string): string | null {
  return text.match(/(?<!\d)(?:19|20)\d{2}(?!\d)/)?.[0] ?? null;
}

function qualityRank(label: string): number {
  const index = QUALITY_ORDER.indexOf(label.toLowerCase());
  return index === -1 ? QUALITY_ORDER.length : index;
}

export function sortQualities(labels: string[]): string[] {
  return [...labels].sort((a, b) => qualityRank(a) - qualityRank(b));
}

// Подпись варианта с сервера плеера (kinogo.UNCONFIRMED).
const UNCONFIRMED_QUALITY = "Качество не подтверждено";

export function bestQuality(labels: string[], saved: string | null): string | null {
  if (saved && labels.includes(saved)) return saved;
  // Рядом с другими вариантами он бывает, только когда верхние недоступны: остальные заметно хуже.
  if (labels.includes(UNCONFIRMED_QUALITY)) return UNCONFIRMED_QUALITY;
  return sortQualities(labels)[0] ?? null;
}

export interface Fact {
  label: string;
  value: string;
}

export type StepState = "pending" | "running" | "done" | "error";

export interface LoadStep {
  id: string;
  label: string;
  state: StepState;
}

export const SLOW_LOAD_SECONDS = 20;

const STEP_LABELS: Record<string, string> = {
  page: "Открываем страницу фильма",
  player: "Запускаем плеер",
  stream: "Получаем ссылку на видео",
  voice: "Включаем озвучку",
  episode: "Переключаем серию",
  quality: "Проверяем качество",
  fallback: "Ищем фильм на HDRezka",
};

function makeSteps(ids: string[]): LoadStep[] {
  return ids.map((id) => ({ id, label: STEP_LABELS[id] ?? id, state: "pending" }));
}

export function movieSteps(source: SourceId): LoadStep[] {
  return makeSteps(source === "kinogo" ? ["page", "player", "stream", "quality"] : ["page"]);
}

export function voiceSteps(source: SourceId): LoadStep[] {
  return makeSteps(source === "kinogo" ? ["page", "player", "stream", "voice", "quality"] : ["voice"]);
}

export function episodeSteps(source: SourceId): LoadStep[] {
  return makeSteps(source === "kinogo" ? ["page", "player", "stream", "episode", "quality"] : ["episode"]);
}

/** Заголовок плеера: на KinoGo в названии сериала уже есть отметка «(1-5 сезон)». */
export function episodeTitle(title: string, season: string | null, episode: string | null): string {
  const name = title.replace(/\s*\(\d+(\s*-\s*\d+)?\s*сезон\S*\)(\s*\(\d{4}\))?\s*$/i, "");
  const place = [season, episode].filter(Boolean).join(", ");
  return place ? `${name} — ${place}` : name;
}

export const MOVED_EPISODE_NOTICE = "Выбранной серии в этой озвучке нет, открыта ближайшая.";

export function switchedSourceNotice(from: SourceId | null, source: SourceId): string | null {
  return from ? `На ${sourceName(from)} видео нет, открыто с ${sourceName(source)}.` : null;
}

/**
 * Обновить шаг. Новый шаг встаёт перед ещё не начатыми, а ожидавшие шаги выше начавшегося
 * скрываются: раз дошли до этого шага, те не понадобились.
 */
export function applyStep(steps: LoadStep[], id: string, state: StepState): LoadStep[] {
  let next = steps;
  if (!next.some((step) => step.id === id)) {
    const pending = next.findIndex((step) => step.state === "pending");
    const at = pending === -1 ? next.length : pending;
    next = [...next.slice(0, at), ...makeSteps([id]), ...next.slice(at)];
  }
  const index = next.findIndex((step) => step.id === id);
  return next
    .filter((step, position) => position >= index || step.state !== "pending")
    .map((step) => (step.id === id ? { ...step, state } : step));
}

export function failedStep(steps: LoadStep[]): LoadStep | null {
  return steps.find((step) => step.state === "error") ?? null;
}

export function formatElapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export const PRESET_NAMES: Record<Device["preset"], string> = { high: "High", mid: "Mid", low: "Low" };

export function describeDevice(device: Device | null): string {
  if (!device) return "Определяем видеокарту…";
  const name = PRESET_NAMES[device.preset];
  return device.gpu
    ? `Сейчас: ${name}, ${device.gpu}${device.preset === "high" && device.vsr ? ", для фильмов RTX VSR" : ""}`
    : `Сейчас: ${name}. Видеокарту определить не удалось, поэтому выбран щадящий вариант.`;
}

export interface ErrorView {
  title: string;
  hint: string;
  retry: boolean;
}

/** Ошибка потока: у сериала видео может не быть только у этой серии. */
export function describeStreamError(code: ErrorCode, isSeries: boolean): ErrorView {
  if (code === "no_streams" && isSeries) {
    return { title: "Для этой серии видео не найдено", hint: "Выберите другую серию или озвучку.", retry: false };
  }
  return describeError(code);
}

const ERRORS: Record<ErrorCode, ErrorView> = {
  network: {
    title: "Не удалось связаться с сайтом",
    hint: "Проверьте интернет и попробуйте ещё раз.",
    retry: true,
  },
  lampac_off: { title: "Lampac не запущен", hint: "Включите его в настройках и подождите запуска.", retry: false },
  unconfigured: { title: "Вход через Google не настроен", hint: "В этой сборке нет идентификатора Google-клиента.", retry: false },
  not_found: {
    title: "Ничего не нашлось",
    hint: "Попробуйте изменить запрос.",
    retry: false,
  },
  no_streams: {
    title: "Для этой озвучки видео не найдено",
    hint: "Выберите другую озвучку или другой фильм.",
    retry: false,
  },
  no_mpv: {
    title: "Плеер mpv не установлен",
    hint: "Установите его командой: winget install mpv",
    retry: false,
  },
  no_url: {
    title: "В буфере обмена нет ссылки",
    hint: "Скопируйте ссылку на видео и попробуйте снова.",
    retry: false,
  },
  all_mirrors_failed: {
    title: "Видео сейчас не загружается",
    hint: "Повторите попытку или выберите другое качество.",
    retry: true,
  },
  invalid_params: {
    title: "Не получилось выполнить действие",
    hint: "Проверьте введённые данные.",
    retry: false,
  },
  cancelled: {
    title: "Загрузка отменена",
    hint: "Можно попробовать ещё раз.",
    retry: true,
  },
  lower_quality: {
    title: "Запущен запасной вариант видео",
    hint: "Качество может быть ниже выбранного. Настоящее разрешение показано в меню «Качество картинки».",
    retry: false,
  },
  player_failed: {
    title: "Плеер не запустился",
    hint: "Попробуйте ещё раз. Если не поможет, обновите mpv: winget upgrade mpv",
    retry: true,
  },
  backend_down: {
    title: "Приложение потеряло связь с фоновым процессом",
    hint: "Попробуйте ещё раз: он запустится заново.",
    retry: true,
  },
  internal: {
    title: "Что-то пошло не так",
    hint: "Попробуйте ещё раз. Если не поможет, перезапустите приложение.",
    retry: true,
  },
};

export function describeError(code: ErrorCode): ErrorView {
  return ERRORS[code] ?? ERRORS.internal;
}

// --- Мой список ---

export const WATCH_STATUSES: { id: WatchStatus; label: string; color: string }[] = [
  { id: "watching", label: "Смотрю", color: "#3d3475" },
  { id: "planned", label: "Запланировано", color: "#23436f" },
  { id: "completed", label: "Просмотрено", color: "#2c5e2c" },
];

export type WatchFilter = "all" | WatchStatus;

export function watchStatus(id: WatchStatus) {
  return WATCH_STATUSES.find((status) => status.id === id)!;
}

export function filterWatchlist(items: WatchEntry[], filter: WatchFilter): WatchEntry[] {
  return filter === "all" ? items : items.filter((item) => item.status === filter);
}

export function countByStatus(items: WatchEntry[]): Record<WatchFilter, number> {
  const counts: Record<WatchFilter, number> = { all: items.length, watching: 0, planned: 0, completed: 0 };
  for (const item of items) counts[item.status] += 1;
  return counts;
}

/** Адрес страницы KinoGo на текущем зеркале: старое зеркало могло перестать работать. */
export function rebaseUrl(url: string, base: string | null | undefined): string {
  if (!base) return url;
  try {
    const page = new URL(url);
    const mirror = new URL(base);
    page.protocol = mirror.protocol;
    page.host = mirror.host;
    return page.toString();
  } catch {
    return url;
  }
}

/** Отмеченные серии сезона, которые есть в его списке серий. */
export function watchedCount(entry: WatchEntry | null, season: string, episodes: string[]): number {
  const marks = new Set(entry?.episodes[season] ?? []);
  return episodes.filter((id) => marks.has(id)).length;
}

// --- Страница тайтла ---

/** Контраст двух цветов #rrggbb по WCAG 2. */
export function contrastRatio(foreground: string, background: string): number {
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((at) => {
      const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
      return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

export interface Badge {
  label: string;
  tone: "rating" | "plain" | "outline";
}

export interface TitleFacts {
  year: string | null;
  badges: Badge[];
  chips: Fact[];
  genres: string[];
  siteQuality: string | null;
}

const RATING_NAMES: Record<string, string> = { кинопоиск: "КП", imdb: "IMDb" };

/** Факты страницы для бейджей над названием, чипов и жанров (specs/011-movie-page-redesign/data-model.md). */
export function titleFacts(
  info: Record<string, string>,
  kind: "film" | "series",
  episodeCount: number,
  seasonCount = 1,
): TitleFacts {
  const text = (key: string) => info[key]?.trim() || null;
  const badges: Badge[] = [];

  const rating = text("Рейтинги")?.match(/([A-Za-zА-Яа-яЁё]+)\s*:\s*(\d+(?:[.,]\d+)?)/);
  if (rating) {
    const name = RATING_NAMES[rating[1].toLowerCase()] ?? rating[1];
    badges.push({ label: `${name} ${rating[2].replace(",", ".")}`, tone: "rating" });
  }
  badges.push({ label: kind === "series" ? "Сериал" : "Фильм", tone: "plain" });
  const year = yearFrom(info["Год"] ?? "") ?? yearFrom(info["Дата выхода"] ?? "");
  if (year) badges.push({ label: year, tone: "plain" });
  // Общего числа серий источник не сообщает: у многосезонного сериала показывается число сезонов.
  if (kind === "series" && seasonCount > 1) badges.push({ label: `${seasonCount} сез.`, tone: "plain" });
  else if (kind === "series" && episodeCount > 0) badges.push({ label: `${episodeCount} эп.`, tone: "plain" });
  const duration = text("Время");
  if (duration) badges.push({ label: duration, tone: "plain" });
  const age = text("Возраст");
  if (age) badges.push({ label: age.split(/\s/)[0], tone: "outline" });

  const chips: Fact[] = [];
  for (const [key, label] of [["Страна", "Страна"], ["Режиссер", "Режиссёр"], ["Дата выхода", "Дата выхода"]]) {
    const value = text(key);
    if (value) chips.push({ label, value });
  }

  const genres = [...new Set((text("Жанр") ?? "").split(",").map((item) => item.trim()).filter(Boolean))];
  return { year, badges, chips, genres, siteQuality: text("В качестве") };
}

/** Соседние серии в списке сезона для стрелок над встроенным плеером. */
export function neighbourEpisodes(episodes: { id: string }[], current: string): { previous: string | null; next: string | null } {
  const index = episodes.findIndex((item) => item.id === current);
  if (index === -1) return { previous: null, next: null };
  return { previous: episodes[index - 1]?.id ?? null, next: episodes[index + 1]?.id ?? null };
}

/** Инициалы вместо аватара: первые буквы имени (до двух слов), иначе email. */
export function initials(name: string, email: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 0 ? words.slice(0, 2).map((word) => word[0]) : [email.trim()[0] ?? "?"];
  return letters.join("").toUpperCase();
}

/** Когда прошла синхронизация: «только что», «N мин назад», иначе ЧЧ:ММ (или дата). */
export function syncedAgo(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null;
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return null;
  const minutes = Math.floor((now.getTime() - time.getTime()) / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const clock = time.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return time.toDateString() === now.toDateString() ? clock : `${time.toLocaleDateString("ru-RU")} ${clock}`;
}

/** Текст индикатора синхронизации (contracts/sync-protocol.md). */
export function describeSync(state: SyncState | null, now: Date = new Date()): string | null {
  if (!state) return null;
  switch (state.state) {
    case "disabled":
      return "Только на этом устройстве";
    case "idle": {
      if (state.pending) return "Изменения ждут отправки";
      const ago = syncedAgo(state.last_synced_at, now);
      return ago ? `Синхронизировано · ${ago}` : "Синхронизировано";
    }
    case "syncing":
      return "Синхронизация…";
    case "offline":
      return state.pending ? "Нет связи — изменения отправятся позже" : "Нет связи";
    case "auth_required":
      return "Нужно войти заново";
    case "error":
      return state.message ?? "Ошибка синхронизации";
  }
}

/** Можно ли запустить синхронизацию вручную. */
export function canSyncNow(state: SyncState | null): boolean {
  return !!state && ["idle", "offline", "error"].includes(state.state);
}

/** Подпись под блоком аккаунта; null — подписи нет. */
export function describeAccount(state: AccountState | null): string | null {
  if (!state) return null;
  switch (state.state) {
    case "unconfigured":
      return "Вход через Google не настроен в этой сборке.";
    case "pending":
      return "Завершите вход в открывшемся браузере.";
    case "restoring":
      return "Проверка входа…";
    case "offline":
      return state.message ?? "Нет связи с Google — показан последний известный аккаунт.";
    case "expired":
      return state.message ?? "Нужно войти заново.";
    default:
      return state.message;
  }
}

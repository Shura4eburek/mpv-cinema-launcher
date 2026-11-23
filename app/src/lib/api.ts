// Типизированные вызовы протокола (specs/003-app-player-ui/contracts/backend-protocol.md).
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type SourceId = "kinogo" | "hdrezka" | "lampac";

export interface MovieCard {
  title: string;
  url: string;
  poster_url: string | null;
  info: string;
  source: SourceId;
}

export interface Translator {
  id: string;
  name: string;
  active: boolean;
}

export type Streams = Record<string, string[]>;

export interface Episode {
  id: string;
  name: string;
}

/** У KinoGo серии известны только у текущего сезона, у остальных список пуст. */
export interface Season {
  id: string;
  name: string;
  episodes: Episode[];
}

export interface SeriesInfo {
  seasons: Season[];
  season: string;
  episode: string;
  moved: boolean;
}

export interface EpisodeResult {
  streams: Streams;
  translators: Translator[];
  active_translator_id: string | null;
  series: SeriesInfo | null;
}

export interface MovieDetails {
  title: string;
  url: string;
  orig_title: string | null;
  poster_url: string | null;
  description: string;
  info_table: Record<string, string>;
  translators: Translator[];
  active_translator_id: string | null;
  streams: Streams;
  source: SourceId;
  referer: string;
  alternatives: MovieCard[];
  actors: string[];
  related: MovieCard[];
  series: SeriesInfo | null;
  switched_from: SourceId | null;
}

export type MirrorState = "checking" | "ok" | "empty" | "blocked" | "error" | "down";

export interface MirrorReport {
  site: SourceId;
  url: string;
  state: MirrorState;
  http: number | null;
  ms: number | null;
  final_host: string | null;
  server: string | null;
  count: number;
  matches: number;
  first: string | null;
  first_url: string | null;
  detail: string;
}

export interface LampacState {
  state: "off" | "starting" | "running" | "error";
  detail: string;
  available: boolean;
}

export interface LampacEpisode {
  season: number | null;
  number: number;
  name: string;
}

export interface LampacItem {
  voice: string;
  qualities: { label: string; url: string }[];
  subtitles: { label: string; url: string }[];
  episode: LampacEpisode | null;
}

export interface LampacVariants {
  url: string;
  kind: "movie" | "episode";
  voices: { name: string; url: string; active: boolean }[];
  seasons: { name: string; url: string }[];
  items: LampacItem[];
}

export interface LampacSource {
  id: string;
  name: string;
  variants: LampacVariants;
}

export interface TrailerVideo {
  id: string;
  title: string;
}

export interface PlayDetails {
  movie_url: string;
  source: SourceId;
  quality: string | null;
  voice?: string;
  season?: string;
  episode?: string;
  referer?: string;
  progress_id?: string;
  /** Область видео на странице; без неё плеер открывается отдельным окном. */
  wid?: number;
  /** Продолжить с места, где остановился прежний плеер на странице. */
  resume?: boolean;
  /** Тайтл из «Моего списка»: запуск ставит «Смотрю», досмотр отмечает серию. */
  watch?: WatchPlay;
}

export type WatchStatus = "watching" | "planned" | "completed";

/** Тайтл со страницы: по нему backend находит запись (specs/010-watchlist-statuses/contracts). */
export interface WatchTitle {
  title: string;
  orig_title: string | null;
  year: string | null;
  kind: "film" | "series";
  url: string;
  poster_url: string | null;
  source: SourceId | null;
}

export interface WatchEntry extends WatchTitle {
  key: string;
  status: WatchStatus;
  /** Просмотренные серии по сезонам. */
  episodes: Record<string, string[]>;
  updated_at: string;
  deleted_at: null;
}

export interface WatchPlay {
  title: WatchTitle;
  season?: string;
  episode?: string;
  /** Фильм или последняя серия последнего сезона: после досмотра предлагается «Просмотрено». */
  final: boolean;
}

export interface Status {
  mpv_found: boolean;
  upscale_ready: boolean;
}

export type PresetId = "auto" | "high" | "mid" | "low";

export interface Device {
  preset: Exclude<PresetId, "auto">;
  gpu: string | null;
  vsr?: boolean;
}

export interface UserSettings {
  version: number;
  preset: PresetId;
  content: "film" | "anime";
  interpolation: boolean;
  last_translator: string | null;
  last_quality: string | null;
  kinogo_url: string;
  lampac_enabled: boolean;
  embedded_player: boolean;
}

/** Состояние входа через Google (specs/012-google-auth/data-model.md). */
export type AccountStateId = "unconfigured" | "signed_out" | "pending" | "restoring" | "signed_in" | "offline" | "expired";

export interface AccountInfo {
  name: string;
  email: string;
  /** Локальный путь к скачанному аватару; null — показать инициалы. */
  avatar: string | null;
}

export interface AccountState {
  state: AccountStateId;
  account: AccountInfo | null;
  storage_warning: boolean;
  message: string | null;
}

/** Состояние синхронизации списка (specs/013-drive-sync/data-model.md). */
export type SyncStateId = "disabled" | "idle" | "syncing" | "offline" | "auth_required" | "error";

export interface SyncState {
  state: SyncStateId;
  pending: boolean;
  last_synced_at: string | null;
  message: string | null;
}

export type ErrorCode =
  | "network"
  | "not_found"
  | "no_streams"
  | "no_mpv"
  | "no_url"
  | "all_mirrors_failed"
  | "player_failed"
  | "cancelled"
  | "lower_quality"
  | "invalid_params"
  | "backend_down"
  | "lampac_off"
  | "unconfigured"
  | "internal";

export interface ApiError {
  code: ErrorCode;
  message: string;
}

export function errorCode(error: unknown): ErrorCode {
  const code = (error as Partial<ApiError> | null)?.code;
  return code ?? "internal";
}

function call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  return invoke<T>("backend_call", { method, params });
}

export const api = {
  status: () => call<Status>("status"),
  search: (query: string) => call<MovieCard[]>("search", { query }),
  movie: (url: string, source: SourceId, title: string, voice: string | null, progress_id: string) =>
    call<MovieDetails>("movie", { url, source, title, voice, progress_id }),
  translatorStreams: (url: string, translator_id: string, source: SourceId, progress_id: string) =>
    call<Streams>("translator_streams", { url, translator_id, source, progress_id }),
  episode: (url: string, source: SourceId, translator_id: string | null, season: string, episode: string | null, voice_optional: boolean, progress_id: string) =>
    call<EpisodeResult>("episode", { url, source, translator_id, season, episode, voice_optional, progress_id }),
  cancelLoad: (id: string) => call<{ ok: boolean }>("cancel", { id }),
  device: () => call<Device>("device"),
  posterSrc: async (url: string) =>
    convertFileSrc((await call<{ path: string }>("poster", { url })).path),
  play: (title: string, urls: string[], details?: PlayDetails) =>
    call<{ started: boolean }>("play", { title, urls, ...details }),
  playClipboard: (progress_id: string) => call<{ started: boolean }>("play_clipboard", { progress_id }),
  playerStop: () => call<{ ok: boolean }>("player_stop"),
  copyText: (text: string) => call<{ ok: boolean }>("copy_text", { text }),
  lampacState: () => call<LampacState>("lampac_state"),
  lampacSources: (progress_id: string, title: string, original_title: string | null, year: string | null, serial: boolean) =>
    call<{ found: number }>("lampac_sources", { progress_id, title, original_title, year, serial }),
  lampacVariants: (url: string) => call<LampacVariants>("lampac_variants", { url }),
  mirrorCheck: (query: string, id: string) => call<{ total: number }>("mirror_check", { query, id }),
  trailer: (title: string, year: string | null) => call<{ videos: TrailerVideo[] }>("trailer", { title, year }),
  openTrailerSearch: (title: string, year: string | null) =>
    call<{ ok: boolean }>("open_trailer_search", { title, year }),
  getSettings: () => call<UserSettings>("get_settings"),
  setSettings: (changes: Partial<UserSettings>) => call<UserSettings>("set_settings", changes),
  watchlistList: () => call<{ items: WatchEntry[]; warning?: "watchlist_reset" }>("watchlist_list"),
  watchlistGet: (title: WatchTitle) => call<{ entry: WatchEntry | null }>("watchlist_get", { title }),
  watchlistSetStatus: (title: WatchTitle, status: WatchStatus) =>
    call<{ entry: WatchEntry }>("watchlist_set_status", { title, status }),
  watchlistRemove: (title: WatchTitle) => call<{ entry: null }>("watchlist_remove", { title }),
  watchlistSetEpisode: (title: WatchTitle, season: string, episode: string, watched: boolean) =>
    call<{ entry: WatchEntry | null }>("watchlist_set_episode", { title, season, episode, watched }),
  watchlistResolve: (title: WatchTitle) => call<{ entry: WatchEntry | null; key: string }>("watchlist_resolve", { title }),
  accountGet: () => call<AccountState>("account_get"),
  accountSignIn: () => call<AccountState>("account_sign_in"),
  accountCancel: () => call<AccountState>("account_cancel"),
  accountSignOut: () => call<AccountState>("account_sign_out"),
  syncGet: () => call<SyncState>("sync_get"),
  syncNow: () => call<SyncState>("sync_now"),
};

export interface BackendEvent {
  event:
    | "playback_started"
    | "playback_finished"
    | "playback_failed"
    | "playback_fallback"
    | "player_fullscreen"
    | "upscale_ready"
    | "backend_down"
    | "load_progress"
    | "mirror_result"
    | "lampac_state"
    | "lampac_source"
    | "watchlist_changed"
    | "watch_completed"
    | "account_changed"
    | "sync_changed"
    | "watchlist_reloaded";
  data: {
    code?: number | ErrorCode;
    ready?: boolean;
    on?: boolean;
    id?: string;
    step?: string;
    state?: "running" | "done" | "error";
    mirror?: MirrorReport;
    lampac?: LampacState;
    source?: LampacSource;
    entry?: WatchEntry | null;
    key?: string;
    title?: WatchTitle;
    final?: boolean;
  } | null;
}

/** У account_changed данные — AccountState целиком. */
export function accountFromEvent(event: BackendEvent): AccountState | null {
  return event.event === "account_changed" && event.data ? (event.data as unknown as AccountState) : null;
}

/** У sync_changed данные — SyncState целиком. */
export function syncFromEvent(event: BackendEvent): SyncState | null {
  return event.event === "sync_changed" && event.data ? (event.data as unknown as SyncState) : null;
}

export function onBackendEvent(handler: (event: BackendEvent) => void): Promise<UnlistenFn> {
  return listen<BackendEvent>("backend-event", (message) => handler(message.payload));
}

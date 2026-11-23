<script lang="ts">
  import { onMount, tick } from "svelte";
  import { api, errorCode, onBackendEvent, type Device, type ErrorCode, type LampacState, type MovieCard, type PlayDetails, type UserSettings, type WatchTitle } from "./lib/api";
  import { describeError } from "./lib/logic";
  import PlayerOpening from "./components/PlayerOpening.svelte";
  import Trailer from "./components/Trailer.svelte";
  import Home from "./screens/Home.svelte";
  import MirrorCheck from "./screens/MirrorCheck.svelte";
  import Movie from "./screens/Movie.svelte";
  import Results from "./screens/Results.svelte";
  import Settings from "./screens/Settings.svelte";
  import Watchlist from "./screens/Watchlist.svelte";

  type Screen = "home" | "results" | "movie" | "watchlist";

  let screen = $state<Screen>("home");
  let showSettings = $state(false);
  let showMirrors = $state(false);
  let query = $state("");
  let draft = $state("");
  let movies = $state<MovieCard[]>([]);
  let movie = $state<MovieCard | null>(null);
  let searching = $state(false);
  let searchError = $state<ErrorCode | null>(null);
  let settings = $state<UserSettings | null>(null);
  let upscaleReady = $state<boolean | null>(null);
  let device = $state<Device | null>(null);
  let lampac = $state<LampacState | null>(null);
  let notice = $state<{ code: ErrorCode; retry?: () => void } | null>(null);

  let scroller: HTMLElement;
  let resultsScroll = 0;
  let searchRequest = 0;
  let lastPlayback: (() => void) | null = null;
  let openingId = $state<string | null>(null);
  let trailer = $state<{ title: string; year: string | null } | null>(null);
  let searchActive = $state(false);
  let searchInput = $state<HTMLInputElement>();
  let movieFrom = $state<Screen>("results");
  // Досмотрен фильм или последняя серия: предложение отметить «Просмотрено».
  let finishedTitle = $state<WatchTitle | null>(null);
  let listReset = $state(false);

  const noticeView = $derived(notice ? describeError(notice.code) : null);

  async function runSearch(text: string) {
    const current = ++searchRequest;
    notice = null;
    query = text;
    draft = text;
    movies = [];
    searchError = null;
    searching = true;
    showSettings = false;
    showMirrors = false;
    screen = "results";
    resultsScroll = 0;
    try {
      const found = await api.search(text);
      if (current === searchRequest) movies = found;
    } catch (error) {
      if (current === searchRequest) searchError = errorCode(error);
    } finally {
      if (current === searchRequest) searching = false;
    }
  }

  function submitSearch(event: SubmitEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    runSearch(draft.trim());
    searchInput?.blur();
  }

  // Отмена поиска: Esc или щелчок мимо поля. После запроса query и draft уже совпадают.
  function closeSearch() {
    searchActive = false;
    draft = query;
  }

  function searchKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") searchInput?.blur();
  }

  // Поле с середины главной плавно переходит в шапку.
  function searchFromHome(text: string) {
    if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      runSearch(text);
      return;
    }
    document.startViewTransition(async () => {
      runSearch(text);
      await tick();
    });
  }

  function openMovie(card: MovieCard) {
    if (screen === "results") resultsScroll = scroller.scrollTop;
    if (screen !== "movie") movieFrom = screen;
    movie = card;
    screen = "movie";
    scroller.scrollTop = 0;
  }

  async function backToResults() {
    screen = movieFrom === "watchlist" ? "watchlist" : "results";
    if (screen === "watchlist") return;
    await tick();
    scroller.scrollTop = resultsScroll;
  }

  async function play(title: string, urls: string[], details: PlayDetails) {
    notice = null;
    if (details.wid) {
      // Плеер на странице: ход запуска показывает сама страница, а повтор начинается с её кнопки.
      lastPlayback = null;
      try {
        await api.play(title, urls, details);
      } catch (error) {
        if (errorCode(error) !== "cancelled") notice = { code: errorCode(error) };
        throw error;
      }
      return;
    }
    const retry = () => play(title, urls, details);
    lastPlayback = retry;
    // Экран снимается событием от плеера, а не ответом на запрос: mpv ещё загружает фильм.
    const id = crypto.randomUUID();
    openingId = id;
    try {
      await api.play(title, urls, { ...details, progress_id: id });
    } catch (error) {
      if (openingId === id) openingId = null;
      if (errorCode(error) === "cancelled") return;
      notice = { code: errorCode(error), retry };
    }
  }

  function cancelOpening() {
    const id = openingId;
    openingId = null;
    if (id) api.cancelLoad(id).catch(() => {});
  }

  async function playClipboard() {
    notice = null;
    lastPlayback = playClipboard;
    const id = crypto.randomUUID();
    openingId = id;
    try {
      await api.playClipboard(id);
    } catch (error) {
      if (openingId === id) openingId = null;
      if (errorCode(error) === "cancelled") return;
      notice = { code: errorCode(error), retry: playClipboard };
    }
  }

  function openWatchlist() {
    showSettings = false;
    showMirrors = false;
    screen = "watchlist";
    scroller.scrollTop = 0;
  }

  async function markFinished() {
    const title = finishedTitle;
    finishedTitle = null;
    if (!title) return;
    try {
      await api.watchlistSetStatus(title, "completed");
    } catch (error) {
      notice = { code: errorCode(error) };
    }
  }

  async function changeSettings(changes: Partial<UserSettings>) {
    if (settings) settings = { ...settings, ...changes };
    try {
      settings = await api.setSettings(changes);
    } catch (error) {
      notice = { code: errorCode(error) };
      settings = await api.getSettings().catch(() => settings);
    }
  }

  async function connect() {
    notice = null;
    try {
      const [status, saved] = await Promise.all([api.status(), api.getSettings()]);
      settings = saved;
      upscaleReady = status.upscale_ready;
      if (!status.mpv_found) notice = { code: "no_mpv" };
      lampac = await api.lampacState();
      // Вход через Google восстанавливается в фоне сразу после запуска.
      api.accountGet().catch(() => {});
      device = await api.device();
    } catch (error) {
      notice = { code: errorCode(error), retry: connect };
    }
  }

  onMount(() => {
    connect();
    const stop = onBackendEvent(({ event, data }) => {
      const ended = event === "playback_started" || event === "playback_finished" || event === "playback_failed";
      if ((ended && data?.id === openingId) || event === "backend_down") openingId = null;
      if (event === "upscale_ready") upscaleReady = data?.ready ?? false;
      if (event === "lampac_state" && data?.lampac) lampac = data.lampac;
      if (event === "playback_fallback") notice = { code: (data?.code as ErrorCode) ?? "lower_quality" };
      if (event === "playback_failed") {
        notice = { code: (data?.code as ErrorCode) ?? "internal", retry: lastPlayback ?? undefined };
      }
      if (event === "backend_down") notice = { code: "backend_down", retry: connect };
      if (event === "watch_completed" && data?.final && data.title) finishedTitle = data.title;
    });
    return () => {
      stop.then((unlisten) => unlisten());
    };
  });
</script>

{#if openingId}
  <PlayerOpening oncancel={cancelOpening} />
{/if}

{#if trailer}
  <Trailer title={trailer.title} year={trailer.year} onclose={() => (trailer = null)} />
{/if}

<div class="app" inert={openingId !== null || trailer !== null}>
  <header>
    <button class="logo" onclick={() => { showSettings = false; showMirrors = false; screen = "home"; }}>
      <span class="mark">
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.9 3 12.1 8 4.9 13z" /></svg>
      </span>
      MPV Cinema
    </button>

    {#if screen !== "home" || showSettings || showMirrors}
      <form class:active={searchActive} onsubmit={submitSearch}>
        <input
          bind:this={searchInput}
          bind:value={draft}
          placeholder="Поиск фильмов"
          aria-label="Поиск фильмов"
          onfocus={() => (searchActive = true)}
          onblur={closeSearch}
          onkeydown={searchKeydown}
        />
      </form>
    {/if}

    <div class="tools">
      <button class="btn ghost" aria-pressed={screen === "watchlist" && !showSettings && !showMirrors} onclick={openWatchlist}>Мой список</button>
      <button class="btn ghost" onclick={playClipboard}>Открыть ссылку из буфера</button>
      <button class="btn ghost" aria-pressed={showSettings} onclick={() => { showSettings = !showSettings; showMirrors = false; }}>Настройки</button>
    </div>
  </header>

  <div class="body">
  <div class="scrim" class:active={searchActive} aria-hidden="true"></div>

  {#if notice && noticeView}
    <div class="notice" role="alert">
      <div><strong>{noticeView.title}</strong> <span>{noticeView.hint}</span></div>
      {#if notice.retry && noticeView.retry}
        <button class="btn" onclick={notice.retry}>Повторить</button>
      {/if}
      <button class="btn ghost" aria-label="Закрыть сообщение" onclick={() => (notice = null)}>✕</button>
    </div>
  {/if}

  {#if finishedTitle}
    <div class="notice ask" role="status">
      <div><strong>{finishedTitle.title}</strong> <span>досмотрен. Отметить как просмотренное?</span></div>
      <button class="btn primary" onclick={markFinished}>Да</button>
      <button class="btn ghost" onclick={() => (finishedTitle = null)}>Нет</button>
    </div>
  {/if}

  {#if listReset}
    <div class="notice" role="alert">
      <div><strong>Файл «Моего списка» был повреждён.</strong> <span>Список начат заново, копия старого файла сохранена рядом с ним.</span></div>
      <button class="btn ghost" aria-label="Закрыть сообщение" onclick={() => (listReset = false)}>✕</button>
    </div>
  {/if}

  <main bind:this={scroller}>
    {#if showSettings && settings}
      <Settings
        {settings}
        {upscaleReady}
        {device}
        {lampac}
        onchange={changeSettings}
        onclose={() => (showSettings = false)}
        onmirrors={() => {
          showSettings = false;
          showMirrors = true;
        }}
      />
    {/if}
    {#if showMirrors}
      <MirrorCheck onclose={() => { showMirrors = false; showSettings = true; }} />
    {/if}
    <!-- Экран остаётся открытым под настройками: загрузка и запуск фильма не прерываются. -->
    <div class="screen" hidden={(showSettings && !!settings) || showMirrors}>
    {#if screen === "home"}
      <Home onsearch={searchFromHome} />
    {:else if screen === "results"}
      <Results {query} {movies} loading={searching} error={searchError} onopen={openMovie} onretry={() => runSearch(query)} />
    {:else if screen === "watchlist"}
      <Watchlist kinogoUrl={settings?.kinogo_url ?? null} onopen={openMovie} onreset={() => (listReset = true)} onsettings={() => { showMirrors = false; showSettings = true; }} />
    {:else if screen === "movie" && movie}
      {#key movie.url}
        <Movie card={movie} {settings} stopPlayer={showSettings || showMirrors || trailer !== null} hidePlayer={searchActive} onback={backToResults} backLabel={movieFrom === "watchlist" ? "Назад к списку" : "Назад к результатам"} onsettings={changeSettings} onplay={play} onopen={openMovie} ontrailer={(title, year) => (trailer = { title, year })} />
      {/key}
    {/if}
    </div>
  </main>
  </div>
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  header {
    position: relative;
    z-index: 2;
    display: grid;
    grid-template-columns: minmax(max-content, 1fr) minmax(120px, 560px) minmax(max-content, 1fr);
    align-items: center;
    gap: 16px;
    padding: 12px 24px;
    border-bottom: 1px solid var(--surface);
  }

  .body {
    position: relative;
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
  }

  .scrim {
    position: absolute;
    inset: 0;
    z-index: 5;
    background: rgb(0 0 0 / 78%);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s var(--ease);
  }

  .scrim.active {
    opacity: 1;
    pointer-events: auto;
  }

  .logo {
    display: flex;
    align-items: center;
    justify-self: start;
    gap: 9px;
    padding: 0;
    border: 0;
    background: none;
    font-size: 16px;
    font-weight: 700;
    white-space: nowrap;
    cursor: pointer;
  }

  .mark {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border-radius: 8px;
    background: var(--accent);
    color: #fff;
  }

  .mark svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }

  form {
    grid-column: 2;
    justify-self: center;
    width: 72%;
    min-width: 120px;
    view-transition-name: search-field;
    transition: width 0.25s var(--ease);
  }

  form.active {
    width: 100%;
  }

  input {
    width: 100%;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--input);
  }

  input:focus {
    border-color: var(--accent);
    outline: none;
  }

  .tools {
    grid-column: 3;
    display: flex;
    justify-self: end;
  }

  .tools [aria-pressed="true"] {
    color: var(--text);
    background: var(--surface-2);
  }

  .notice {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 24px;
    background: rgb(244 63 94 / 13%);
    animation: appear 0.2s var(--ease);
  }

  .notice.ask {
    background: rgb(44 94 44 / 22%);
  }

  .notice > div {
    flex: 1;
    min-width: 0;
    user-select: text;
  }

  .notice span {
    color: var(--body);
  }

  .screen {
    height: 100%;
  }

  .screen[hidden] {
    display: none;
  }

  main {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 24px;
  }

  @media (max-width: 860px) {
    .tools .btn {
      padding: 9px 10px;
    }
  }
</style>

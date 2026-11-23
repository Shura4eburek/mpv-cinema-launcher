<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import { api, errorCode, onBackendEvent, type ErrorCode, type MovieCard, type MovieDetails, type PlayDetails, type SeriesInfo, type Streams, type UserSettings, type WatchEntry, type WatchStatus, type WatchTitle } from "../lib/api";
  import { MOVED_EPISODE_NOTICE, applyStep, bestQuality, describeError, describeStreamError, episodeSteps, episodeTitle, failedStep, looksLikeSeries, movieSteps, sortQualities, sourceName, neighbourEpisodes, switchedSourceNotice, titleFacts, voiceSteps, watchedCount, yearFrom, type LoadStep, type StepState } from "../lib/logic";
  import { surface, type SurfaceRect } from "../lib/surface";
  import EpisodePanel from "../components/EpisodePanel.svelte";
  import FactBadges from "../components/FactBadges.svelte";
  import PlayerBar from "../components/PlayerBar.svelte";
  import LampacSources from "../components/LampacSources.svelte";
  import LoadProgress from "../components/LoadProgress.svelte";
  import Poster from "../components/Poster.svelte";
  import PosterGrid from "../components/PosterGrid.svelte";
  import StatusMessage from "../components/StatusMessage.svelte";
  import StatusPicker from "../components/StatusPicker.svelte";
  import VoicePanel from "../components/VoicePanel.svelte";

  interface Props {
    card: MovieCard;
    settings: UserSettings | null;
    /** Настройки или трейлер открыты: плеер на странице останавливается. */
    stopPlayer: boolean;
    /** Страница затемнена поиском: видео не должно быть поверх затемнения. */
    hidePlayer: boolean;
    onback: () => void;
    backLabel?: string;
    onsettings: (changes: Partial<UserSettings>) => void;
    onplay: (title: string, urls: string[], details: PlayDetails) => Promise<void>;
    onopen: (card: MovieCard) => void;
    ontrailer: (title: string, year: string | null) => void;
  }

  let { card, settings, stopPlayer, hidePlayer, onback, backLabel = "Назад к результатам", onsettings, onplay, onopen, ontrailer }: Props = $props();

  let backdrop = $state<string | null>(null);

  let details = $state<MovieDetails | null>(null);
  let streams = $state<Streams>({});
  let translator = $state("");
  // Выбор зрителя виден сразу, а списки series меняются только с ответом сайта.
  let series = $state<SeriesInfo | null>(null);
  let season = $state("");
  let episode = $state("");
  let quality = $state<string | null>(null);
  /** Высота колонки с постером и кнопками: панель «Эпизоды» рядом с ней той же высоты. */
  let sideHeight = $state(0);
  let loadError = $state<ErrorCode | null>(null);
  let streamError = $state<ErrorCode | null>(null);
  let loadingStreams = $state(false);
  let copied = $state(false);
  let starting = $state(false);
  let steps = $state<LoadStep[]>([]);
  let elapsed = $state(0);
  // Плеер на странице.
  let watching = $state(false);
  let videoReady = $state(false);
  let fullscreen = $state(false);
  let playerBox = $state<HTMLElement>();
  let playId: string | null = null;
  let destroyed = false;
  // Выбор, сделанный во время запуска: применяется, когда запуск закончится.
  let pendingRestart: { resume: boolean } | null = null;
  let requestId = 0;
  let previousTranslator = "";
  let previousSeason = "";
  let previousEpisode = "";
  let progressId: string | null = null;
  let startedAt = 0;
  let ticker: ReturnType<typeof setInterval> | undefined;
  // Мой список.
  let entry = $state<WatchEntry | null>(null);
  let savingStatus = $state(false);
  let watchError = $state<ErrorCode | null>(null);
  let listedUrl: string | null = null;
  // Число серий по сезонам у озвучек, уже загруженных на этой странице: список озвучек сайта его не сообщает.
  let voiceEpisodes = $state<Record<string, Record<string, number>>>({});

  function beginProgress(initial: LoadStep[]): string {
    stopProgress();
    const id = crypto.randomUUID();
    progressId = id;
    steps = initial;
    elapsed = 0;
    startedAt = Date.now();
    ticker = setInterval(() => (elapsed = (Date.now() - startedAt) / 1000), 1000);
    return id;
  }

  function stopProgress() {
    clearInterval(ticker);
    ticker = undefined;
    progressId = null;
  }

  function cancelProgress() {
    if (progressId) api.cancelLoad(progressId).catch(() => {});
    stopProgress();
  }

  function cancelLoad() {
    cancelProgress();
    requestId++;
    // Потоки остались от прежней озвучки, поэтому и в списке должна быть она.
    if (loadingStreams) {
      translator = previousTranslator;
      season = previousSeason;
      episode = previousEpisode;
    }
    loadingStreams = false;
    starting = false;
    if (!details) loadError = "cancelled";
    else if (Object.keys(streams).length === 0) streamError = "cancelled";
  }

  function retryLoad() {
    cancelProgress();
    load();
  }

  onMount(() => {
    const stop = onBackendEvent(({ event, data }) => {
      if (event === "load_progress" && data?.id === progressId && data.step && data.state) {
        steps = applyStep(steps, data.step, data.state as StepState);
      }
      if (playId && data?.id === playId) {
        if (event === "playback_started") videoReady = true;
        if (event === "playback_finished" || event === "playback_failed") closePlayer();
        if (event === "player_fullscreen") setFullscreen(data.on === true);
      }
      if (event === "watchlist_changed" || event === "watchlist_reloaded") refreshEntry();
    });
    load();
    return () => {
      stop.then((unlisten) => unlisten());
    };
  });

  // Начатый запуск фильма не отменяется при уходе со страницы: зритель уже нажал «Смотреть».
  onDestroy(() => {
    destroyed = true;
    stopPrefetch();
    if (starting) stopProgress();
    else cancelProgress();
    if (watching) stopWatching();
  });

  function setFullscreen(on: boolean) {
    // mpv сообщает начальное значение при запуске: это не команда, а фокус трогать нельзя.
    if (on === fullscreen) return;
    fullscreen = on;
    surface.fullscreen(on).catch(() => {});
  }

  function closePlayer() {
    playId = null;
    watching = false;
    videoReady = false;
    if (fullscreen) setFullscreen(false);
    surface.hide().catch(() => {});
  }

  function stopWatching() {
    // Ссылка могла ещё обновляться: без отмены mpv запустился бы уже без области на странице.
    if (playId) api.cancelLoad(playId).catch(() => {});
    api.playerStop().catch(() => {});
    closePlayer();
  }

  function videoRect(box: HTMLElement): SurfaceRect {
    const rect = box.getBoundingClientRect();
    const page = box.closest("main")?.getBoundingClientRect().top ?? 0;
    return { x: rect.left, y: rect.top, width: rect.width, height: rect.height, clip_top: page };
  }

  // Видео это окно поверх страницы: на каждом кадре оно следует за своим местом на странице.
  $effect(() => {
    const box = playerBox;
    if (!watching || !box) return;
    if (!videoReady || hidePlayer) {
      surface.hide().catch(() => {});
      return;
    }
    if (fullscreen) return;

    let frame = 0;
    let last = "";
    let busy = false;
    let stopped = false;
    const follow = () => {
      if (stopped) return;
      frame = requestAnimationFrame(follow);
      if (busy) return;
      const rect = videoRect(box);
      const text = JSON.stringify(rect);
      if (text === last) return;
      last = text;
      busy = true;
      surface.move(rect).catch(() => {}).finally(() => (busy = false));
    };
    surface.show(videoRect(box)).catch(() => {}).finally(() => (frame = requestAnimationFrame(follow)));
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
    };
  });

  $effect(() => {
    if (stopPlayer && watching) stopWatching();
  });

  const posterUrl = $derived(details?.poster_url ?? card.poster_url);

  $effect(() => {
    const requested = posterUrl;
    let cancelled = false;
    if (requested) {
      api
        .posterSrc(requested)
        .then((value) => {
          if (!cancelled) backdrop = value;
        })
        // Фон необязателен: без него остаётся обычный цвет окна.
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  });

  function openTrailer() {
    ontrailer(details?.title ?? card.title, filmYear);
  }

  const qualities = $derived(sortQualities(Object.keys(streams)));
  const currentSeason = $derived(series?.seasons.find((item) => item.id === season) ?? null);
  const currentEpisode = $derived(currentSeason?.episodes.find((item) => item.id === episode) ?? null);
  // Тип по адресу, названию и жанру одинаков при каждом открытии: от него зависит ключ записи в списке.
  const titleKind = $derived<"film" | "series">(
    details && (details.series !== null || looksLikeSeries(details.url, details.title, details.info_table["Жанр"] ?? ""))
      ? "series"
      : "film",
  );
  const pageFacts = $derived(
    titleFacts(details?.info_table ?? {}, titleKind, currentSeason?.episodes.length ?? 0, series?.seasons.length ?? 1),
  );
  const filmYear = $derived(pageFacts.year ?? yearFrom(card.info) ?? yearFrom(card.title));
  const urls = $derived(quality ? (streams[quality] ?? []) : []);
  /** У фильма в третьей колонке — озвучки, у сериала — эпизоды. */
  const voicePanel = $derived(series === null && details !== null && !details.alternatives.length && details.translators.length > 0);

  const watchTitle = $derived<WatchTitle | null>(
    details
      ? {
          title: details.title,
          orig_title: details.orig_title,
          year: filmYear,
          kind: titleKind,
          url: details.url,
          poster_url: details.poster_url?.startsWith("http") ? details.poster_url : null,
          source: details.source,
        }
      : null,
  );
  const neighbours = $derived(neighbourEpisodes(currentSeason?.episodes ?? [], episode));
  // После последней серии сезона «›» открывает следующий сезон: его серии KinoGo сообщит только при загрузке.
  const nextSeason = $derived.by(() => {
    if (!series || neighbours.next) return null;
    const index = series.seasons.findIndex((item) => item.id === season);
    return index === -1 ? null : (series.seasons[index + 1] ?? null);
  });

  function nextEpisode() {
    if (neighbours.next) loadEpisode(null, season, neighbours.next);
    else if (nextSeason) loadEpisode(null, nextSeason.id, null);
  }
  const playerLabel = $derived.by(() => {
    if (!series) return details?.title ?? card.title;
    const name = currentEpisode?.name ?? "";
    const number = name.match(/^(\d+)\s*серия$/i)?.[1];
    return number ? `Серия ${number}` : name || "Серия";
  });
  const seasonEpisodes = $derived(currentSeason?.episodes.map((item) => item.id) ?? []);
  const watchedInSeason = $derived(watchedCount(entry, season, seasonEpisodes));
  const lastSeason = $derived(series?.seasons[series.seasons.length - 1] ?? null);
  const finalEpisode = $derived(
    !series || (lastSeason?.id === season && lastSeason.episodes[lastSeason.episodes.length - 1]?.id === episode),
  );

  $effect(() => {
    const count = currentSeason?.episodes.length ?? 0;
    if (!series || loadingStreams || !translator || !count) return;
    if (voiceEpisodes[translator]?.[season] === count) return;
    voiceEpisodes = { ...voiceEpisodes, [translator]: { ...voiceEpisodes[translator], [season]: count } };
  });
  // Число серий у остальных озвучек подгружается в фоне, по одной, когда страница простаивает.
  // Ответы backend кеширует: переключение на уже подгруженную озвучку потом мгновенное.
  let prefetchRun = 0;
  let prefetchId: string | null = null;

  function stopPrefetch() {
    prefetchRun++;
    if (prefetchId) api.cancelLoad(prefetchId).catch(() => {});
    prefetchId = null;
  }

  async function prefetchVoices(run: number, movie: MovieDetails, forSeason: string, forEpisode: string) {
    for (const voice of movie.translators) {
      if (run !== prefetchRun || destroyed) return;
      if (voiceEpisodes[voice.name]?.[forSeason] !== undefined) continue;
      const id = crypto.randomUUID();
      prefetchId = id;
      try {
        const next = await api.episode(movie.url, movie.source, voice.id, forSeason, forEpisode || null, false, id);
        const found = next.series?.seasons.find((item) => item.id === forSeason);
        if (run === prefetchRun && found?.episodes.length) {
          voiceEpisodes = { ...voiceEpisodes, [voice.name]: { ...voiceEpisodes[voice.name], [forSeason]: found.episodes.length } };
        }
      } catch {
        // У озвучки нет этого сезона или сайт не ответил: метки просто не будет.
      } finally {
        if (prefetchId === id) prefetchId = null;
      }
    }
  }

  $effect(() => {
    const movie = details;
    const forSeason = season;
    const forEpisode = episode;
    if (!movie || !series || loadingStreams || starting || movie.translators.length < 2) return;
    const run = ++prefetchRun;
    // Пауза: зритель может сразу выбрать другую серию, фоновая загрузка не должна ему мешать.
    const timer = setTimeout(() => prefetchVoices(run, movie, forSeason, forEpisode), 1500);
    return () => {
      clearTimeout(timer);
      stopPrefetch();
    };
  });

  const seasonVoiceEpisodes = $derived(
    Object.fromEntries(
      Object.entries(voiceEpisodes)
        .filter(([, seasons]) => seasons[season] !== undefined)
        .map(([name, seasons]) => [name, seasons[season]]),
    ),
  );

  // Страница загружена: статус из списка, затем в фоне поиск id IMDb.
  $effect(() => {
    const title = watchTitle;
    if (!title || listedUrl === title.url) return;
    listedUrl = title.url;
    api
      .watchlistGet(title)
      .then((result) => {
        if (watchTitle?.url === title.url) entry = result.entry;
        return api.watchlistResolve(title);
      })
      .then((result) => {
        if (watchTitle?.url === title.url && result.entry) entry = result.entry;
      })
      .catch(() => {});
  });

  async function refreshEntry() {
    const title = watchTitle;
    if (!title) return;
    try {
      const result = await api.watchlistGet(title);
      if (watchTitle?.url === title.url) entry = result.entry;
    } catch {
      // Статус обновится при следующем открытии страницы.
    }
  }

  async function changeStatus(next: WatchStatus | null) {
    const title = watchTitle;
    if (!title) return;
    savingStatus = true;
    watchError = null;
    try {
      if (next) {
        entry = (await api.watchlistSetStatus(title, next)).entry;
      } else {
        await api.watchlistRemove(title);
        entry = null;
      }
    } catch (error) {
      watchError = errorCode(error);
    } finally {
      savingStatus = false;
    }
  }

  async function toggleEpisode(id: string, watched: boolean) {
    const title = watchTitle;
    if (!title || !season) return;
    watchError = null;
    try {
      entry = (await api.watchlistSetEpisode(title, season, id, watched)).entry;
    } catch (error) {
      watchError = errorCode(error);
    }
  }

  // Источники Lampac не знают серию: запуск только ставит «Смотрю», у фильма досмотр предлагает «Просмотрено».
  function playLampac(title: string, urls: string[], playDetails: PlayDetails) {
    const watch = watchTitle ? { title: watchTitle, final: watchTitle.kind === "film" } : undefined;
    return onplay(title, urls, { ...playDetails, watch });
  }
  const switchedNotice = $derived(details ? switchedSourceNotice(details.switched_from, details.source) : null);

  function showSeries(next: SeriesInfo | null) {
    series = next;
    season = next?.season ?? "";
    episode = next?.episode ?? "";
  }

  function applyStreams(next: Streams) {
    streams = next;
    quality = bestQuality(Object.keys(next), settings?.last_quality ?? null);
  }

  async function loadTranslator(name: string, id: string, remember = false) {
    const current = ++requestId;
    const url = details!.url;
    previousTranslator = translator;
    translator = name;
    loadingStreams = true;
    streamError = null;
    const progress = beginProgress(voiceSteps(details!.source));
    try {
      const next = await api.translatorStreams(url, id, details!.source, progress);
      if (current === requestId) {
        applyStreams(next);
        // Запоминаем только озвучку, которая действительно загрузилась.
        if (remember) onsettings({ last_translator: name });
        if (watching) play(true);
      }
    } catch (error) {
      if (current === requestId) {
        applyStreams({});
        streamError = errorCode(error);
      }
    } finally {
      if (current === requestId) {
        loadingStreams = false;
        stopProgress();
      }
    }
  }

  async function loadEpisode(voice: { name: string; id: string } | null, nextSeason: string, nextEpisode: string | null, remember = false) {
    const current = ++requestId;
    const movie = details!;
    previousTranslator = translator;
    previousSeason = season;
    previousEpisode = episode;
    if (voice) translator = voice.name;
    season = nextSeason;
    // До ответа сайта серия нового сезона не известна.
    episode = nextEpisode ?? series?.seasons.find((item) => item.id === nextSeason)?.episodes[0]?.id ?? "";
    loadingStreams = true;
    streamError = null;
    const progress = beginProgress(episodeSteps(movie.source));
    try {
      const translatorId = voice?.id ?? movie.active_translator_id;
      const next = await api.episode(movie.url, movie.source, translatorId, nextSeason, nextEpisode, voice === null, progress);
      if (current !== requestId) return;
      applyStreams(next.streams);
      if (next.series) showSeries(next.series);
      if (next.translators.length) movie.translators = next.translators;
      movie.active_translator_id = next.active_translator_id;
      translator = next.translators.find((item) => item.active)?.name ?? translator;
      if (remember && voice) onsettings({ last_translator: voice.name });
      // Та же серия в другой озвучке продолжается с того же места, другая серия начинается сначала.
      if (watching) play(voice !== null && !next.series?.moved);
    } catch (error) {
      if (current === requestId) {
        // Серии сезона на KinoGo приходят только с ответом: без них выбирать нечего, остаётся прежняя серия.
        if (series?.seasons.find((item) => item.id === season)?.episodes.length) {
          applyStreams({});
        } else {
          translator = previousTranslator;
          season = previousSeason;
          episode = previousEpisode;
        }
        streamError = errorCode(error);
      }
    } finally {
      if (current === requestId) {
        loadingStreams = false;
        stopProgress();
      }
    }
  }

  function retryStreams() {
    // Озвучка могла не загрузиться: повторяется выбор зрителя, а не прежняя озвучка.
    const voice = details?.translators.find((item) => item.name === translator) ?? null;
    if (series) loadEpisode(voice, season, episode || null);
    else load();
  }

  async function load() {
    const current = ++requestId;
    const url = card.url;
    // Места для плеера больше нет, а окно видео само со страницы не уйдёт.
    if (watching) stopWatching();
    details = null;
    showSeries(null);
    loadError = null;
    streamError = null;
    const progress = beginProgress(movieSteps(card.source));
    try {
      const movie = await api.movie(url, card.source, card.title, settings?.last_translator ?? null, progress);
      if (current !== requestId) return;
      stopProgress();
      details = movie;
      translator = movie.translators.find((t) => t.active)?.name ?? movie.translators[0]?.name ?? "";
      applyStreams(movie.streams);
      showSeries(movie.series);

      // Без видео на KinoGo предлагаются фильмы запасного источника.
      if (movie.alternatives.length > 0) return;

      // Сохранённую озвучку KinoGo уже применил backend при открытии плеера.
      if (movie.source === "kinogo") {
        if (Object.keys(movie.streams).length === 0) streamError = "no_streams";
        return;
      }

      const saved = movie.translators.find((t) => t.name === settings?.last_translator);
      const active = movie.translators.find((t) => t.name === translator);
      if (saved && saved.name !== translator) {
        if (movie.series) await loadEpisode(saved, movie.series.season, movie.series.episode);
        else await loadTranslator(saved.name, saved.id);
      } else if (Object.keys(movie.streams).length === 0) {
        // На части страниц ссылок нет в HTML: они приходят только по запросу озвучки.
        if (movie.series) await loadEpisode(active ?? null, movie.series.season, movie.series.episode);
        else if (active) await loadTranslator(active.name, active.id);
        else streamError = "no_streams";
      }
    } catch (error) {
      if (current === requestId) {
        stopProgress();
        loadError = errorCode(error);
      }
    }
  }

  function chooseTranslator(name: string) {
    const found = details?.translators.find((t) => t.name === name);
    if (!found) return;
    // Серия остаётся прежней: если её нет в этой озвучке, backend выберет ближайшую.
    if (series) loadEpisode(found, season, episode || null, true);
    else loadTranslator(name, found.id, true);
  }

  function chooseQuality(label: string) {
    quality = label;
    onsettings({ last_quality: label });
    if (watching) play(true);
  }

  async function copy() {
    await api.copyText(urls[0]);
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }

  async function play(resume: boolean | MouseEvent = false) {
    const continuing = resume === true;
    if (starting) {
      pendingRestart = { resume: continuing && (pendingRestart?.resume ?? true) };
      return;
    }
    if (urls.length === 0) {
      // Для нового выбора видео нет: прежний плеер показывал бы не то, что выбрано.
      if (watching) stopWatching();
      return;
    }
    const movie = details!;
    starting = true;
    const wid = settings?.embedded_player ? await surface.create().catch(() => null) : null;
    // Пока шло создание области, зритель мог уйти со страницы или открыть настройки.
    if (destroyed || stopPlayer) {
      starting = false;
      return;
    }
    const embedded = wid ? { wid, progress_id: crypto.randomUUID(), resume: continuing } : {};
    if (wid) {
      // Новый запуск заменяет прежний: его завершение уже не закрывает плеер.
      if (playId) api.cancelLoad(playId).catch(() => {});
      const replacing = watching;
      playId = embedded.progress_id ?? null;
      // Пока обновляется ссылка, старая озвучка не должна звучать под скрытым видео.
      if (replacing) await api.playerStop().catch(() => {});
      watching = true;
      videoReady = false;
      await tick();
      playerBox?.scrollIntoView({ block: "nearest" });
    }
    try {
      const title = series ? episodeTitle(movie.title, currentSeason?.name ?? null, currentEpisode?.name ?? null) : movie.title;
      await onplay(title, urls, {
        movie_url: movie.url,
        source: movie.source,
        quality,
        voice: translator || undefined,
        season: series ? season : undefined,
        episode: series ? episode : undefined,
        referer: movie.referer || undefined,
        watch: watchTitle
          ? {
              title: watchTitle,
              season: series && episode ? season : undefined,
              episode: series && episode ? episode : undefined,
              final: finalEpisode,
            }
          : undefined,
        ...embedded,
      });
    } catch {
      // Сообщение показывает окно приложения, здесь остаётся убрать плеер.
      if (wid && playId === embedded.progress_id) closePlayer();
    } finally {
      starting = false;
      const restart = pendingRestart;
      pendingRestart = null;
      if (restart && watching && !destroyed) play(restart.resume);
    }
  }

  const streamView = $derived(streamError ? describeStreamError(streamError, series !== null) : null);
  const streamFailure = $derived(streamError ? failedStep(steps) : null);
</script>

{#if backdrop}
  <div class="backdrop" aria-hidden="true"><img src={backdrop} alt="" onerror={() => (backdrop = null)} /></div>
{/if}

<div class="page">
<button class="btn ghost back" onclick={onback}>← {backLabel}</button>

  <!-- «Смотреть» стоит под выбором: под озвучкой у фильма, под сериями у сериала. -->
  {#snippet watchButton()}
    {#if watching}
      <button class="btn watch play" onclick={stopWatching}>■ Закрыть плеер</button>
    {:else}
      <button class="btn watch play" disabled={loadingStreams || starting || urls.length === 0} onclick={play}>
        ▶ {loadingStreams ? (series ? "Загружаем серию…" : "Загружаем озвучку…") : starting ? "Запускаем…" : "Смотреть"}
      </button>
    {/if}
  {/snippet}

  {#snippet streamStatus()}
    {#if series?.moved && !loadingStreams && !streamError}
      <p class="notice" role="status">{MOVED_EPISODE_NOTICE}</p>
    {/if}

    {#if streamView}
      <p class="stream-error" role="alert">
        {streamView.title}.
        {#if streamFailure}Не удалось: {streamFailure.label.toLowerCase()}.{/if}
        {streamView.hint}
        {#if streamError === "cancelled" || streamView.retry}
          <button class="btn retry" onclick={retryStreams}>Повторить</button>
        {/if}
      </p>
    {/if}

    {#if loadingStreams && steps.length}
      <LoadProgress {steps} {elapsed} oncancel={cancelLoad} />
    {/if}
  {/snippet}

  {#snippet info()}
    {#if details}<FactBadges badges={pageFacts.badges} />{/if}
    <h1>{details?.title ?? card.title}</h1>
    {#if details?.orig_title}<p class="orig">{details.orig_title}</p>{/if}

    {#if loadError}
      {@const view = describeError(loadError)}
      {@const failed = failedStep(steps)}
      <StatusMessage
        title={view.title}
        hint={failed ? `Не удалось: ${failed.label.toLowerCase()}. ${view.hint}` : view.hint}
        onretry={view.retry ? load : undefined}
      />
    {:else if !details}
      <LoadProgress {steps} {elapsed} oncancel={cancelLoad} onretry={retryLoad} />
    {:else}
      <ul class="chips">
        {#each pageFacts.chips as chip (chip.label)}
          <li><small>{chip.label}</small>{chip.value}</li>
        {/each}
        <li><small>Источник</small>{sourceName(details.source)}</li>
      </ul>

      {#if series && seasonEpisodes.length}
        <div class="progress" role="group" aria-label="Просмотрено">
          <div class="progress-head">
            <span><i aria-hidden="true"></i>Просмотрено</span>
            <span><b>{watchedInSeason}</b> / {seasonEpisodes.length}</span>
          </div>
          <div class="bar"><div style:width={`${(watchedInSeason / seasonEpisodes.length) * 100}%`}></div></div>
        </div>
      {/if}

      {#if pageFacts.genres.length}
        <ul class="genres">
          {#each pageFacts.genres as genre (genre)}<li>{genre}</li>{/each}
        </ul>
      {/if}

      {#if switchedNotice}<p class="notice">{switchedNotice}</p>{/if}

      {#if !details.alternatives.length}
        <div class="controls">
          <!-- Озвучка выбирается в третьей колонке: «Озвучка» у фильма, «Эпизоды» у сериала. -->
          {#if qualities.length}
            <div class="quality">
              <span>Качество</span>
              <div class="segments">
                {#each qualities as label (label)}
                  <button
                    class:active={label === quality}
                    aria-pressed={label === quality}
                    onclick={() => chooseQuality(label)}>{label}</button
                  >
                {/each}
              </div>
            </div>
          {/if}

          <button class="btn ghost copy" disabled={urls.length === 0} onclick={copy}>
            {copied ? "Ссылка скопирована" : "Скопировать ссылку на поток"}
          </button>
        </div>
      {/if}

      {#if !watching}{@render streamStatus()}{/if}

      {#if details.alternatives.length}
        <div class="alternatives">
          <p>На этой странице нет видео фильма. Выберите вариант из HDRezka:</p>
          <PosterGrid movies={details.alternatives} {onopen} />
        </div>
      {/if}

      {#if details.description}<p class="description">{details.description}</p>{/if}

      {#if details.actors.length}
        <p class="actors"><span>В ролях</span>{details.actors.join(", ")}</p>
      {/if}

      {#if settings?.lampac_enabled}
        <LampacSources title={details.title} originalTitle={details.orig_title} year={filmYear} movieUrl={details.url} serial={looksLikeSeries(details.url, details.title, details.info_table["Жанр"] ?? "")} onplay={playLampac} />
      {/if}
    {/if}
  {/snippet}

  <article class:with-panel={series !== null || voicePanel} class:watching style:--side-height={sideHeight ? `${sideHeight}px` : null}>
    <div class="side" bind:offsetHeight={sideHeight}>
      <div class="art">
        <Poster url={details?.poster_url ?? card.poster_url} title={card.title} />
        {#if pageFacts.siteQuality}<span class="site-quality">{pageFacts.siteQuality}</span>{/if}
      </div>
      {#if watchTitle}
        <StatusPicker status={entry?.status ?? null} busy={savingStatus} onchange={changeStatus} />
        {#if watchError}<p class="watch-error" role="alert">{describeError(watchError).title}</p>{/if}
      {/if}
      <div class="side-actions">
        <button class="btn second" onclick={openTrailer}>Трейлер</button>
      </div>
    </div>

    {#if watching}
      <div class="player-area">
        <div class="player-card">
          <PlayerBar
            label={playerLabel}
            series={series !== null}
            hasPrevious={neighbours.previous !== null}
            hasNext={neighbours.next !== null || nextSeason !== null}
            busy={loadingStreams || starting}
            onprevious={() => neighbours.previous && loadEpisode(null, season, neighbours.previous)}
            onnext={nextEpisode}
            onclose={stopWatching}
          />
          <div class="player" bind:this={playerBox}>
            <!-- Видно при запуске и на долю секунды при прокрутке, пока видео догоняет страницу. -->
            {#if backdrop}<img src={backdrop} alt="" aria-hidden="true" />{/if}
            {#if !videoReady}<p>Запускаем плеер…</p>{/if}
          </div>
        </div>
        {@render streamStatus()}
      </div>
    {/if}

    <div class="center">{@render info()}</div>

    {#if series}
      <EpisodePanel
        seasons={series.seasons}
        {season}
        {episode}
        watched={entry?.episodes[season] ?? []}
        watchedCount={watchedInSeason}
        {quality}
        voices={details?.translators.map((item) => item.name) ?? []}
        voice={translator}
        voiceEpisodes={seasonVoiceEpisodes}
        onvoice={chooseTranslator}
        busy={loadingStreams}
        canMark={watchTitle !== null}
        onseason={(id) => loadEpisode(null, id, null)}
        onepisode={(id) => loadEpisode(null, season, id)}
        ontoggle={toggleEpisode}
        footer={details && !details.alternatives.length ? watchButton : undefined}
      />
    {:else if voicePanel && details}
      <VoicePanel
        voices={details.translators.map((item) => item.name)}
        voice={translator}
        busy={loadingStreams}
        onvoice={chooseTranslator}
        footer={watchButton}
      />
    {/if}
  </article>

  {#if details?.related.length}
    <section class="related">
      <h2>Рекомендации сайта</h2>
      <PosterGrid movies={details.related} {onopen} compact />
    </section>
  {/if}
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 0;
    overflow: hidden;
    pointer-events: none;
    animation: fade 0.5s var(--ease);
  }

  .backdrop img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0.22;
    filter: blur(48px) saturate(1.1);
    transform: scale(1.15);
  }

  .backdrop::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgb(0 0 0 / 30%), var(--bg) 85%);
  }

  .page {
    position: relative;
    z-index: 1;
    max-width: 1500px;
    margin: 0 auto;
  }

  .back {
    margin: -8px 0 12px -10px;
  }

  /* Колонки (contracts/movie-page-layout.md): действия | сведения | эпизоды.
     Встроенный плеер занимает место сведений, а они переезжают строкой ниже — тот же блок, без пересоздания. */
  article {
    display: grid;
    grid-template-columns: minmax(200px, 320px) minmax(0, 1fr);
    grid-template-areas: "side center";
    gap: 28px;
    align-items: start;
    animation: appear 0.25s var(--ease);
  }

  article.watching {
    grid-template-areas:
      "side player"
      "center center";
  }

  article.with-panel {
    --episodes-height: var(--side-height);
    grid-template-columns: minmax(180px, 300px) minmax(0, 1fr) minmax(260px, 340px);
    grid-template-areas: "side center panel";
  }

  article.with-panel.watching {
    grid-template-areas:
      "side player panel"
      "center center center";
  }

  .player-area {
    grid-area: player;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }

  article :global(.panel) {
    grid-area: panel;
  }

  .side {
    grid-area: side;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
  }

  .art {
    position: relative;
    border-radius: var(--radius);
    box-shadow: 0 18px 40px rgb(0 0 0 / 50%);
  }

  .site-quality {
    position: absolute;
    top: 10px;
    right: 10px;
    padding: 2px 7px;
    border: 1px solid rgb(255 255 255 / 70%);
    border-radius: 6px;
    background: rgb(0 0 0 / 65%);
    color: #fff;
    font-size: 12px;
    font-weight: 700;
  }

  .watch-error {
    color: #fda4af;
    font-size: 13px;
  }

  .side-actions {
    display: flex;
    gap: 8px;
  }

  .side-actions .btn {
    flex: 1;
    min-width: 0;
    padding: 11px 12px;
    font-weight: 700;
    white-space: nowrap;
  }

  /* Главная кнопка страницы белая, как у сайта; остальные основные кнопки — акцентные. */
  .btn.watch {
    border-color: transparent;
    background: #fff;
    color: #000;
  }

  .btn.watch:hover:not(:disabled) {
    border-color: transparent;
    background: #e2e2e2;
  }

  .btn.second {
    background: var(--surface-2);
  }

  .btn.play {
    width: 100%;
    padding: 12px;
    font-weight: 700;
  }

  .center {
    grid-area: center;
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-width: 0;
  }

  /* У фильма нет панели «Эпизоды»: строки описания не растягиваются на всю ширину окна. */
  article:not(.with-panel) .center {
    max-width: 980px;
  }

  h1 {
    font-size: 34px;
    font-weight: 800;
    line-height: 1.12;
    letter-spacing: -0.015em;
    overflow-wrap: anywhere;
  }

  .orig {
    margin-top: -6px;
    color: var(--muted);
    font-size: 19px;
    font-weight: 600;
  }

  .chips,
  .genres {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chips li {
    display: flex;
    align-items: baseline;
    gap: 6px;
    max-width: 100%;
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--surface) 70%, transparent);
    font-size: 13px;
  }

  .chips small {
    color: var(--muted);
    font-size: 12px;
  }

  .genres li {
    padding: 6px 14px;
    border-radius: 999px;
    background: var(--surface-2);
    font-size: 13px;
    font-weight: 600;
  }

  .progress {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 680px;
  }

  .progress-head {
    display: flex;
    justify-content: space-between;
    color: var(--muted);
    font-size: 13px;
  }

  .progress-head i {
    display: inline-block;
    width: 8px;
    height: 8px;
    margin-right: 7px;
    border-radius: 50%;
    background: var(--accent);
  }

  .progress-head b {
    color: var(--text);
  }

  .bar {
    height: 6px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--surface-2);
  }

  .bar div {
    height: 100%;
    border-radius: inherit;
    background: var(--accent);
    transition: width 0.3s var(--ease);
  }

  .description {
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--surface) 80%, transparent);
    color: var(--body);
    user-select: text;
  }

  .actors {
    color: var(--body);
    user-select: text;
  }

  .actors span {
    display: block;
    color: var(--muted);
    font-size: 12px;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    align-items: flex-end;
  }

  .quality {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  .quality > span {
    color: var(--muted);
    font-size: 12px;
  }

  .segments {
    display: flex;
    padding: 3px;
    border-radius: 10px;
    background: var(--surface-2);
  }

  .segments button {
    padding: 6px 14px;
    border: 0;
    border-radius: 8px;
    background: none;
    cursor: pointer;
    transition: background 0.15s;
  }

  .segments button:hover:not(.active) {
    background: var(--hover);
  }

  .segments button.active {
    background: var(--text);
    color: var(--bg);
    font-weight: 600;
  }

  .copy {
    margin-left: auto;
  }

  .stream-error {
    color: #fda4af;
  }

  .retry {
    display: block;
    margin-top: 8px;
    color: var(--text);
  }

  .notice {
    color: #fcd34d;
  }

  .alternatives {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .alternatives p {
    color: #fda4af;
  }

  .player-card {
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 16px;
    background: var(--surface);
  }

  .player {
    position: relative;
    width: min(100%, calc((100vh - 200px) * 16 / 9));
    margin: 0 auto;
    aspect-ratio: 16 / 9;
    overflow: hidden;
    background: #000;
  }

  .player img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    filter: blur(24px) brightness(0.55);
    transform: scale(1.1);
  }

  .player p {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    margin: 0;
  }

  .related {
    margin-top: 40px;
    animation: appear 0.25s var(--ease);
  }

  .related h2 {
    margin-bottom: 16px;
    font-size: 19px;
    font-weight: 600;
  }

  @media (max-width: 1180px) {
    /* Панель уходит под сведения, равнять её по постеру незачем. */
    article.with-panel {
      --episodes-height: initial;
      grid-template-columns: minmax(180px, 300px) minmax(0, 1fr);
      grid-template-areas:
        "side center"
        "panel panel";
    }

    article.with-panel.watching {
      grid-template-areas:
        "side player"
        "panel panel"
        "center center";
    }
  }

  @media (max-width: 860px) {
    article,
    article.with-panel {
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "side" "center" "panel";
      gap: 22px;
    }

    article.watching,
    article.with-panel.watching {
      grid-template-areas: "side" "player" "panel" "center";
    }

    .side {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      align-items: start;
    }

    .art {
      grid-row: span 3;
    }

    h1 {
      font-size: 24px;
    }

    .copy {
      margin-left: 0;
    }
  }
</style>

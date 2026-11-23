<script lang="ts">
  import { onMount } from "svelte";
  import { api, onBackendEvent, type LampacSource, type LampacState, type LampacVariants, type PlayDetails } from "../lib/api";
  import { bestLampacSource, pickLampacItem, sortQualities } from "../lib/logic";
  import Dropdown from "./Dropdown.svelte";

  interface Props {
    title: string;
    originalTitle: string | null;
    year: string | null;
    movieUrl: string;
    serial: boolean;
    onplay: (title: string, urls: string[], details: PlayDetails) => Promise<void>;
  }

  let { title, originalTitle, year, movieUrl, serial, onplay }: Props = $props();

  let server = $state<LampacState | null>(null);
  let sources = $state<LampacSource[]>([]);
  let searching = $state(false);
  let failed = $state(false);
  let selectedId = $state<string | null>(null);
  let variants = $state<LampacVariants | null>(null);
  let voice = $state("");
  let quality = $state("");
  let seasons = $state<{ name: string; url: string }[]>([]);
  let season = $state("");
  let episode = $state<string | null>(null);
  let userChose = false;
  // Ответ на прежний выбор не должен заменить более новый выбор зрителя.
  let selection = 0;
  let loadingVoice = $state(false);
  let starting = $state(false);
  let playError = $state(false);
  let searchId: string | null = null;

  const selected = $derived(sources.find((source) => source.id === selectedId) ?? null);
  const voiceNames = $derived(variants ? (variants.voices.length ? variants.voices.map((v) => v.name) : [...new Set(variants.items.map((i) => i.voice))]) : []);
  const episodes = $derived(variants ? [...new Set(variants.items.flatMap((i) => (i.episode ? [i.episode.name] : [])))] : []);
  const item = $derived(variants ? pickLampacItem(variants, voice, episode) : null);
  const qualities = $derived(item ? sortQualities(item.qualities.map((q) => q.label)) : []);

  function bestQualityOf(list: LampacVariants, name: string, part: string | null) {
    return sortQualities(pickLampacItem(list, name, part)?.qualities.map((q) => q.label) ?? [])[0] ?? "";
  }

  function show(next: LampacVariants, keepEpisode: string | null = null) {
    variants = next;
    const active = next.voices.find((v) => v.active)?.name ?? next.items[0]?.voice ?? "";
    voice = active;
    const names = next.items.flatMap((i) => (i.episode ? [i.episode.name] : []));
    episode = keepEpisode && names.includes(keepEpisode) ? keepEpisode : (names[0] ?? null);
    quality = bestQualityOf(next, active, episode);
  }

  function open(source: LampacSource) {
    selection++;
    loadingVoice = false;
    selectedId = source.id;
    playError = false;
    seasons = source.variants.seasons;
    season = seasons[0]?.name ?? "";
    show(source.variants);
  }

  function choose(source: LampacSource) {
    userChose = true;
    open(source);
  }

  function chooseQuality(label: string) {
    userChose = true;
    quality = label;
  }

  function chooseEpisode(name: string) {
    userChose = true;
    episode = name;
    playError = false;
    quality = bestQualityOf(variants!, voice, name);
  }

  async function chooseSeason(name: string) {
    const found = seasons.find((s) => s.name === name);
    if (!found) return;
    userChose = true;
    season = name;
    playError = false;
    loadingVoice = true;
    const current = ++selection;
    try {
      const next = await api.lampacVariants(found.url);
      if (current === selection) show(next);
    } catch {
      if (current === selection) playError = true;
    } finally {
      if (current === selection) loadingVoice = false;
    }
  }

  async function search() {
    if (searching || searchId) return;
    const id = crypto.randomUUID();
    searchId = id;
    searching = true;
    try {
      await api.lampacSources(id, title, originalTitle, year, serial);
    } catch {
      failed = sources.length === 0;
    } finally {
      searching = false;
    }
  }

  async function chooseVoice(name: string) {
    const found = variants?.voices.find((v) => v.name === name);
    userChose = true;
    voice = name;
    playError = false;
    if (!found) {
      quality = bestQualityOf(variants!, name, episode);
      return;
    }
    loadingVoice = true;
    const current = ++selection;
    try {
      const next = await api.lampacVariants(found.url);
      if (current === selection) {
        show(next, episode);
        voice = name;
      }
    } catch {
      if (current === selection) playError = true;
    } finally {
      if (current === selection) loadingVoice = false;
    }
  }

  async function play() {
    if (!variants || starting) return;
    userChose = true;
    starting = true;
    playError = false;
    try {
      // Ссылки временные: перед запуском берутся свежие.
      const fresh = await api.lampacVariants(variants.url).catch(() => variants!);
      const url = pickLampacItem(fresh, voice, episode)?.qualities.find((q) => q.label === quality)?.url
        ?? item?.qualities.find((q) => q.label === quality)?.url;
      if (!url) {
        playError = true;
        return;
      }
      const name = episode ? `${title}: ${[season, episode].filter(Boolean).join(", ")}` : title;
      await onplay(name, [url], { movie_url: movieUrl, source: "lampac", quality, voice: voice || undefined });
    } finally {
      starting = false;
    }
  }

  function applyServer(next: LampacState) {
    server = next;
    if (next.state === "running") search();
  }

  onMount(() => {
    const stop = onBackendEvent(({ event, data }) => {
      if (event === "lampac_state" && data?.lampac) applyServer(data.lampac);
      if (event === "lampac_source" && data?.id === searchId && data?.source) {
        sources.push(data.source);
        // Пока зритель не выбрал сам, открыт источник с наибольшим числом озвучек.
        if (!userChose) {
          const best = bestLampacSource(sources);
          if (best && best.id !== selectedId) open(best);
        }
      }
    });
    api.lampacState().then(applyServer).catch(() => {});
    return () => {
      if (searchId) api.cancelLoad(searchId).catch(() => {});
      searchId = null;
      stop.then((unlisten) => unlisten());
    };
  });
</script>

{#if server?.state === "starting" || server?.state === "running"}
  <section class="sources">
    <h2>Другие источники</h2>

    {#if server.state === "starting"}
      <p class="hint" role="status">Lampac запускается…</p>
    {:else if failed}
      <p class="hint" role="alert">Lampac не ответил. Основной источник работает как обычно.</p>
    {:else if sources.length === 0}
      <p class="hint" role="status">{searching ? "Ищем фильм в других источниках…" : "В других источниках фильм не найден."}</p>
    {:else}
      <div class="list">
        {#each sources as source (source.id)}
          <button class:active={source.id === selectedId} aria-pressed={source.id === selectedId} onclick={() => choose(source)}>
            {source.name}
          </button>
        {/each}
        {#if searching}<span class="hint">Ищем ещё…</span>{/if}
      </div>

      {#if selected && variants}
        <div class="controls">
          {#if seasons.length > 1}
            <div class="field short">
              <span>Сезон</span>
              <Dropdown label="Сезон" options={seasons.map((s) => s.name)} value={season} disabled={loadingVoice} onchange={chooseSeason} />
            </div>
          {/if}
          {#if episodes.length > 1 && episode}
            <div class="field short">
              <span>Серия</span>
              <Dropdown label="Серия" options={episodes} value={episode} disabled={loadingVoice} onchange={chooseEpisode} />
            </div>
          {/if}
          {#if voiceNames.length > 1}
            <div class="field voices">
              <span>Озвучка</span>
              <Dropdown label="Озвучка источника" options={voiceNames} value={voice} disabled={loadingVoice} onchange={chooseVoice} />
            </div>
          {:else if voiceNames[0]}
            <div class="field"><span>Озвучка</span><div class="single">{voiceNames[0]}</div></div>
          {/if}

          {#if qualities.length > 1}
            <div class="field">
              <span>Качество</span>
              <div class="segments">
                {#each qualities as label (label)}
                  <button class:active={label === quality} aria-pressed={label === quality} onclick={() => chooseQuality(label)}>{label}</button>
                {/each}
              </div>
            </div>
          {:else if qualities[0]}
            <div class="field"><span>Качество</span><div class="single">{qualities[0]}</div></div>
          {/if}

          <button class="btn play" disabled={starting || loadingVoice || !item} onclick={play}>
            ▶ {loadingVoice ? "Загружаем озвучку…" : starting ? "Запускаем…" : `Смотреть через ${selected.name}`}
          </button>
        </div>
        {#if playError}<p class="error" role="alert">Этот вариант сейчас недоступен. Выберите другой источник или озвучку.</p>{/if}
      {/if}
    {/if}
  </section>
{/if}

<style>
  .sources {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 10px;
    padding-top: 16px;
    border-top: 1px solid rgb(255 255 255 / 8%);
  }

  h2 {
    font-size: 17px;
    font-weight: 600;
  }

  .hint {
    color: var(--muted);
  }

  .error {
    color: #fda4af;
  }

  .list {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }

  .list button {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface-2);
    cursor: pointer;
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  .list button:hover:not(.active) {
    background: var(--hover);
  }

  .list button.active {
    border-color: var(--accent);
    background: rgb(244 63 94 / 14%);
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 18px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  .voices {
    width: 320px;
    max-width: 100%;
  }

  .short {
    width: 200px;
    max-width: 100%;
  }

  .field > span {
    color: var(--muted);
    font-size: 12px;
  }

  .single {
    padding: 9px 0;
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
  }

  .segments button.active {
    background: var(--text);
    color: var(--bg);
    font-weight: 600;
  }
</style>

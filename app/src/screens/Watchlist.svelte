<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorCode, onBackendEvent, type ErrorCode, type MovieCard, type WatchEntry } from "../lib/api";
  import { WATCH_STATUSES, countByStatus, describeError, filterWatchlist, rebaseUrl, watchStatus, type WatchFilter } from "../lib/logic";
  import Poster from "../components/Poster.svelte";
  import StatusMessage from "../components/StatusMessage.svelte";
  import SyncStatus from "../components/SyncStatus.svelte";

  interface Props {
    kinogoUrl: string | null;
    onopen: (card: MovieCard) => void;
    /** Файл списка был повреждён и начат заново. */
    onreset: () => void;
    /** Открыть Настройки (вход заново для синхронизации). */
    onsettings: () => void;
  }

  let { kinogoUrl, onopen, onreset, onsettings }: Props = $props();

  let items = $state<WatchEntry[] | null>(null);
  let error = $state<ErrorCode | null>(null);
  let filter = $state<WatchFilter>("all");

  const counts = $derived(countByStatus(items ?? []));
  const shown = $derived(filterWatchlist(items ?? [], filter));
  const tabs = $derived([{ id: "all" as WatchFilter, label: "Все" }, ...WATCH_STATUSES]);

  let request = 0;

  async function load() {
    const current = ++request;
    error = null;
    try {
      const result = await api.watchlistList();
      if (current !== request) return;
      items = result.items;
      if (result.warning === "watchlist_reset") onreset();
    } catch (failure) {
      if (current === request) error = errorCode(failure);
    }
  }

  function open(entry: WatchEntry) {
    const source = entry.source ?? "kinogo";
    onopen({
      title: entry.title,
      url: source === "kinogo" ? rebaseUrl(entry.url, kinogoUrl) : entry.url,
      poster_url: entry.poster_url,
      info: entry.year ?? "",
      source,
    });
  }

  onMount(() => {
    load();
    const stop = onBackendEvent(({ event }) => {
      if (event === "watchlist_changed" || event === "watchlist_reloaded") load();
    });
    return () => {
      stop.then((unlisten) => unlisten());
    };
  });
</script>

<section>
  <header>
    <h1>Мой список</h1>
    <SyncStatus {onsettings} />
  </header>

  <div class="tabs" role="tablist" aria-label="Статус">
    {#each tabs as tab (tab.id)}
      <button role="tab" aria-selected={filter === tab.id} onclick={() => (filter = tab.id)}>
        {tab.label} <span>{counts[tab.id]}</span>
      </button>
    {/each}
  </div>

  {#if error}
    <StatusMessage title={describeError(error).title} hint={describeError(error).hint} onretry={load} />
  {:else if items === null}
    <StatusMessage title="Загружаем список…" loading />
  {:else if shown.length === 0}
    <p class="hint">
      {items.length === 0
        ? "Список пуст. Откройте фильм или сериал и выберите статус под постером."
        : "В этом разделе пока ничего нет."}
    </p>
  {:else}
    <div class="grid">
      {#each shown as entry (entry.key)}
        {@const status = watchStatus(entry.status)}
        <button class="card" title={entry.title} onclick={() => open(entry)}>
          <div class="art">
            <Poster url={entry.poster_url} title={entry.title} />
            <span class="badge" style:background={status.color}>{status.label}</span>
          </div>
          <strong>{entry.title}</strong>
          {#if entry.year}<small>{entry.year}</small>{/if}
        </button>
      {/each}
    </div>
  {/if}
</section>

<style>
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin: 0 0 18px;
  }

  h1 {
    margin: 0;
    font-size: 26px;
  }

  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 24px;
  }

  .tabs button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface);
    color: var(--muted);
    font-weight: 600;
    cursor: pointer;
  }

  .tabs button[aria-selected="true"] {
    border-color: var(--accent);
    background: var(--surface-2);
    color: var(--text);
  }

  .tabs span {
    font-size: 12px;
    opacity: 0.75;
  }

  .hint {
    color: var(--muted);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(165px, 1fr));
    gap: 26px 20px;
    animation: appear 0.25s var(--ease);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    text-align: left;
    cursor: pointer;
  }

  .art {
    position: relative;
    margin-bottom: 8px;
    border-radius: var(--radius);
    box-shadow: 0 6px 18px rgb(0 0 0 / 35%);
    transition:
      transform 0.2s var(--ease),
      box-shadow 0.2s;
  }

  .card:hover .art {
    transform: translateY(-4px) scale(1.02);
    box-shadow:
      0 14px 30px rgb(0 0 0 / 50%),
      0 0 0 2px var(--accent);
  }

  .badge {
    position: absolute;
    left: 8px;
    bottom: 8px;
    padding: 3px 8px;
    border-radius: 6px;
    color: #fff;
    font-size: 12px;
    font-weight: 600;
  }

  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    color: var(--muted);
  }
</style>

<script lang="ts">
  import type { ErrorCode, MovieCard } from "../lib/api";
  import { describeError } from "../lib/logic";
  import PosterGrid from "../components/PosterGrid.svelte";
  import StatusMessage from "../components/StatusMessage.svelte";

  interface Props {
    query: string;
    movies: MovieCard[];
    loading: boolean;
    error: ErrorCode | null;
    onopen: (movie: MovieCard) => void;
    onretry: () => void;
  }

  let { query, movies, loading, error, onopen, onretry }: Props = $props();
  const view = $derived(error ? describeError(error) : null);
</script>

{#if loading}
  <StatusMessage title="Ищем фильмы…" loading />
{:else if view}
  <StatusMessage title={view.title} hint={view.hint} onretry={view.retry ? onretry : undefined} />
{:else if movies.length === 0}
  <StatusMessage title={`По запросу «${query}» ничего не нашлось`} hint="Попробуйте изменить запрос." />
{:else}
  <h2>Результаты по запросу «{query}»</h2>
  {#if movies[0].source === "hdrezka"}
    <p class="fallback" role="status">На основном источнике ничего не нашлось, показаны результаты HDRezka.</p>
  {/if}
  <PosterGrid {movies} {onopen} />
{/if}

<style>
  .fallback {
    margin: -12px 0 20px;
    color: #fda4af;
  }

  h2 {
    margin-bottom: 20px;
    color: var(--muted);
    font-size: 15px;
    font-weight: 400;
  }
</style>

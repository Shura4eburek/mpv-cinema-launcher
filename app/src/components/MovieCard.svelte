<script lang="ts">
  import type { MovieCard } from "../lib/api";
  import { yearFrom } from "../lib/logic";
  import Poster from "./Poster.svelte";

  interface Props {
    movie: MovieCard;
    onopen: (movie: MovieCard) => void;
  }

  let { movie, onopen }: Props = $props();
  const year = $derived(yearFrom(movie.info));
</script>

<button class="card" title={movie.title} onclick={() => onopen(movie)}>
  <div class="art"><Poster url={movie.poster_url} title={movie.title} /></div>
  <strong>{movie.title}</strong>
  {#if year}<small>{year}</small>{/if}
</button>

<style>
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

  strong {
    display: -webkit-box;
    overflow: hidden;
    font-weight: 600;
    line-height: 1.3;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }

  small {
    color: var(--muted);
    font-size: 13px;
  }
</style>

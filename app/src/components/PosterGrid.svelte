<script lang="ts">
  import type { MovieCard as Movie } from "../lib/api";
  import MovieCard from "./MovieCard.svelte";

  interface Props {
    movies: Movie[];
    onopen: (movie: Movie) => void;
    compact?: boolean;
  }

  let { movies, onopen, compact = false }: Props = $props();
</script>

<div class="grid" class:compact>
  {#each movies as movie}
    <MovieCard {movie} {onopen} />
  {/each}
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(165px, 1fr));
    gap: 26px 20px;
    animation: appear 0.25s var(--ease);
  }

  /* У рекомендаций сайта постеры мелкие: крупнее они размываются. */
  .compact {
    grid-template-columns: repeat(auto-fill, minmax(125px, 1fr));
  }
</style>

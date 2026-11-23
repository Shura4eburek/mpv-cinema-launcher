<script lang="ts">
  import { api } from "../lib/api";

  interface Props {
    url: string | null;
    title: string;
  }

  let { url, title }: Props = $props();
  let src = $state<string | null>(null);

  $effect(() => {
    const requested = url;
    let cancelled = false;
    src = null;
    if (requested) {
      api
        .posterSrc(requested)
        .then((value) => {
          if (!cancelled) src = value;
        })
        // Постер необязателен: при ошибке остаётся заглушка.
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  });
</script>

<div class="poster">
  {#if src}
    <img {src} alt="" onerror={() => (src = null)} />
  {:else}
    <span>{title}</span>
  {/if}
</div>

<style>
  .poster {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    aspect-ratio: 2 / 3;
    overflow: hidden;
    border-radius: var(--radius);
    background: linear-gradient(160deg, var(--surface-2), var(--surface));
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    animation: appear 0.3s var(--ease);
  }

  span {
    padding: 14px;
    color: var(--muted);
    font-size: 13px;
    text-align: center;
    overflow-wrap: anywhere;
  }
</style>

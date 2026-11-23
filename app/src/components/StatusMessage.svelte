<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    title: string;
    hint?: string;
    loading?: boolean;
    onretry?: () => void;
    children?: Snippet;
  }

  let { title, hint = "", loading = false, onretry, children }: Props = $props();
</script>

<div class="status" role="status">
  {#if loading}<div class="spinner"></div>{/if}
  <h2>{title}</h2>
  {#if hint}<p>{hint}</p>{/if}
  {#if onretry}<button class="btn" onclick={onretry}>Повторить</button>{/if}
  {@render children?.()}
</div>

<style>
  .status {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    min-height: 320px;
    padding: 32px;
    text-align: center;
    animation: appear 0.25s var(--ease);
  }

  h2 {
    font-size: 18px;
    font-weight: 600;
  }

  p {
    max-width: 460px;
    color: var(--muted);
    user-select: text;
  }

  button {
    margin-top: 8px;
  }
</style>

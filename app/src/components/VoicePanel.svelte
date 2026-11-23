<script lang="ts">
  import type { Snippet } from "svelte";
  import Dropdown from "./Dropdown.svelte";

  interface Props {
    voices: string[];
    voice: string;
    /** Пока загружается озвучка, выбор недоступен. */
    busy: boolean;
    onvoice: (name: string) => void;
    /** Кнопка «Смотреть» под выбором озвучки. */
    footer?: Snippet;
  }

  let { voices, voice, busy, onvoice, footer }: Props = $props();
</script>

<aside class="panel" aria-label="Озвучка">
  <h2>Озвучка</h2>

  {#if voices.length > 1}
    <Dropdown label="Озвучка" options={voices} value={voice} disabled={busy} onchange={onvoice} />
  {:else}
    <div class="voice" title="Озвучка">{voices[0]}</div>
  {/if}

  {@render footer?.()}
</aside>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 16px;
    background: var(--surface);
    align-self: start;
  }

  h2 {
    font-size: 16px;
    font-weight: 700;
  }

  .panel :global(.dropdown) {
    width: 100%;
  }

  .voice {
    padding: 9px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface-2);
    font-weight: 600;
  }
</style>

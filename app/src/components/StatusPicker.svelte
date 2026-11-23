<script lang="ts">
  import type { WatchStatus } from "../lib/api";
  import { WATCH_STATUSES, watchStatus } from "../lib/logic";

  interface Props {
    status: WatchStatus | null;
    busy?: boolean;
    onchange: (status: WatchStatus | null) => void;
  }

  let { status, busy = false, onchange }: Props = $props();

  let open = $state(false);
  let root: HTMLDivElement;
  const current = $derived(status ? watchStatus(status) : null);

  function choose(next: WatchStatus | null) {
    open = false;
    if (next !== status) onchange(next);
  }

  function closeOutside(event: PointerEvent) {
    if (open && !root.contains(event.target as Node)) open = false;
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === "Escape") open = false;
  }
</script>

<svelte:window onpointerdown={closeOutside} />

<div class="picker" bind:this={root}>
  <button
    type="button"
    class="trigger"
    class:set={current !== null}
    style:--status={current?.color}
    aria-haspopup="menu"
    aria-expanded={open}
    disabled={busy}
    onclick={() => (open = !open)}
    {onkeydown}
  >
    {#if current}
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" /></svg>
    {:else}
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
    {/if}
    <span>{current?.label ?? "Добавить в список"}</span>
    <svg class="chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
  </button>

  {#if open}
    <div class="menu" role="menu" tabindex="-1" {onkeydown}>
      {#each WATCH_STATUSES as item (item.id)}
        <button
          type="button"
          role="menuitemradio"
          aria-checked={item.id === status}
          style:--status={item.color}
          onclick={() => choose(item.id)}
        >
          <i aria-hidden="true"></i>{item.label}
        </button>
      {/each}
      {#if status}
        <button type="button" role="menuitem" class="remove" onclick={() => choose(null)}>Удалить из списка</button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .picker {
    position: relative;
    width: 100%;
  }

  .trigger {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface-2);
    font-weight: 600;
    cursor: pointer;
    transition:
      background 0.15s,
      border-color 0.15s,
      filter 0.15s;
  }

  .trigger.set {
    border-color: transparent;
    background: var(--status);
    color: #fff;
  }

  .trigger:hover:not(:disabled) {
    filter: brightness(1.15);
  }

  .trigger:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .trigger span {
    flex: 1;
    text-align: center;
  }

  svg {
    flex: none;
    width: 16px;
    height: 16px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .chevron {
    transition: transform 0.2s var(--ease);
  }

  [aria-expanded="true"] .chevron {
    transform: rotate(180deg);
  }

  .menu {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 20;
    display: flex;
    flex-direction: column;
    width: 100%;
    padding: 5px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--popover);
    box-shadow: 0 18px 40px rgb(0 0 0 / 55%);
    animation: appear 0.15s var(--ease);
  }

  .menu button {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border: 0;
    border-radius: 8px;
    background: none;
    text-align: left;
    cursor: pointer;
  }

  .menu button:hover {
    background: var(--surface-2);
  }

  .menu [aria-checked="true"] {
    font-weight: 600;
  }

  i {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--status);
    box-shadow: 0 0 0 1px rgb(255 255 255 / 25%);
  }

  .remove {
    margin-top: 4px;
    border-top: 1px solid var(--border) !important;
    border-radius: 0 0 8px 8px !important;
    color: var(--muted);
  }
</style>

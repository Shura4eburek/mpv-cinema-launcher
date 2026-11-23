<script lang="ts">
  interface Props {
    label: string;
    /** У фильма стрелок нет. */
    series: boolean;
    hasPrevious: boolean;
    hasNext: boolean;
    busy: boolean;
    onprevious: () => void;
    onnext: () => void;
    onclose: () => void;
  }

  let { label, series, hasPrevious, hasNext, busy, onprevious, onnext, onclose }: Props = $props();
</script>

<div class="bar">
  {#if series}
    <button class="arrow" aria-label="Предыдущая серия" disabled={!hasPrevious || busy} onclick={onprevious}>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5 5.5 8l4.5 4.5" /></svg>
    </button>
  {/if}
  <strong>{label}</strong>
  {#if series}
    <button class="arrow" aria-label="Следующая серия" disabled={!hasNext || busy} onclick={onnext}>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" /></svg>
    </button>
  {/if}
  <button class="close" aria-label="Закрыть плеер" onclick={onclose}>
    <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
  </button>
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 10px;
  }

  strong {
    min-width: 0;
    overflow: hidden;
    font-size: 15px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  button {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    padding: 0;
    border: 0;
    border-radius: 8px;
    background: none;
    color: var(--muted);
    cursor: pointer;
  }

  button:hover:not(:disabled) {
    background: var(--surface-2);
    color: var(--text);
  }

  button:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .close {
    margin-left: auto;
  }

  svg {
    width: 16px;
    height: 16px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }
</style>

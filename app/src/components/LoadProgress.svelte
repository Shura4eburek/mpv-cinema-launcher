<script lang="ts">
  import { SLOW_LOAD_SECONDS, formatElapsed, type LoadStep } from "../lib/logic";

  interface Props {
    steps: LoadStep[];
    elapsed: number;
    oncancel?: () => void;
    onretry?: () => void;
  }

  let { steps, elapsed, oncancel, onretry }: Props = $props();
  const slow = $derived(elapsed >= SLOW_LOAD_SECONDS);
  const marks = { pending: "○", running: "", done: "✓", error: "✕" } as const;
</script>

<section class="progress" role="status" aria-live="polite">
  <ol>
    {#each steps as step (step.id)}
      <li class={step.state}>
        <span class="mark" aria-hidden="true">
          {#if step.state === "running"}<span class="spinner small"></span>{:else}{marks[step.state]}{/if}
        </span>
        {step.label}
      </li>
    {/each}
  </ol>
  <p class="time">Прошло {formatElapsed(elapsed)}</p>

  {#if slow}
    <div class="slow">
      <p>Загрузка идёт дольше обычного. Сайт или плеер отвечают медленно.</p>
      <div>
        {#if onretry}<button class="btn" onclick={onretry}>Повторить</button>{/if}
        {#if oncancel}<button class="btn ghost" onclick={oncancel}>Отменить</button>{/if}
      </div>
    </div>
  {/if}
</section>

<style>
  .progress {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 18px 20px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    animation: appear 0.2s var(--ease);
  }

  ol {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--muted);
  }

  li.running {
    color: var(--text);
    font-weight: 600;
  }

  li.done .mark {
    color: #4ade80;
  }

  li.error,
  li.error .mark {
    color: #fda4af;
  }

  .mark {
    display: grid;
    place-items: center;
    width: 18px;
    height: 18px;
    flex: none;
  }

  .small {
    width: 14px;
    height: 14px;
    border-width: 2px;
  }

  .time {
    color: var(--muted);
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }

  .slow {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }

  .slow div {
    display: flex;
    gap: 8px;
  }
</style>

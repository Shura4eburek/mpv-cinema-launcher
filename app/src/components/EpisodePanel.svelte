<script lang="ts">
  import type { Snippet } from "svelte";
  import type { Season } from "../lib/api";
  import Dropdown from "./Dropdown.svelte";

  interface Props {
    seasons: Season[];
    season: string;
    episode: string;
    /** Просмотренные серии выбранного сезона. */
    watched: string[];
    /** Отмечено в сезоне — то же число, что на полосе «Просмотрено». */
    watchedCount: number;
    quality: string | null;
    voices: string[];
    voice: string;
    /** Число серий выбранного сезона у озвучек, которые уже загружались. */
    voiceEpisodes: Record<string, number>;
    /** Пока загружается серия, выбор недоступен. */
    busy: boolean;
    /** Отметки ставятся, только когда страницу можно записать в список. */
    canMark: boolean;
    onvoice: (name: string) => void;
    onseason: (id: string) => void;
    onepisode: (id: string) => void;
    ontoggle: (id: string, watched: boolean) => void;
    /** Кнопка «Смотреть» под сериями. */
    footer?: Snippet;
  }

  let { seasons, season, episode, watched, watchedCount, quality, voices, voice, voiceEpisodes, busy, canMark, onvoice, onseason, onepisode, ontoggle, footer }: Props = $props();

  const current = $derived(seasons.find((item) => item.id === season) ?? null);
  const episodes = $derived(current?.episodes ?? []);
  const marks = $derived(new Set(watched));
  const badges = $derived(Object.fromEntries(Object.entries(voiceEpisodes).map(([name, n]) => [name, `${n} эп.`])));

  function number(id: string, index: number): string {
    return /^\d+$/.test(id) ? id : String(index + 1);
  }

  /** «1 серия» у KinoGo — это только номер: название тогда не повторяется. */
  function name(label: string): string {
    return /^\d+\s*серия$/i.test(label.trim()) ? "Серия" : label;
  }

  function chooseSeason(label: string) {
    const found = seasons.find((item) => item.name === label);
    if (found) onseason(found.id);
  }
</script>

<aside class="panel" aria-label="Эпизоды">
  <header>
    <h2>Эпизоды</h2>
    {#if episodes.length}<span class="count">{watchedCount} / {episodes.length}</span>{/if}
  </header>

  {#if voices.length > 1}
    <Dropdown label="Озвучка" options={voices} value={voice} {badges} disabled={busy} onchange={onvoice} />
  {:else if voices.length === 1}
    <div class="voice" title="Озвучка">
      <span>{voices[0]}</span>
      {#if badges[voices[0]]}<span class="pill">{badges[voices[0]]}</span>{/if}
    </div>
  {/if}

  {#if seasons.length > 1}
    <Dropdown label="Сезон" options={seasons.map((item) => item.name)} value={current?.name ?? ""} disabled={busy} onchange={chooseSeason} />
  {/if}

  <ol>
    {#each episodes as item, index (item.id)}
      {@const done = marks.has(item.id)}
      <li class:current={item.id === episode} class:done>
        <button class="row" disabled={busy} aria-current={item.id === episode} onclick={() => item.id !== episode && onepisode(item.id)}>
          <span class="num">{number(item.id, index)}</span>
          <span class="name">{name(item.name)}</span>
          {#if quality && item.id === episode}<span class="q">{quality}</span>{/if}
        </button>
        <button
          class="check"
          aria-pressed={done}
          aria-label={done ? `Снять отметку: ${item.name}` : `Отметить просмотренной: ${item.name}`}
          disabled={!canMark}
          onclick={() => ontoggle(item.id, !done)}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <circle cx="10" cy="10" r="8.2" />
            {#if done}<path d="M6.2 10.3l2.5 2.5 5-5.4" />{/if}
          </svg>
        </button>
      </li>
    {:else}
      <li class="empty">Серии этого сезона появятся после загрузки.</li>
    {/each}
  </ol>

  {@render footer?.()}
</aside>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    height: var(--episodes-height, auto);
    max-height: var(--episodes-height, min(640px, calc(100vh - 160px)));
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 16px;
    background: var(--surface);
    align-self: start;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h2 {
    font-size: 16px;
    font-weight: 700;
  }

  .count {
    padding: 2px 9px;
    border: 1px solid rgb(244 63 94 / 45%);
    border-radius: 999px;
    background: rgb(244 63 94 / 14%);
    color: var(--accent);
    font-size: 12px;
    font-weight: 700;
  }

  .panel :global(.dropdown) {
    width: 100%;
  }

  .voice {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface-2);
    font-weight: 600;
  }

  .pill {
    padding: 1px 7px;
    border-radius: 6px;
    background: var(--border);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
  }

  ol {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0 -4px 0 0;
    padding: 0 4px 0 0;
    overflow-y: auto;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    border: 1px solid transparent;
    border-radius: 10px;
    background: var(--surface-2);
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  li:hover {
    border-color: var(--border);
  }

  li.current {
    border-color: rgb(244 63 94 / 55%);
    background: rgb(244 63 94 / 14%);
  }

  .row {
    display: flex;
    flex: 1;
    align-items: center;
    gap: 14px;
    min-width: 0;
    padding: 12px 6px 12px 14px;
    border: 0;
    background: none;
    text-align: left;
    cursor: pointer;
  }

  .row:disabled {
    cursor: default;
  }

  .num {
    min-width: 22px;
    color: var(--muted);
    font-size: 15px;
    font-weight: 700;
    text-align: center;
  }

  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .done .name {
    color: var(--muted);
    text-decoration: line-through;
  }

  .q {
    color: var(--muted);
    font-size: 11px;
  }

  .check {
    display: grid;
    place-items: center;
    padding: 10px 12px 10px 6px;
    border: 0;
    background: none;
    color: var(--muted);
    cursor: pointer;
  }

  .check:disabled {
    cursor: default;
    opacity: 0.5;
  }

  .check:hover:not(:disabled),
  .done .check {
    color: #4ade80;
  }

  svg {
    width: 22px;
    height: 22px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.6;
  }

  .empty {
    padding: 12px 14px;
    color: var(--muted);
    font-size: 13px;
  }
</style>

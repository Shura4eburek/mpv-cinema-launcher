<script lang="ts">
  import { onMount } from "svelte";
  import { api, onBackendEvent, type LampacState, type MirrorReport } from "../lib/api";
  import { describeLampacState, describeMirrorState, mirrorSummary, mirrorsAsText, sourceName } from "../lib/logic";

  interface Props {
    onclose: () => void;
  }

  let { onclose }: Props = $props();

  let query = $state("Довод");
  let rows = $state<MirrorReport[]>([]);
  let running = $state(false);
  let failed = $state(false);
  let copied = $state(false);
  let lampac = $state<LampacState | null>(null);
  let currentId: string | null = null;

  const summary = $derived(mirrorSummary(rows));

  function applyReport(report: MirrorReport) {
    const index = rows.findIndex((row) => row.site === report.site && row.url === report.url);
    if (index === -1) rows.push(report);
    else rows[index] = report;
  }

  async function run() {
    if (running || !query.trim()) return;
    const id = crypto.randomUUID();
    currentId = id;
    rows = [];
    running = true;
    failed = false;
    try {
      await api.mirrorCheck(query.trim(), id);
    } catch {
      failed = true;
    } finally {
      if (currentId === id) running = false;
    }
  }

  async function copyReport() {
    await api.copyText(mirrorsAsText(query, rows));
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    run();
  }

  onMount(() => {
    const stop = onBackendEvent(({ event, data }) => {
      if (event === "mirror_result" && data?.id === currentId && data.mirror) applyReport(data.mirror);
      if (event === "lampac_state" && data?.lampac) lampac = data.lampac;
    });
    run();
    api.lampacState().then((state) => (lampac = state)).catch(() => {});
    return () => {
      currentId = null;
      stop.then((unlisten) => unlisten());
    };
  });
</script>

<section>
  <header>
    <h1>Проверка зеркал</h1>
    <button class="btn" onclick={onclose}>Готово</button>
  </header>

  <p class="hint">Один поисковый запрос к каждому адресу, обычным запросом приложения, без браузера. Открытие фильма и поток здесь не проверяются.</p>

  <form onsubmit={submit}>
    <input bind:value={query} aria-label="Запрос для проверки" />
    <button class="btn primary" disabled={running || !query.trim()}>{running ? "Проверяем…" : "Проверить"}</button>
    <button type="button" class="btn ghost" disabled={running || rows.length === 0} onclick={copyReport}>
      {copied ? "Отчёт скопирован" : "Скопировать отчёт"}
    </button>
  </form>

  {#if failed}<p class="failed" role="alert">Проверка не запустилась. Попробуйте ещё раз.</p>{/if}
  {#if rows.length}<p class="summary" role="status">{summary}</p>{/if}
  {#if lampac?.available}<p class="summary">Lampac: {describeLampacState(lampac)}</p>{/if}

  <ul>
    {#each rows as row (`${row.site} ${row.url}`)}
      {@const view = describeMirrorState(row.state)}
      <li>
        <div class="line">
          <span class="badge {view.tone}">{view.label}</span>
          <strong>{row.url}</strong>
          <small>{sourceName(row.site)}</small>
        </div>
        {#if row.state !== "checking"}
          <dl>
            <div><dt>HTTP</dt><dd>{row.http ?? "нет ответа"}</dd></div>
            <div><dt>Время</dt><dd>{row.ms ?? "?"} мс</dd></div>
            {#if row.server}<div><dt>Сервер</dt><dd>{row.server}</dd></div>{/if}
            <div><dt>Карточек</dt><dd>{row.count}</dd></div>
            <div><dt>С запросом в названии</dt><dd>{row.matches}</dd></div>
            {#if row.first}<div class="wide"><dt>Первая карточка</dt><dd>{row.first}</dd></div>{/if}
            {#if row.first_url}<div class="wide"><dt>Адрес карточки</dt><dd>{row.first_url}</dd></div>{/if}
          </dl>
          {#if row.detail}<p class="detail">{row.detail}</p>{/if}
        {/if}
      </li>
    {/each}
  </ul>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-width: 960px;
    margin: 0 auto;
    animation: appear 0.25s var(--ease);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h1 {
    font-size: 28px;
    font-weight: 700;
  }

  .hint,
  .summary {
    color: var(--muted);
  }

  .failed {
    color: #fda4af;
  }

  form {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }

  input {
    flex: 1;
    min-width: 180px;
    padding: 9px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--input);
  }

  input:focus {
    border-color: var(--accent);
    outline: none;
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    user-select: text;
  }

  .line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }

  .line small {
    margin-left: auto;
    color: var(--muted);
  }

  .badge {
    padding: 2px 9px;
    border-radius: 999px;
    background: var(--surface-2);
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
  }

  .badge.good {
    background: rgb(34 197 94 / 16%);
    color: #86efac;
  }

  .badge.warn {
    background: rgb(234 179 8 / 16%);
    color: #fde047;
  }

  .badge.bad {
    background: rgb(244 63 94 / 16%);
    color: #fda4af;
  }

  dl {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 22px;
    margin: 10px 0 0;
  }

  dl > div {
    min-width: 0;
    max-width: 100%;
  }

  .wide {
    flex-basis: 100%;
  }

  dt {
    color: var(--muted);
    font-size: 12px;
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .detail {
    margin-top: 8px;
    color: var(--body);
  }
</style>

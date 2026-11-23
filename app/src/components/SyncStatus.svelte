<script lang="ts">
  import { onMount } from "svelte";
  import { api, onBackendEvent, syncFromEvent, type SyncState } from "../lib/api";
  import { canSyncNow, describeSync } from "../lib/logic";

  interface Props {
    /** Есть — в состоянии «нужно войти заново» показывается переход в Настройки. */
    onsettings?: () => void;
  }

  let { onsettings }: Props = $props();

  let sync = $state<SyncState | null>(null);
  let now = $state(new Date());
  let busy = $state(false);

  const text = $derived(describeSync(sync, now));
  const tone = $derived(
    sync?.state === "idle" ? "ok" : sync?.state === "syncing" ? "busy" : sync && ["offline", "auth_required", "error"].includes(sync.state) ? "warn" : "muted",
  );
  // Растёт с каждым событием: ответ, пришедший после события, уже устарел.
  let eventCount = 0;

  async function fetchState(action: () => Promise<SyncState>) {
    const seen = eventCount;
    try {
      const next = await action();
      if (seen === eventCount) sync = next;
    } catch {
      // Без входа sync_now отвечает ошибкой: состояние придёт событием или останется прежним.
    }
  }

  async function syncNow() {
    busy = true;
    await fetchState(api.syncNow);
    busy = false;
  }

  onMount(() => {
    fetchState(api.syncGet);
    const stop = onBackendEvent((event) => {
      const next = syncFromEvent(event);
      if (next) {
        eventCount += 1;
        sync = next;
      }
    });
    const tick = setInterval(() => (now = new Date()), 30_000);
    return () => {
      clearInterval(tick);
      stop.then((unlisten) => unlisten());
    };
  });
</script>

{#if sync && text}
  <div class="sync {tone}" role="status" aria-live="polite" aria-busy={sync.state === "syncing"}>
    <span class="dot" aria-hidden="true"></span>
    <span class="text" title={sync.state === "error" ? (sync.message ?? undefined) : undefined}>{text}</span>
    {#if sync.state === "auth_required" && onsettings}
      <button class="link" onclick={onsettings}>Войти</button>
    {:else if canSyncNow(sync)}
      <button class="link" disabled={busy} onclick={syncNow}>Синхронизировать</button>
    {/if}
  </div>
{/if}

<style>
  .sync {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: var(--muted);
    font-size: 13px;
  }

  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--muted);
  }

  .ok .dot {
    background: #4ade80;
  }

  .busy .dot {
    background: var(--accent, #60a5fa);
    animation: pulse 1s ease-in-out infinite;
  }

  .warn {
    color: #fda4af;
  }

  .warn .dot {
    background: #fb7185;
  }

  .text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .link {
    flex: none;
    padding: 0;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 3px;
    cursor: pointer;
  }

  .link:disabled {
    opacity: 0.5;
    cursor: default;
  }

  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .busy .dot {
      animation: none;
    }
  }
</style>

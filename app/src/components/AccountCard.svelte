<script lang="ts">
  import { onMount } from "svelte";
  import { convertFileSrc } from "@tauri-apps/api/core";
  import { accountFromEvent, api, errorCode, onBackendEvent, type AccountState } from "../lib/api";
  import { describeAccount, initials } from "../lib/logic";
  import SyncStatus from "./SyncStatus.svelte";

  let account = $state<AccountState | null>(null);
  let busy = $state(false);
  let failed = $state<string | null>(null);
  let avatarBroken = $state(false);

  const info = $derived(account?.account ?? null);
  const shown = $derived(account && ["signed_in", "offline", "restoring"].includes(account.state) ? info : null);
  const note = $derived(failed ?? describeAccount(account));
  // Файл аватара всегда один; email в адресе не даёт WebView показать картинку прошлого аккаунта.
  const avatar = $derived(
    shown?.avatar && !avatarBroken ? `${convertFileSrc(shown.avatar)}?v=${encodeURIComponent(shown.email)}` : null,
  );
  // Растёт с каждым событием: ответ, пришедший после события, уже устарел.
  let eventCount = 0;

  function update(next: AccountState) {
    if (next.account?.avatar !== account?.account?.avatar) avatarBroken = false;
    account = next;
  }

  async function run(action: () => Promise<AccountState>) {
    busy = true;
    failed = null;
    const seen = eventCount;
    try {
      const next = await action();
      if (seen === eventCount) update(next);
    } catch (error) {
      failed = errorCode(error) === "unconfigured" ? "Вход через Google не настроен в этой сборке." : "Не удалось связаться с приложением.";
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    run(api.accountGet);
    const stop = onBackendEvent((event) => {
      const next = accountFromEvent(event);
      if (next) {
        eventCount += 1;
        failed = null;
        update(next);
      }
    });
    return () => {
      stop.then((unlisten) => unlisten());
    };
  });
</script>

<div class="account" aria-busy={busy || account?.state === "pending" || account?.state === "restoring"}>
  {#if shown}
    <div class="who">
      {#if avatar}
        <img src={avatar} alt="" onerror={() => (avatarBroken = true)} />
      {:else}
        <span class="initials" aria-hidden="true">{initials(shown.name, shown.email)}</span>
      {/if}
      <span class="text">
        <strong>{shown.name || shown.email || "Аккаунт Google"}</strong>
        {#if shown.name && shown.email}<small>{shown.email}</small>{/if}
      </span>
    </div>
    <button class="btn" disabled={busy || account?.state === "restoring"} onclick={() => run(api.accountSignOut)}>Выйти</button>
  {:else if account?.state === "pending"}
    <span class="text"><strong>Ожидание входа…</strong></span>
    <button class="btn" onclick={() => run(api.accountCancel)}>Отмена</button>
  {:else}
    <span class="text">
      <strong>Вход не выполнен</strong>
      <small>Нужен для синхронизации «Моего списка». Без входа приложение работает как обычно.</small>
    </span>
    <button class="btn primary" disabled={busy || !account || account.state === "unconfigured"} onclick={() => run(api.accountSignIn)}>
      Войти через Google
    </button>
  {/if}
</div>
{#if note}
  <small class="note" class:warn={account?.state === "expired" || account?.state === "offline" || !!failed} role="status">{note}</small>
{/if}
{#if account && ["signed_in", "offline", "expired"].includes(account.state)}
  <div class="sync"><SyncStatus /></div>
{/if}
{#if account?.storage_warning && shown}
  <small class="note warn" role="status">Системное хранилище паролей недоступно: вход не сохранится после закрытия приложения.</small>
{/if}

<style>
  .account {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .who {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  img,
  .initials {
    flex: none;
    width: 40px;
    height: 40px;
    border-radius: 50%;
  }

  img {
    object-fit: cover;
  }

  .initials {
    display: grid;
    place-items: center;
    background: var(--surface-2);
    color: var(--text);
    font-weight: 600;
  }

  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .text strong,
  .text small {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  small {
    color: var(--muted);
    font-size: 13px;
  }

  .sync {
    margin-top: 8px;
  }

  .note.warn {
    color: #fda4af;
  }

  .btn {
    flex: none;
  }
</style>

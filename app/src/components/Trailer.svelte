<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { api, errorCode, type TrailerVideo } from "../lib/api";

  const PLAYER_ORIGIN = "https://www.youtube-nocookie.com";
  const LISTEN_RETRY_MS = 500;

  interface Props {
    title: string;
    year: string | null;
    onclose: () => void;
  }

  let { title, year, onclose }: Props = $props();

  let videos = $state<TrailerVideo[]>([]);
  let index = $state(0);
  let failure = $state<string | null>(null);
  let loading = $state(true);
  let frame = $state<HTMLIFrameElement>();
  let dialog: HTMLDivElement;
  let listenTimer: ReturnType<typeof setInterval> | undefined;

  const video = $derived(videos[index] ?? null);
  const src = $derived(
    video
      // Без автозапуска: автозапущенный ролик плеер держит без звука и глушит снова даже после unMute.
      ? `${PLAYER_ORIGIN}/embed/${video.id}?enablejsapi=1&rel=0&origin=${encodeURIComponent(location.origin)}`
      : null,
  );

  function nextVideo() {
    if (index + 1 < videos.length) index += 1;
    else failure = "Этот трейлер нельзя показать в приложении.";
  }

  // Плеер может подключить свой обработчик уже после загрузки, поэтому просьба повторяется до первого ответа.
  function listen() {
    clearInterval(listenTimer);
    const ask = () =>
      frame?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), PLAYER_ORIGIN);
    ask();
    listenTimer = setInterval(ask, LISTEN_RETRY_MS);
  }

  function onMessage(event: MessageEvent) {
    if (event.origin !== PLAYER_ORIGIN || event.source !== frame?.contentWindow) return;
    clearInterval(listenTimer);
    try {
      // Коды 101 и 150: владелец запретил показ вне YouTube.
      if (JSON.parse(event.data).event === "onError") nextVideo();
    } catch {
      // Плеер присылает и другие сообщения, не только JSON.
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && !document.fullscreenElement) onclose();
  }

  // Клавиши не доходят до окна, пока фокус в чужом плеере, и Esc перестал бы работать.
  // Фокус на самом окне трейлера, а не на кнопке: иначе пробел после щелчка по плееру закрыл бы его.
  function keepFocus() {
    setTimeout(() => {
      if (document.activeElement === frame && !document.fullscreenElement) dialog?.focus();
    });
  }

  function openInBrowser() {
    api.openTrailerSearch(title, year).catch(() => {});
  }

  function closeOutside(event: MouseEvent) {
    if (event.target === event.currentTarget) onclose();
  }

  onDestroy(() => clearInterval(listenTimer));

  onMount(() => {
    dialog.focus();
    api
      .trailer(title, year)
      .then((result) => (videos = result.videos))
      .catch((error) => {
        failure = errorCode(error) === "not_found" ? "Трейлер не найден." : "Не удалось найти трейлер. Проверьте подключение к интернету.";
      })
      .finally(() => (loading = false));
  });
</script>

<svelte:window onmessage={onMessage} onkeydown={onKeydown} onblur={keepFocus} />
<svelte:document onfullscreenchange={keepFocus} />

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="overlay" onclick={closeOutside}>
  <div bind:this={dialog} class="dialog" role="dialog" aria-modal="true" aria-label={`Трейлер: ${title}`} tabindex="-1">
    <header>
      <strong>{video && !failure ? video.title : `Трейлер: ${title}`}</strong>
      <button class="btn ghost" onclick={openInBrowser}>Открыть в браузере</button>
      <button class="btn ghost" aria-label="Закрыть трейлер" onclick={onclose}>✕</button>
    </header>
    <div class="screen">
      {#if failure}
        <div class="state" role="alert">
          <p>{failure}</p>
          <button class="btn" onclick={openInBrowser}>Искать в браузере</button>
        </div>
      {:else if loading}
        <div class="state"><div class="spinner"></div></div>
      {:else if src}
        {#key src}
          <iframe
            bind:this={frame}
            {src}
            title={video?.title}
            allow="encrypted-media; fullscreen"
            referrerpolicy="strict-origin-when-cross-origin"
            onload={listen}
          ></iframe>
        {/key}
      {/if}
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 90;
    display: grid;
    place-items: center;
    padding: 24px;
    background: rgb(0 0 0 / 86%);
    animation: fade 0.2s var(--ease);
  }

  .dialog {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(1280px, 100%, calc((100vh - 110px) * 16 / 9));
    min-width: 0;
    outline: none;
  }

  header {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  strong {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .screen {
    aspect-ratio: 16 / 9;
    overflow: hidden;
    border-radius: var(--radius);
    background: #000;
  }

  iframe {
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
  }

  .state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
    height: 100%;
    padding: 24px;
    text-align: center;
  }
</style>

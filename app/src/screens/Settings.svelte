<script lang="ts">
  import type { Device, LampacState, UserSettings } from "../lib/api";
  import { describeDevice, describeLampacState } from "../lib/logic";
  import AccountCard from "../components/AccountCard.svelte";

  interface Props {
    settings: UserSettings;
    upscaleReady: boolean | null;
    device: Device | null;
    onchange: (changes: Partial<UserSettings>) => void;
    onclose: () => void;
    onmirrors: () => void;
    lampac: LampacState | null;
  }

  let { settings, upscaleReady, device, onchange, onclose, onmirrors, lampac }: Props = $props();

  const windows = navigator.userAgent.includes("Windows");

  const presetOptions = [
    { value: "auto", title: "Авто", text: "Приложение выберет вариант по вашей видеокарте." },
    { value: "high", title: "High", text: "Самая качественная обработка: RTX VSR или нейросеть. Для мощных видеокарт." },
    { value: "mid", title: "Mid", text: "Облегчённая нейросетевая обработка. Для средних видеокарт." },
    { value: "low", title: "Low", text: "Без нейросети. Для встроенных и старых видеокарт." },
  ] as const;

  const content = [
    { value: "film", title: "Фильмы и сериалы", text: "Естественная чёткость для снятого видео." },
    { value: "anime", title: "Аниме", text: "Чистые линии для рисованной анимации." },
  ] as const;

</script>

<section>
  <header>
    <h1>Настройки</h1>
    <button class="btn" onclick={onclose}>Готово</button>
  </header>

  {#if upscaleReady === false}
    <p class="notice">Файлы для улучшения картинки ещё не загружены. Фильм запустится, но без нейросетевого увеличения.</p>
  {/if}

  <h2>Аккаунт Google</h2>
  <AccountCard />

  <h2>Производительность</h2>
  <div class="options presets">
    {#each presetOptions as item (item.value)}
      <button
        class:active={settings.preset === item.value}
        aria-pressed={settings.preset === item.value}
        onclick={() => onchange({ preset: item.value })}
      >
        <strong>{item.title}</strong><small>{item.text}</small>
      </button>
    {/each}
  </div>
  {#if settings.preset === "auto"}
    <p class="device">{describeDevice(device)}</p>
  {/if}

  <h2>Что смотрите чаще</h2>
  <div class="options">
    {#each content as item (item.value)}
      <button
        class:active={settings.content === item.value}
        aria-pressed={settings.content === item.value}
        onclick={() => onchange({ content: item.value })}
      >
        <strong>{item.title}</strong><small>{item.text}</small>
      </button>
    {/each}
  </div>

  <h2>Движение</h2>
  <label class="switch">
    <input
      type="checkbox"
      checked={settings.interpolation}
      onchange={(event) => onchange({ interpolation: event.currentTarget.checked })}
    />
    <span><strong>Плавное движение</strong><small>Подстраивает кадры под частоту монитора и убирает рывки.</small></span>
  </label>

  <h2>Адрес основного источника</h2>
  <input
    class="address"
    type="url"
    value={settings.kinogo_url}
    aria-label="Адрес основного источника"
    onchange={(event) => onchange({ kinogo_url: event.currentTarget.value.trim() })}
  />

  {#if windows}
    <h2>Плеер</h2>
    <label class="switch">
      <input
        type="checkbox"
        checked={settings.embedded_player}
        onchange={(event) => onchange({ embedded_player: event.currentTarget.checked })}
      />
      <span>
        <strong>Плеер на странице фильма</strong>
        <small>Экспериментально. Видео идёт прямо на странице, а не в отдельном окне.</small>
      </span>
    </label>
  {/if}

  {#if lampac?.available}
    <h2>Дополнительные источники</h2>
    <label class="switch">
      <input
        type="checkbox"
        checked={settings.lampac_enabled}
        onchange={(event) => onchange({ lampac_enabled: event.currentTarget.checked })}
      />
      <span>
        <strong>Lampac</strong>
        <small>Больше источников и озвучек на странице фильма. Пока включён, использует около 400 МБ памяти.</small>
        <small class:failed={lampac.state === "error"} role="status">{describeLampacState(lampac)}</small>
      </span>
    </label>
  {/if}

  <h2>Диагностика</h2>
  <button class="btn mirrors" onclick={onmirrors}>Проверить зеркала</button>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-width: 720px;
    margin: 0 auto;
    animation: appear 0.25s var(--ease);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  small.failed {
    color: #fda4af;
  }

  .mirrors {
    align-self: flex-start;
  }

  h1 {
    font-size: 28px;
    font-weight: 700;
  }

  h2 {
    margin-top: 16px;
    color: var(--muted);
    font-size: 13px;
    font-weight: 600;
  }

  .notice {
    padding: 12px 14px;
    border-radius: 10px;
    background: rgb(244 63 94 / 12%);
    color: #fda4af;
  }

  .device {
    color: var(--muted);
    font-size: 13px;
  }

  .presets {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }

  .options {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 10px;
  }

  .options button,
  .switch {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.15s,
      background 0.15s;
  }

  .options button:hover,
  .switch:hover {
    background: var(--surface-2);
  }

  .options button.active {
    border-color: var(--accent);
    background: rgb(244 63 94 / 8%);
  }

  small {
    color: var(--muted);
    font-size: 13px;
  }

  .switch {
    flex-direction: row;
    align-items: center;
    gap: 14px;
  }

  .switch span {
    display: flex;
    flex-direction: column;
  }

  .switch input {
    width: 18px;
    height: 18px;
    accent-color: var(--accent);
  }

  .address {
    width: min(420px, 100%);
    padding: 9px 12px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--input);
  }

</style>

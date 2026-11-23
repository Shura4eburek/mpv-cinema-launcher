<script lang="ts">
  import { tick } from "svelte";

  interface Props {
    label: string;
    options: string[];
    value: string;
    disabled?: boolean;
    /** Метка-пилюля рядом с вариантом, например число серий у озвучки. */
    badges?: Record<string, string>;
    onchange: (value: string) => void;
  }

  let { label, options, value, disabled = false, badges = {}, onchange }: Props = $props();

  const listId = `dropdown-${crypto.randomUUID()}`;
  let open = $state(false);
  let active = $state(0);
  let root: HTMLDivElement;
  let list = $state<HTMLUListElement>();

  async function show() {
    active = Math.max(0, options.indexOf(value));
    open = true;
    await tick();
    list?.children[active]?.scrollIntoView({ block: "nearest" });
    // Список у нижнего края окна: страница прокручивается так, чтобы он был виден целиком.
    list?.scrollIntoView({ block: "nearest" });
  }

  function choose(option: string) {
    open = false;
    if (option !== value) onchange(option);
  }

  async function move(index: number) {
    active = Math.min(options.length - 1, Math.max(0, index));
    await tick();
    list?.children[active]?.scrollIntoView({ block: "nearest" });
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === "Tab") {
      open = false;
      return;
    }
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        show();
      }
      return;
    }
    const actions: Record<string, () => void> = {
      ArrowDown: () => move(active + 1),
      ArrowUp: () => move(active - 1),
      Home: () => move(0),
      End: () => move(options.length - 1),
      Enter: () => choose(options[active]),
      " ": () => choose(options[active]),
      Escape: () => (open = false),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  }

  function closeOutside(event: PointerEvent) {
    if (open && !root.contains(event.target as Node)) open = false;
  }
</script>

<svelte:window onpointerdown={closeOutside} />

<div class="dropdown" bind:this={root}>
  <button
    type="button"
    class="trigger"
    class:open
    role="combobox"
    aria-label={label}
    aria-expanded={open}
    aria-haspopup="listbox"
    aria-controls={listId}
    aria-activedescendant={open ? `${listId}-${active}` : undefined}
    {disabled}
    onclick={() => (open ? (open = false) : show())}
    {onkeydown}
  >
    <span class="value">{value}</span>
    {#if badges[value]}<span class="pill">{badges[value]}</span>{/if}
    <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>
  </button>

  {#if open}
    <ul bind:this={list} id={listId} role="listbox" aria-label={label}>
      {#each options as option, index (option)}
        <!-- Клавиатурой список управляется через кнопку, фокус остаётся на ней. -->
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <li
          id={`${listId}-${index}`}
          role="option"
          aria-selected={option === value}
          class:active={index === active}
          onpointermove={() => (active = index)}
          onclick={() => choose(option)}
        >
          <span class="name">{option}</span>
          {#if badges[option]}<span class="pill">{badges[option]}</span>{/if}
          {#if option === value}
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" /></svg>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .dropdown {
    position: relative;
    width: min(320px, 100%);
    min-width: 200px;
  }

  .trigger {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    padding: 9px 12px 9px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface-2);
    text-align: left;
    cursor: pointer;
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  .trigger:hover:not(:disabled) {
    background: var(--hover);
    border-color: var(--hover-border);
  }

  .trigger.open {
    border-color: var(--accent);
  }

  .trigger:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .value {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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

  .trigger svg {
    color: var(--muted);
    transition: transform 0.2s var(--ease);
  }

  .trigger.open svg {
    transform: rotate(180deg);
  }

  ul {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 20;
    width: 100%;
    max-height: 300px;
    margin: 0;
    padding: 5px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--popover);
    box-shadow: 0 18px 40px rgb(0 0 0 / 55%);
    list-style: none;
    animation: appear 0.15s var(--ease);
  }

  .pill {
    flex: none;
    padding: 1px 7px;
    border-radius: 6px;
    background: var(--border);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
  }

  li .name {
    flex: 1;
    min-width: 0;
  }

  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 8px 10px;
    border-radius: 8px;
    cursor: pointer;
  }

  li.active {
    background: var(--surface-2);
  }

  li[aria-selected="true"] {
    font-weight: 600;
  }

  li svg {
    color: var(--accent);
  }
</style>

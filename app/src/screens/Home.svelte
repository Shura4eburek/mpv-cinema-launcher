<script lang="ts">
  import { onMount } from "svelte";

  interface Props {
    onsearch: (query: string) => void;
  }

  let { onsearch }: Props = $props();
  let query = $state("");
  let input: HTMLInputElement;

  onMount(() => input.focus());

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (query.trim()) onsearch(query.trim());
  }
</script>

<section>
  <h1>Что посмотрим?</h1>
  <p>Найдите фильм и смотрите его в высоком качестве с плавным движением.</p>
  <form onsubmit={submit}>
    <input bind:this={input} bind:value={query} placeholder="Например, Довод или Интерстеллар" />
    <button class="btn primary" disabled={!query.trim()}>Найти</button>
  </form>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    height: 100%;
    min-height: 340px;
    padding-bottom: 8vh;
    text-align: center;
    animation: appear 0.3s var(--ease);
  }

  h1 {
    font-size: 40px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  p {
    color: var(--muted);
  }

  form {
    display: flex;
    gap: 10px;
    width: min(600px, 100%);
    margin-top: 16px;
    view-transition-name: search-field;
  }

  input {
    flex: 1;
    min-width: 0;
    padding: 12px 16px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--input);
  }

  input:focus {
    border-color: var(--accent);
    outline: none;
  }
</style>

<script lang="ts">
  import type { Badge } from "../lib/logic";

  interface Props {
    badges: Badge[];
  }

  let { badges }: Props = $props();
</script>

{#if badges.length}
  <ul class="badges" aria-label="Коротко о тайтле">
    {#each badges as badge, index (badge.label + index)}
      <li class={badge.tone}>
        {#if badge.tone === "rating"}<span aria-hidden="true">★</span>{/if}
        {#if badge.tone === "outline"}<span class="box">{badge.label}</span>{:else}{badge.label}{/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .badges {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 0;
    margin: 0;
    padding: 0;
    color: var(--muted);
    font-size: 14px;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  /* Разделитель «|» между всеми бейджами, как у сайта (и перед рамкой возраста). */
  li + li::before {
    content: "";
    width: 1px;
    height: 14px;
    margin: 0 10px;
    background: var(--border);
  }

  .rating {
    color: #4ade80;
    font-weight: 700;
  }

  .box {
    padding: 1px 6px;
    border: 1px solid var(--hover-border);
    border-radius: 5px;
    font-size: 12px;
  }
</style>

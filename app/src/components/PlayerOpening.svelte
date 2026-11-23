<script lang="ts">
  interface Props {
    oncancel: () => void;
  }

  let { oncancel }: Props = $props();
  let button: HTMLButtonElement;

  $effect(() => {
    button.focus();
  });
</script>

<div class="overlay" role="alertdialog" aria-modal="true" aria-label="Открываем плеер">
  <div class="spinner"></div>
  <h2>Открываем плеер</h2>
  <button bind:this={button} class="btn" onclick={oncancel}>Отменить</button>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 18px;
    background: rgb(0 0 0 / 92%);
    animation: appear 0.15s var(--ease);
  }

  h2 {
    font-size: 22px;
    font-weight: 600;
  }

  .spinner {
    width: 44px;
    height: 44px;
    border-width: 4px;
  }

  button {
    margin-top: 10px;
  }
</style>

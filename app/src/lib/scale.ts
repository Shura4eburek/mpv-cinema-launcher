// Масштаб интерфейса: вёрстка рассчитана на окно до 1800×1000, больше — всё пропорционально крупнее.
const BASE_WIDTH = 1800;
const BASE_HEIGHT = 1000;
const MAX_SCALE = 1.75;

export function uiScale(width: number, height: number): number {
  const scale = Math.min(width / BASE_WIDTH, height / BASE_HEIGHT);
  return Math.round(Math.min(MAX_SCALE, Math.max(1, scale)) * 100) / 100;
}

export function watchWindowScale() {
  const apply = () => {
    document.documentElement.style.zoom = String(uiScale(window.innerWidth, window.innerHeight));
  };
  apply();
  window.addEventListener("resize", apply);
}

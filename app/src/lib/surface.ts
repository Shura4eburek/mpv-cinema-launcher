// Область видео на странице: дочернее окно, в которое рисует встроенный mpv (contracts/player-surface.md).
import { invoke } from "@tauri-apps/api/core";

export interface SurfaceRect {
  x: number;
  y: number;
  width: number;
  height: number;
  clip_top: number;
}

export const surface = {
  create: () => invoke<number>("player_surface_create"),
  show: (rect: SurfaceRect) => invoke<void>("player_surface_show", { rect }),
  move: (rect: SurfaceRect) => invoke<void>("player_surface_move", { rect }),
  hide: () => invoke<void>("player_surface_hide"),
  fullscreen: (on: boolean) => invoke<void>("player_surface_fullscreen", { on }),
};

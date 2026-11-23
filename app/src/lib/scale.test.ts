import { describe, expect, it } from "vitest";
import { uiScale } from "./scale";

describe("uiScale", () => {
  it("не уменьшает интерфейс в обычном окне", () => {
    expect(uiScale(1000, 700)).toBe(1);
    expect(uiScale(1240, 820)).toBe(1);
  });

  it("растёт на большом экране", () => {
    expect(uiScale(1920, 1080)).toBe(1.07);
    expect(uiScale(2560, 1440)).toBe(1.42);
  });

  it("ограничен сверху", () => {
    expect(uiScale(3840, 2160)).toBe(1.75);
  });

  it("на сверхшироком окне считает по высоте", () => {
    expect(uiScale(3440, 1000)).toBe(1);
  });
});

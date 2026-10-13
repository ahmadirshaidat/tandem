import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = "tandem_csrf=; max-age=0";
  localStorage.clear();
});
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi
    .fn()
    .mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
});

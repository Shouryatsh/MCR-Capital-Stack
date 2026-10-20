import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Pages now load in a chain (entity list, then the panel, then its data); give async queries headroom on a loaded machine.
configure({ asyncUtilTimeout: 5000 });

// Recharts' ResponsiveContainer and framer-motion need these browser APIs that jsdom lacks.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = RO as unknown as typeof ResizeObserver;
window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

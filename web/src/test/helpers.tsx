import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { routes } from "./fixtures";

export type Handler = (path: string, init?: RequestInit) => { status?: number; body: unknown } | undefined;

/** Stubs fetch with API-shaped fixtures; `handler` can override any request (status codes, PUT/POST bodies). */
export function mockApi(overrides: Record<string, unknown> = {}, handler?: Handler) {
  const table = { ...routes, ...overrides };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = decodeURIComponent(String(url).replace(/^\/api/, "")).split("?")[0];
    const custom = handler?.(path, init);
    const body = custom ? custom.body : table[path];
    const status = custom?.status ?? (body === undefined ? 404 : 200);
    return { ok: status < 400, status, statusText: "err", json: async () => (body === undefined ? { detail: "not found" } : body) } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const renderApp = (path = "/") => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

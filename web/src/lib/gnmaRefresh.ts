import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { RefreshContext } from "./hooks";
import type { RefreshStatus } from "./types";

/** Starts the server-side GNMA download + extraction and polls until it finishes, then refreshes all data. */
export function useGnmaRefresh() {
  const { bump } = useContext(RefreshContext);
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const poll = useCallback(async () => {
    try {
      const s = await api<RefreshStatus>("/gnma/refresh");
      if (!alive.current) return;
      setStatus(s);
      if (s.running) timer.current = setTimeout(poll, 1500);
      else {
        if (s.error) setError(s.error);
        bump();
      }
    } catch (e) {
      if (alive.current) setError(e instanceof ApiError ? e.message : String(e));
    }
  }, [bump]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const s = await api<RefreshStatus>("/gnma/refresh", { method: "POST" });
      setStatus(s);
    } catch (e) {
      // 409 = a refresh is already running: just follow it
      if (!(e instanceof ApiError && e.status === 409)) {
        setError(e instanceof ApiError ? e.message : String(e));
        return;
      }
    }
    poll();
  }, [poll]);

  return { start, status, error, running: !!status?.running };
}

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError } from "./api";

/** Bumped by the top-bar refresh button; every useApi call re-fetches when it changes. */
export const RefreshContext = createContext<{ key: number; bump: () => void }>({ key: 0, bump: () => {} });

/** The reporting period shared by the top bar and the Overview / Summary pages. */
export const PeriodContext = createContext<{ period: string | null; setPeriod: (p: string) => void }>({ period: null, setPeriod: () => {} });
export const usePeriod = () => useContext(PeriodContext);

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(path: string | null): ApiState<T> {
  const { key } = useContext(RefreshContext);
  const [state, setState] = useState<{ data: T | null; error: ApiError | null; loading: boolean }>({ data: null, error: null, loading: !!path });
  const [local, setLocal] = useState(0);
  const reload = useCallback(() => setLocal((n) => n + 1), []);

  useEffect(() => {
    if (!path) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let live = true;
    setState((s) => ({ ...s, error: null, loading: true }));
    api<T>(path)
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((e) => live && setState({ data: null, error: e instanceof ApiError ? e : new ApiError(0, String(e)), loading: false }));
    return () => {
      live = false;
    };
  }, [path, key, local]);

  return { ...state, reload };
}

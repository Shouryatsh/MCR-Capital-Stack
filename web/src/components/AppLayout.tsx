import { MotionConfig } from "framer-motion";
import { useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useOutlet } from "react-router-dom";
import { getToken } from "../lib/api";
import { PeriodContext, RefreshContext, useApi } from "../lib/hooks";
import type { Meta } from "../lib/types";
import { AuroraBackground } from "./AuroraBackground";
import { ErrorState } from "./States";
import { MobileDrawer, SidebarNavigation } from "./SidebarNavigation";
import { NAV } from "./nav";
import { TokenGate } from "./TokenGate";
import { TopNavigation } from "./TopNavigation";

export function AppLayout() {
  const { pathname } = useLocation();
  const item = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to))) ?? NAV[0];
  const [refreshKey, setRefreshKey] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [period, setPeriod] = useState<string | null>(null);
  const [gateKey, setGateKey] = useState(0);

  const refresh = useMemo(() => ({ key: refreshKey + gateKey, bump: () => setRefreshKey((k) => k + 1) }), [refreshKey, gateKey]);
  return (
    <RefreshContext.Provider value={refresh}>
      <Shell item={item} pathname={pathname} collapsed={collapsed} setCollapsed={setCollapsed} drawer={drawer} setDrawer={setDrawer}
        period={period} setPeriod={setPeriod} onToken={() => setGateKey((k) => k + 1)} />
    </RefreshContext.Provider>
  );
}

function Shell({ item, pathname, collapsed, setCollapsed, drawer, setDrawer, period, setPeriod, onToken }: {
  item: (typeof NAV)[number]; pathname: string; collapsed: boolean; setCollapsed: (f: (c: boolean) => boolean) => void;
  drawer: boolean; setDrawer: (o: boolean) => void; period: string | null; setPeriod: (p: string) => void; onToken: () => void;
}) {
  const meta = useApi<Meta>("/meta");
  // Captured per render so an exiting page keeps showing ITS content instead of re-rendering with the next route's.
  const outlet = useOutlet();
  const { bump } = useContext(RefreshContext);
  const periods = meta.data?.periods ?? [];
  const effective = period && periods.includes(period) ? period : (periods[0] ?? null);

  useEffect(() => setDrawer(false), [pathname, setDrawer]);

  if (meta.error?.status === 401) return <><AuroraBackground /><TokenGate onSubmit={onToken} rejected={!!getToken()} /></>;

  return (
    <MotionConfig reducedMotion="user">
      <AuroraBackground />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded-lg focus:bg-ink-800 focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="flex min-h-dvh">
        <SidebarNavigation collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        <MobileDrawer open={drawer} onClose={() => setDrawer(false)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopNavigation
            item={item}
            meta={meta.data}
            refreshing={meta.loading}
            failed={!!meta.error}
            period={effective}
            onPeriod={setPeriod}
            onRefresh={bump}
            onMenu={() => setDrawer(true)}
          />
          <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-3 py-5 lg:pr-3">
            <PeriodContext.Provider value={{ period: effective, setPeriod }}>
              {meta.error ? (
                <ErrorState error={meta.error} onRetry={meta.reload} />
              ) : (
                // CSS enter animation only: the new page mounts immediately, so a transition can never leave the screen blank.
                <div key={pathname} className="page-enter">{outlet}</div>
              )}
            </PeriodContext.Provider>
          </main>
        </div>
      </div>
    </MotionConfig>
  );
}

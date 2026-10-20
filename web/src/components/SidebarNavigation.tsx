import { motion } from "framer-motion";
import { ChevronsLeft, ChevronsRight, ExternalLink, Settings, X } from "lucide-react";
import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { cx } from "./GlassCard";
import { NAV, streamlitUrl } from "./nav";

export function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-3 px-1">
      <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-aurora-teal to-aurora-violet text-sm font-bold text-ink-950 shadow-[0_0_24px_-4px_rgb(45_212_191/0.6)]" aria-hidden="true">
        M
      </div>
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <p className="truncate text-sm font-semibold">MCR Dashboard</p>
          <p className="truncate text-[11px] text-subtle">Capital &amp; exposure analytics</p>
        </div>
      )}
    </div>
  );
}

function NavList({ collapsed, onNavigate, idSuffix = "side" }: { collapsed?: boolean; onNavigate?: () => void; idSuffix?: string }) {
  return (
    <nav aria-label="Primary" className="mt-6 flex-1">
      <ul className="space-y-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              onClick={onNavigate}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                cx(
                  "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive ? "text-fg" : "text-muted hover:bg-white/5 hover:text-fg",
                  collapsed && "justify-center",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.span
                      layoutId={`nav-active-${idSuffix}`}
                      className="absolute inset-0 rounded-xl border border-aurora-teal/30 bg-gradient-to-r from-aurora-teal/20 via-aurora-cyan/10 to-aurora-violet/10 shadow-[0_0_28px_-8px_rgb(45_212_191/0.55)]"
                      transition={{ type: "spring", stiffness: 420, damping: 36 }}
                    />
                  )}
                  <Icon className={cx("relative size-[18px] shrink-0", isActive && "text-aurora-teal")} aria-hidden="true" />
                  <span className={cx("relative truncate", collapsed && "sr-only")}>{label}</span>
                  {isActive && <span className="sr-only">(current page)</span>}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function UtilityLinks({ collapsed }: { collapsed?: boolean }) {
  return (
    <a
      href={streamlitUrl()}
      target="_blank"
      rel="noreferrer"
      title="Uploads and Settings live in the Streamlit app"
      className={cx("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted hover:bg-white/5 hover:text-fg", collapsed && "justify-center")}
    >
      <Settings className="size-[18px] shrink-0" aria-hidden="true" />
      <span className={cx("truncate", collapsed && "sr-only")}>Uploads &amp; settings</span>
      {!collapsed && <ExternalLink className="ml-auto size-3.5" aria-hidden="true" />}
      <span className="sr-only"> (opens the Streamlit app)</span>
    </a>
  );
}

export function SidebarNavigation({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 76 : 248 }}
      transition={{ duration: 0.22, ease: "easeInOut" }}
      className="glass sticky top-0 m-3 mr-0 hidden h-[calc(100dvh-1.5rem)] shrink-0 flex-col overflow-hidden p-3 lg:flex"
      data-testid="sidebar"
      data-collapsed={collapsed}
    >
      <Brand collapsed={collapsed} />
      <NavList collapsed={collapsed} />
      <UtilityLinks collapsed={collapsed} />
      <button
        type="button"
        onClick={onToggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        className={cx("mt-2 flex items-center gap-3 rounded-xl px-3 py-2 text-xs text-subtle hover:bg-white/5 hover:text-fg", collapsed && "justify-center")}
      >
        {collapsed ? <ChevronsRight className="size-4" aria-hidden="true" /> : <ChevronsLeft className="size-4" aria-hidden="true" />}
        {!collapsed && "Collapse"}
      </button>
    </motion.aside>
  );
}

export function MobileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  // Enter animation is CSS (disabled under prefers-reduced-motion); closing is immediate so it can never get stuck.
  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
      <div className="scrim-enter absolute inset-0 bg-ink-950/70 backdrop-blur-sm" onClick={onClose} />
      <div className="drawer-enter glass absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col rounded-l-none p-4">
        <div className="flex items-center justify-between">
          <Brand />
          <button type="button" onClick={onClose} aria-label="Close menu" className="rounded-lg p-2 text-muted hover:bg-white/5">
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
        <NavList onNavigate={onClose} idSuffix="drawer" />
        <UtilityLinks />
      </div>
    </div>
  );
}


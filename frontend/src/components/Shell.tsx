import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useLocation } from "react-router-dom";
import {
  IconActivity, IconCog, IconDevice, IconDollar, IconGrid, IconHome, IconKey, IconKeyboard, IconLogout, IconMessages,
  IconMore, IconMoon, IconSearch, IconSun, IconX,
} from "../icons";
import { useFocusTrap } from "../util/hooks";
import { useTheme } from "../theme";
import type { CurrentUser } from "../types";
import { Brand } from "./Brand";
import { Menu } from "./Menu";
import { useCommands } from "./Palette";
import { useToast } from "./Toast";

const TABS: Array<{ to: string; label: string; icon: ReactNode }> = [
  { to: "/", label: "Home", icon: <IconHome /> },
  { to: "/analytics", label: "Analytics", icon: <IconActivity /> },
  { to: "/billing", label: "Billing", icon: <IconDollar /> },
  { to: "/keys", label: "Keys", icon: <IconKey /> },
  { to: "/conversations", label: "Sessions", icon: <IconMessages /> },
  { to: "/models", label: "Models", icon: <IconGrid /> },
  { to: "/settings", label: "Settings", icon: <IconCog /> },
];

const mac = typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);

function Needle({ tabs }: { tabs: React.RefObject<HTMLElement> }) {
  const ref = useRef<HTMLSpanElement>(null);
  const loc = useLocation();
  useLayoutEffect(() => {
    const place = (animate: boolean) => {
      const bar = tabs.current;
      const needle = ref.current;
      if (!bar || !needle) return;
      const on = bar.querySelector<HTMLElement>(".tab.active");
      needle.style.transition = animate ? "" : "none";
      if (!on) { needle.dataset.idle = "true"; return; }
      needle.dataset.idle = "false";
      needle.style.setProperty("--nx", `${on.offsetLeft + 12}px`);
      needle.style.setProperty("--nw", String((on.offsetWidth - 24) / 100));
    };
    place(ref.current?.dataset.placed === "1");
    if (ref.current) ref.current.dataset.placed = "1";
    const ro = new ResizeObserver(() => place(false));
    if (tabs.current) ro.observe(tabs.current);
    document.fonts?.ready.then(() => place(false));
    return () => ro.disconnect();
  }, [loc.pathname, tabs]);
  return <span ref={ref} className="needle" data-idle="true" aria-hidden="true" />;
}

export function TopBar({ user }: { user: CurrentUser }) {
  const tabs = useRef<HTMLElement>(null);
  const [theme, toggleTheme] = useTheme();
  const { openPalette, openShortcuts } = useCommands();
  const toast = useToast();
  const initials = (user.name || user.email || "?").charAt(0).toUpperCase();
  const host = window.location.host;

  const copyHub = async () => {
    try { await navigator.clipboard.writeText(window.location.origin); } catch { /* clipboard can be blocked */ }
    toast("Copied hub URL");
  };

  return (
    <header className="bar">
      <div className="bar-in">
        <Brand />
        <nav className="tabs" aria-label="Primary" ref={tabs}>
          {TABS.map(t => (
            <NavLink key={t.to} to={t.to} end={t.to === "/"} className={({ isActive }) => `tab${isActive ? " active" : ""}`}>
              <span>{t.label}</span>
            </NavLink>
          ))}
          <Needle tabs={tabs} />
        </nav>
        <div className="bar-end">
          <button type="button" className="cmd-trigger" onClick={openPalette} aria-label="Search or jump to, opens the command palette" aria-keyshortcuts="Control+K Meta+K /">
            <IconSearch />
            <span className="cmd-label">Search or jump to</span>
            <span className="kbd-group" aria-hidden="true"><span className="kbd">{mac ? "⌘" : "Ctrl"}</span><span className="kbd">K</span></span>
          </button>
          <button type="button" className="host-chip" onClick={copyHub} title="Copy hub URL" aria-label={`Connected to ${host}. Copy hub URL`}>
            <span className="live-dot" aria-hidden="true" />
            <span className="host-text">{host}</span>
          </button>
          <button
            type="button" className="icon-btn" onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <IconSun /> : <IconMoon />}
          </button>
          <Menu
            label="Account menu" className="avatar-btn"
            head={<><div className="name">{user.name || "Operator"}</div><div className="mail">{user.email}</div></>}
            items={[
              { label: "Keyboard shortcuts", icon: <IconKeyboard />, onSelect: openShortcuts, hint: <span className="kbd-group"><span className="kbd">?</span></span> },
              { label: "Settings", icon: <IconCog />, onSelect: () => { window.location.assign("/app/settings"); } },
              { label: "Log out", icon: <IconLogout />, danger: true, separatorBefore: true, onSelect: () => { window.location.href = "/auth/logout"; } },
            ]}
          >
            <span className="avatar" title={user.email}>{initials}</span>
          </Menu>
        </div>
      </div>
    </header>
  );
}

const MORE_ROUTES = ["/conversations", "/models", "/settings", "/pair"];

export function TabBar() {
  const loc = useLocation();
  const [more, setMore] = useState(false);
  const moreActive = MORE_ROUTES.some(r => loc.pathname.startsWith(r));
  useEffect(() => setMore(false), [loc.pathname]);
  const primary = [TABS[0], TABS[3], TABS[1], TABS[2]];
  return (
    <>
      <nav className="tabbar" aria-label="Primary">
        {primary.map(t => (
          <NavLink key={t.to} to={t.to} end={t.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
            {t.icon}{t.label}
          </NavLink>
        ))}
        <button type="button" onClick={() => setMore(true)} aria-haspopup="dialog" aria-expanded={more} className={moreActive ? "active" : ""} style={moreActive ? { color: "var(--ink)" } : undefined}>
          <IconMore />More
        </button>
      </nav>
      {more && <MoreSheet onClose={() => setMore(false)} />}
    </>
  );
}

function MoreSheet({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const [theme, toggleTheme] = useTheme();
  const { openPalette, openShortcuts } = useCommands();
  useFocusTrap(ref);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={id} onMouseDown={e => e.stopPropagation()}>
        <div className="modal-head">
          <div className="row between">
            <h2 id={id}>More</h2>
            <button type="button" className="icon-btn" aria-label="Close dialog" onClick={onClose}><IconX /></button>
          </div>
        </div>
        <div className="modal-body">
          <div className="sheet-links">
            <Link to="/conversations"><IconMessages />Sessions</Link>
            <Link to="/models"><IconGrid />Models</Link>
            <Link to="/pair"><IconDevice />Pair a device</Link>
            <Link to="/settings"><IconCog />Settings</Link>
            <button type="button" onClick={() => { onClose(); openPalette(); }}><IconSearch />Search and jump</button>
            <button type="button" onClick={() => { onClose(); openShortcuts(); }}><IconKeyboard />Keyboard shortcuts</button>
            <button type="button" onClick={toggleTheme}>{theme === "dark" ? <IconSun /> : <IconMoon />}{theme === "dark" ? "Light theme" : "Dark theme"}</button>
            <a href="/auth/logout"><IconLogout />Log out</a>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

import { NavLink } from "react-router-dom";
import {
  IconBook, IconExternal, IconGrid, IconHome, IconKey, IconMessages,
  IconMoon, IconSun,
} from "../icons";
import { useTheme } from "../theme";
import type { CurrentUser } from "../types";
import { Brand } from "./Brand";

const nav: Array<[string, string, (p: { style?: React.CSSProperties }) => JSX.Element]> = [
  ["/", "Home", IconHome],
  ["/keys", "Keys", IconKey],
  ["/conversations", "Sessions", IconMessages],
  ["/models", "Models", IconGrid],
];

export function Header({ user }: { user: CurrentUser }) {
  const initials = (user.name || user.email || "?").charAt(0).toUpperCase();
  const [theme, toggleTheme] = useTheme();
  return (
    <header className="header">
      <div className="container header-inner">
        <Brand />
        <nav className="nav" aria-label="Primary">
          {nav.map(([to, label, Ico]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              <Ico style={{ width: 16, height: 16 }} />{label}
            </NavLink>
          ))}
          <a className="ext" href="/docs" target="_blank" rel="noopener noreferrer" title="Auto-generated OpenAPI docs">
            <IconBook style={{ width: 16, height: 16 }} />Docs
            <IconExternal style={{ width: 12, height: 12, opacity: 0.6 }} />
          </a>
        </nav>
        <div className="header-right">
          <button
            className="icon-btn"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <IconSun /> : <IconMoon />}
          </button>
          <div className="divider" style={{ width: 1, height: 22, margin: "0 4px" }}></div>
          <div className="row" style={{ gap: 9 }}>
            <span className="avatar" title={user.email}>{initials}</span>
            <div style={{ lineHeight: 1.2 }}>
              {user.name && <div style={{ fontWeight: 600, fontSize: 12.5 }}>{user.name}</div>}
              <div className="faint" style={{ fontSize: 11 }}>{user.email}</div>
            </div>
          </div>
          <a
            href="/auth/logout"
            className="btn btn-sm btn-ghost"
            title="Log out"
            aria-label="Log out"
            style={{ borderColor: "var(--border)" }}
          >
            <IconExternal />Logout
          </a>
        </div>
      </div>
    </header>
  );
}

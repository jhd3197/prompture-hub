import { NavLink } from "react-router-dom";
import {
  IconCog, IconExternal, IconGrid, IconHome, IconKey, IconMessages,
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
  ["/settings", "Settings", IconCog],
];

export function Sidebar({ user }: { user: CurrentUser }) {
  const initials = (user.name || user.email || "?").charAt(0).toUpperCase();
  const [theme, toggleTheme] = useTheme();
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Brand />
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        {nav.map(([to, label, Ico]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            <Ico style={{ width: 17, height: 17 }} />{label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="sidebar-user">
          <span className="avatar" title={user.email}>{initials}</span>
          <div className="sidebar-user-meta">
            {user.name && <div className="sidebar-user-name">{user.name}</div>}
            <div className="faint sidebar-user-email">{user.email}</div>
          </div>
          <button
            className="icon-btn"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <IconSun /> : <IconMoon />}
          </button>
        </div>
        <a
          href="/auth/logout"
          className="btn btn-sm btn-ghost sidebar-logout"
          title="Log out"
          aria-label="Log out"
        >
          <IconExternal />Logout
        </a>
      </div>
    </aside>
  );
}

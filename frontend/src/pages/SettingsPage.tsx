import { NavLink, Outlet } from "react-router-dom";
import { IconCode, IconCog, IconNetwork, IconPalette } from "../icons";

const SECTIONS: Array<{
  to: string;
  label: string;
  icon: (p: { style?: React.CSSProperties }) => JSX.Element;
}> = [
  { to: "appearance", label: "Appearance", icon: IconPalette },
  { to: "network",    label: "Network",    icon: IconNetwork },
  { to: "api",        label: "API & docs", icon: IconCode },
];

export function SettingsPage() {
  return (
    <div className="container">
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">
            Operator-only knobs. Changes to appearance are local to this
            browser; network and API info reflect the running hub process.
          </p>
        </div>
      </div>

      <div className="grid-dash" style={{ gridTemplateColumns: "minmax(200px, 220px) 1fr", gap: 24, alignItems: "start" }}>
        <nav
          aria-label="Settings sections"
          className="card"
          style={{ padding: 8, position: "sticky", top: 80 }}
        >
          {SECTIONS.map(({ to, label, icon: Ico }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => isActive ? "active" : ""}
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "9px 12px",
                borderRadius: "var(--r-sm)",
                fontSize: 13,
                fontWeight: 500,
                color: isActive ? "var(--text)" : "var(--text-2)",
                background: isActive ? "var(--accent-soft)" : "transparent",
                marginBottom: 2,
              })}
            >
              <Ico style={{ width: 14, height: 14 }} />
              {label}
            </NavLink>
          ))}

          <div
            style={{
              padding: "10px 12px",
              marginTop: 10,
              borderTop: "1px solid var(--border)",
              fontSize: 11.5,
              color: "var(--text-3)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <IconCog style={{ width: 12, height: 12 }} />
              <strong style={{ color: "var(--text-2)" }}>About</strong>
            </div>
            <div className="mono" style={{ fontSize: 11 }}>prompture-hub v0.0.1</div>
          </div>
        </nav>

        <div>
          <Outlet />
        </div>
      </div>
    </div>
  );
}

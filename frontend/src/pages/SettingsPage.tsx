import { NavLink, Outlet } from "react-router-dom";
import { IconBolt, IconCode, IconCog, IconNetwork, IconPalette, IconRoute, IconShield } from "../icons";

const SECTIONS: Array<{
  to: string;
  label: string;
  icon: (p: { style?: React.CSSProperties }) => JSX.Element;
}> = [
  { to: "appearance", label: "Appearance", icon: IconPalette },
  { to: "network",    label: "Network",    icon: IconNetwork },
  { to: "api",        label: "API & docs", icon: IconCode },
  { to: "devices",    label: "Devices",    icon: IconShield },
  { to: "alerts",     label: "Alerts",     icon: IconBolt },
  { to: "endpoints",  label: "Endpoints",  icon: IconRoute },
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

      <div className="settings-layout">
        <nav aria-label="Settings sections" className="card settings-nav">
          {SECTIONS.map(({ to, label, icon: Ico }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => isActive ? "active" : ""}
            >
              <Ico style={{ width: 14, height: 14 }} />
              {label}
            </NavLink>
          ))}

          <div className="settings-about">
            <div className="row" style={{ gap: 6, marginBottom: 4 }}>
              <IconCog style={{ width: 12, height: 12 }} />
              <strong style={{ color: "var(--text-2)" }}>About</strong>
            </div>
            <div className="mono" style={{ fontSize: 11 }}>prompture-hub v0.0.1</div>
          </div>
        </nav>

        <div className="settings-body">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

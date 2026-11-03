import { NavLink, Outlet } from "react-router-dom";
import { PageHead } from "../components/PageHead";
import { IconBolt, IconCode, IconNetwork, IconPalette, IconRoute, IconShield } from "../icons";

const SECTIONS: Array<{
  to: string;
  label: string;
  icon: (p: { style?: React.CSSProperties }) => JSX.Element;
}> = [
  { to: "appearance", label: "Appearance", icon: IconPalette },
  { to: "network",    label: "Network",    icon: IconNetwork },
  { to: "api",        label: "API and docs", icon: IconCode },
  { to: "devices",    label: "Devices",    icon: IconShield },
  { to: "alerts",     label: "Alerts",     icon: IconBolt },
  { to: "endpoints",  label: "Endpoints",  icon: IconRoute },
];

export function SettingsPage() {
  return (
    <div className="container">
      <PageHead
        title="Settings"
        sub="Operator controls. Appearance is local to this browser; network and API details reflect the running hub process."
      />
      <div className="settings-layout">
        <nav aria-label="Settings sections" className="settings-nav">
          {SECTIONS.map(({ to, label, icon: Ico }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
              <Ico />
              <span>{label}</span>
            </NavLink>
          ))}
          <div className="settings-about mono">prompture-hub v0.0.1</div>
        </nav>
        <div className="settings-body"><Outlet /></div>
      </div>
    </div>
  );
}

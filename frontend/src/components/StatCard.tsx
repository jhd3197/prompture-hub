import type { ReactNode } from "react";

export function StatCard({
  icon, label, value, meta,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="stat fade-in">
      <div className="stat-label">{icon}{label}</div>
      <div className="stat-value tnum">{value}</div>
      {meta && <div className="stat-meta">{meta}</div>}
    </div>
  );
}

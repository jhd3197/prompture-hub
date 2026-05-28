import type { ReactNode } from "react";

export function EmptyState({
  icon, title, children, action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-ico">{icon}</div>
      <h4>{title}</h4>
      <p>{children}</p>
      {action && <div className="mt16">{action}</div>}
    </div>
  );
}

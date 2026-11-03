import type { ReactNode } from "react";

/** A designed empty state: says what will appear here and offers the next action. */
export function EmptyState({
  icon, title, children, action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state-ico">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action && <div className="state-actions">{action}</div>}
    </div>
  );
}

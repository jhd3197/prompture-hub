import type { ReactNode } from "react";
import { usePageTitle } from "../util/hooks";

/** The page's single h1, the sentence under it, and its actions. Also sets the tab title. */
export function PageHead({
  title, sub, children, docTitle,
}: {
  title: string;
  sub?: ReactNode;
  children?: ReactNode;
  docTitle?: string;
}) {
  usePageTitle(docTitle ?? title);
  return (
    <div className="page-head">
      <div className="grow">
        <h1 className="page-title">{title}</h1>
        {sub && <p className="page-sub">{sub}</p>}
      </div>
      {children && <div className="page-head-actions">{children}</div>}
      <i className="head-scale" aria-hidden="true" />
    </div>
  );
}

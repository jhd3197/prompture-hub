import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { IconX } from "../icons";

interface Props {
  title: string;
  desc?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  wide?: boolean;
}

export function Modal({ title, desc, children, footer, onClose, wide }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Portal to <body> so any ancestor with `transform`, `filter`, etc.
  // can't trap our position:fixed overlay (the agent-card's fade-in
  // animation does exactly that).
  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div
        className="modal"
        style={wide ? { maxWidth: 600 } : undefined}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="modal-head">
          <div className="row between">
            <h2>{title}</h2>
            <button className="icon-btn" onClick={onClose} aria-label="Close dialog">
              <IconX />
            </button>
          </div>
          {desc && <p>{desc}</p>}
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

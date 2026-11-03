import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { IconX } from "../icons";
import { useFocusTrap } from "../lib/hooks";

interface Props {
  title: string;
  desc?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  wide?: boolean;
}

export function Modal({ title, desc, children, footer, onClose, wide }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useFocusTrap(ref);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [onClose]);

  // Portaled to <body> so no ancestor transform can trap the fixed overlay.
  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div
        ref={ref}
        className="modal"
        style={wide ? { maxWidth: 640 } : undefined}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="modal-head">
          <div className="row between" style={{ alignItems: "flex-start" }}>
            <h2 id={titleId}>{title}</h2>
            <button type="button" className="icon-btn" onClick={onClose} aria-label="Close dialog">
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

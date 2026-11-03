import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface MenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
  hint?: ReactNode;
  separatorBefore?: boolean;
}

/** A button that opens an ARIA menu in a portal: arrow keys move, Escape returns focus, outside click closes. */
export function Menu({
  label, items, head, className = "icon-btn", children,
}: {
  label: string;
  items: MenuItem[];
  head?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  const toggle = () => {
    if (open) { setOpen(false); return; }
    const r = btn.current!.getBoundingClientRect();
    setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
    setOpen(true);
  };

  useLayoutEffect(() => {
    if (!open || !menu.current || !btn.current) return;
    const h = menu.current.offsetHeight;
    const r = btn.current.getBoundingClientRect();
    if (r.bottom + 6 + h > window.innerHeight - 8) setPos({ top: Math.max(8, r.top - 6 - h), right: Math.max(8, window.innerWidth - r.right) });
    menu.current.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)')?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("pointerdown", away);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("pointerdown", away);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);

  const onKey = (e: React.KeyboardEvent) => {
    const nodes = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? []);
    const i = nodes.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); btn.current?.focus(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); nodes[(i + 1) % nodes.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); nodes[(i - 1 + nodes.length) % nodes.length]?.focus(); }
    else if (e.key === "Home") { e.preventDefault(); nodes[0]?.focus(); }
    else if (e.key === "End") { e.preventDefault(); nodes[nodes.length - 1]?.focus(); }
    else if (e.key === "Tab") setOpen(false);
  };

  return (
    <>
      <button ref={btn} type="button" className={className} aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={toggle}>
        {children}
      </button>
      {open && pos && createPortal(
        <div ref={menu} className="menu" role="menu" aria-label={label} style={{ top: pos.top, right: pos.right }} onKeyDown={onKey}>
          {head && <div className="menu-head">{head}</div>}
          {head && <div className="menu-sep" />}
          {items.map(it => (
            <div key={it.label} style={{ display: "contents" }}>
              {it.separatorBefore && <div className="menu-sep" />}
              <button
                type="button" role="menuitem" disabled={it.disabled}
                className={`menu-item${it.danger ? " danger" : ""}`}
                onClick={() => { setOpen(false); btn.current?.focus(); it.onSelect(); }}
              >
                {it.icon}{it.label}{it.hint}
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}

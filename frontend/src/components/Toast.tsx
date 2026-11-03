import {
  createContext, useCallback, useContext, useState,
  type ReactNode,
} from "react";
import { IconAlert, IconCheck, IconX } from "../icons";

type Tone = "ok" | "bad";
interface ToastItem { id: string; msg: string; tone: Tone; }
type Push = (msg: string, tone?: Tone) => void;

const Ctx = createContext<Push>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: string) => setItems(prev => prev.filter(t => t.id !== id)), []);
  const push = useCallback<Push>((msg, tone) => {
    // Failures read as errors without every caller having to say so.
    const t: Tone = tone ?? (/^couldn.t|failed/i.test(msg) ? "bad" : "ok");
    const id = Math.random().toString(36).slice(2);
    setItems(prev => [...prev.slice(-3), { id, msg, tone: t }]);
    setTimeout(() => dismiss(id), t === "bad" ? 7000 : 3200);
  }, [dismiss]);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="toast-stack">
        <div role="status" aria-live="polite" style={{ display: "contents" }}>
          {items.filter(t => t.tone === "ok").map(t => (
            <div className="toast" key={t.id}><IconCheck />{t.msg}</div>
          ))}
        </div>
        <div role="alert" style={{ display: "contents" }}>
          {items.filter(t => t.tone === "bad").map(t => (
            <div className="toast bad" key={t.id}>
              <IconAlert />{t.msg}
              <button type="button" className="toast-x" aria-label="Dismiss" onClick={() => dismiss(t.id)}><IconX style={{ width: 14, height: 14 }} /></button>
            </div>
          ))}
        </div>
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);

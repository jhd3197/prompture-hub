import {
  createContext, useCallback, useContext, useState,
  type ReactNode,
} from "react";
import { IconCheck } from "../icons";

interface ToastItem { id: string; msg: string; }
interface ToastCtxValue { push: (msg: string) => void; }

const Ctx = createContext<ToastCtxValue>({ push: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((msg: string) => {
    const id = Math.random().toString(36).slice(2);
    setItems(prev => [...prev, { id, msg }]);
    setTimeout(
      () => setItems(prev => prev.filter(t => t.id !== id)),
      2800,
    );
  }, []);
  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {items.map(t => (
          <div className="toast" key={t.id}>
            <IconCheck /> {t.msg}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx).push;

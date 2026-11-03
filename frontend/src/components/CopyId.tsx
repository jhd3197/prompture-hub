import { useState } from "react";
import { IconCheck, IconCopy } from "../icons";
import { useToast } from "./Toast";

/** Click-to-copy identifier, truncated to fit, full value in the tooltip. */
export function CopyId({ value, display, label = "id" }: { value: string; display?: string; label?: string }) {
  const [done, setDone] = useState(false);
  const toast = useToast();
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); } catch { /* clipboard can be blocked; still confirm below */ }
    setDone(true);
    toast(`Copied ${label}`);
    setTimeout(() => setDone(false), 1400);
  };
  return (
    <button type="button" className="id-copy" onClick={copy} title={`Copy ${label}: ${value}`} aria-label={`${display ?? value}, copy ${label}`}>
      <span className="id-text">{display ?? value}</span>
      {done ? <IconCheck /> : <IconCopy />}
    </button>
  );
}

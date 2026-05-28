import { useState } from "react";
import { IconCheck, IconCopy } from "../icons";
import { useToast } from "./Toast";

export function CopyButton({
  text, label = "Copy", className = "btn btn-sm",
}: { text: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  const toast = useToast();
  const onClick = async () => {
    try { await navigator.clipboard.writeText(text); } catch { /* ignore */ }
    setDone(true);
    toast("Copied to clipboard");
    setTimeout(() => setDone(false), 1400);
  };
  return (
    <button className={className} onClick={onClick} aria-label={label}>
      {done ? <IconCheck /> : <IconCopy />}
      {label}
    </button>
  );
}

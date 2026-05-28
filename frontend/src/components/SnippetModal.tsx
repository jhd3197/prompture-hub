import { useMemo, useState } from "react";
import { IconShield } from "../icons";
import { CopyButton } from "./CopyButton";
import { Modal } from "./Modal";

type Kind = "curl" | "python" | "prompture";

interface Props {
  route: string;     // e.g. "openai/gpt-4o"
  onClose: () => void;
}

const TABS: Array<[Kind, string]> = [
  ["curl", "cURL"],
  ["python", "Python (OpenAI SDK)"],
  ["prompture", "Prompture"],
];

function hubBase(): string {
  if (typeof window === "undefined") return "http://localhost:1984";
  return `${window.location.protocol}//${window.location.host}`;
}

function curlSnippet(route: string): string {
  return `curl -N ${hubBase()}/v1/chat/completions \\
  -H "Authorization: Bearer $PROMPTURE_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${route}",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'`;
}

function pythonSnippet(route: string): string {
  return `from openai import OpenAI

client = OpenAI(
    base_url="${hubBase()}/v1",
    api_key="$PROMPTURE_KEY",   # your hub key, not a provider key
)

resp = client.chat.completions.create(
    model="${route}",            # provider/model selects the driver
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)`;
}

function promptureSnippet(route: string): string {
  return `from prompture import extract_with_model
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

person = extract_with_model(
    Person,
    "Maria is 32.",
    model_name="${route}",
)
print(person)`;
}

function build(route: string, kind: Kind): string {
  if (kind === "curl") return curlSnippet(route);
  if (kind === "python") return pythonSnippet(route);
  return promptureSnippet(route);
}

// Minimal syntax highlight — order matters: comments first so string
// matching inside them doesn't fire, then strings, then keywords.
function highlight(code: string): string {
  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  let html = escape(code);
  html = html.replace(/(#[^\n]*)/g, '<span class="tok-com">$1</span>');
  html = html.replace(/("(?:[^"\\]|\\.)*")/g, '<span class="tok-str">$1</span>');
  html = html.replace(
    /\b(from|import|class|print|return|def|if|else)\b/g,
    '<span class="tok-key">$1</span>',
  );
  return html;
}

export function SnippetModal({ route, onClose }: Props) {
  const [kind, setKind] = useState<Kind>("curl");
  const code = useMemo(() => build(route, kind), [route, kind]);
  const html = useMemo(() => highlight(code), [code]);

  return (
    <Modal
      title="Use this model through the hub"
      wide
      onClose={onClose}
      desc={
        <>
          Call <code className="mono">{route}</code> with your hub key — the prefix routes the driver and the hub meters it.
        </>
      }
      footer={<button className="btn btn-ghost" onClick={onClose}>Close</button>}
    >
      <div className="seg" role="tablist" style={{ alignSelf: "flex-start" }}>
        {TABS.map(([k, label]) => (
          <button
            key={k}
            role="tab"
            aria-selected={kind === k}
            className={kind === k ? "on" : ""}
            onClick={() => setKind(k)}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ position: "relative" }}>
        <pre className="code" dangerouslySetInnerHTML={{ __html: html }} />
        <div style={{ position: "absolute", top: 10, right: 10 }}>
          <CopyButton text={code} label="Copy" className="btn btn-sm" />
        </div>
      </div>

      <div className="row" style={{ gap: 8, fontSize: 12.5, color: "var(--text-2)" }}>
        <IconShield style={{ width: 15, height: 15, color: "var(--accent-strong)", flex: "none" }} />
        Works only if <code className="mono">{route}</code> is on the calling key's whitelist.
      </div>
    </Modal>
  );
}

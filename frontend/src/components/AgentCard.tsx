import { useState } from "react";
import { CopyButton } from "./CopyButton";
import { RunAgentModal } from "./RunAgentModal";
import {
  IconAlert, IconBolt, IconCheck, IconRefresh, IconTerminal, IconX,
} from "../icons";
import type { AgentInfo } from "../types";

const FLAG_LABELS: Array<[keyof AgentInfo["capabilities"], string]> = [
  ["tool_use", "Tool use"],
  ["structured_output", "Structured output"],
  ["questions", "Asks questions"],
  ["session_resume", "Session resume"],
];

function statusBadge(a: AgentInfo) {
  if (a.available) {
    return (
      <span className="badge badge-live">
        <span className="dot"></span>Available
      </span>
    );
  }
  if (a.healthy === false) {
    return (
      <span className="badge badge-warn">
        <IconAlert style={{ width: 11, height: 11 }} />Broken shim
      </span>
    );
  }
  return (
    <span className="badge">
      <span className="dot" style={{ background: "var(--text-faint)" }}></span>
      Not installed
    </span>
  );
}

function installCommand(a: AgentInfo): string | null {
  if (a.npm_packages.length === 0) {
    return a.binary ? `# Install '${a.binary}' from its vendor's instructions` : null;
  }
  return `npm i -g ${a.npm_packages.join(" ")}`;
}

function variant(a: AgentInfo): "available" | "broken" | "missing" {
  if (a.available) return "available";
  if (a.healthy === false) return "broken";
  return "missing";
}

export function AgentCard({ agent }: { agent: AgentInfo }) {
  const kind = variant(agent);
  const install = installCommand(agent);
  const [running, setRunning] = useState(false);

  return (
    <div className={`agent-card ${kind} fade-in`}>
      <div className="agent-card-head">
        <span className="agent-logo">
          <IconTerminal />
        </span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row between">
            <span className="agent-name">{agent.name}</span>
            {statusBadge(agent)}
          </div>
          <div className="agent-sub">
            <code>{agent.binary || agent.id}</code>
            {agent.source && (
              <>
                {" "}· <span>{agent.source}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="agent-body">
        {kind === "broken" && agent.error && (
          <div className="agent-broken" role="alert">
            <IconAlert />
            <span>{agent.error}</span>
          </div>
        )}

        <div className="agent-flags">
          {FLAG_LABELS.map(([key, label]) => {
            const on = agent.capabilities[key];
            return (
              <span key={key} className={`flag ${on ? "" : "off"}`}>
                {on ? <IconCheck /> : <IconX />}
                {label}
              </span>
            );
          })}
        </div>

        {kind === "missing" && install && (
          <div className="agent-install" title="Install command">
            <span className="pf">$</span>
            <span style={{ flex: 1 }}>{install}</span>
          </div>
        )}
      </div>

      <div className="agent-foot">
        {kind === "missing" && install ? (
          <CopyButton
            text={install}
            label="Copy install"
            className="btn btn-sm btn-block"
          />
        ) : kind === "broken" ? (
          <button className="btn btn-sm" disabled title="Coming soon">
            <IconRefresh style={{ width: 13, height: 13 }} />Re-verify
          </button>
        ) : (
          <>
            <button
              className="btn btn-sm btn-primary"
              onClick={() => setRunning(true)}
            >
              <IconBolt style={{ width: 13, height: 13 }} />Run task
            </button>
            <span
              className="approve-pill"
              style={{ marginLeft: "auto" }}
              title="The hub will execute this binary on POST /v1/coding-agents/run"
            >
              /v1/coding-agents/run
            </span>
          </>
        )}
      </div>

      {running && (
        <RunAgentModal agent={agent} onClose={() => setRunning(false)} />
      )}
    </div>
  );
}

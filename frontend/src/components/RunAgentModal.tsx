import { useState } from "react";
import { ApiError, api } from "../api";
import {
  IconAlert, IconBolt, IconCheck, IconRefresh, IconTerminal, IconX,
} from "../icons";
import type { AgentInfo } from "../types";
import { Modal } from "./Modal";

type ApprovalMode = "default" | "auto" | "yolo";
type OutputFormat = "text" | "json";

interface RunResult {
  returncode: number;
  duration_seconds: number;
  output: string;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number; cost_usd: number };
  events: Array<Record<string, unknown>>;
  cwd: string;
}

const APPROVAL_OPTIONS: Array<[ApprovalMode, string, string]> = [
  ["default", "Default", "Prompt before each tool call (safest)."],
  ["auto", "Auto", "Auto-approve sandbox-safe actions; prompt only on risky ones."],
  ["yolo", "Yolo", "Approve everything. Requires HUB_ALLOW_AGENT_YOLO=true."],
];

export function RunAgentModal({
  agent, onClose,
}: { agent: AgentInfo; onClose: () => void }) {
  const [task, setTask] = useState("");
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("default");
  const [model, setModel] = useState("");
  const [extraArgs, setExtraArgs] = useState("");
  const [outputFormat, setOutputFormat] = useState<OutputFormat>(
    agent.capabilities.structured_output ? "json" : "text",
  );
  const [cwd, setCwd] = useState("");

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);

  const submit = async () => {
    if (!task.trim() || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.runAgent({
        agent: agent.id,
        task: task.trim(),
        approval_mode: approvalMode,
        model: model.trim() || null,
        extra_args: extraArgs.split(/\s+/).filter(Boolean),
        output_format: outputFormat,
        cwd: cwd.trim() || null,
      });
      setResult(r);
    } catch (e) {
      const msg = e instanceof ApiError
        ? (typeof e.body === "object" && e.body && "detail" in e.body
            ? String((e.body as { detail: unknown }).detail)
            : e.message)
        : String(e);
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Modal
      title={result ? `Result · ${agent.name}` : `Run task with ${agent.name}`}
      wide
      onClose={onClose}
      desc={
        result ? (
          <>Finished in <span className="mono tnum">{result.duration_seconds.toFixed(2)}s</span> · exit <span className="mono">{result.returncode}</span></>
        ) : (
          <>The hub will execute <code className="mono">{agent.binary}</code> inside the configured workspace and return the captured output.</>
        )
      }
      footer={result ? (
        <>
          <button className="btn btn-ghost" onClick={() => setResult(null)}>
            <IconRefresh style={{ width: 13, height: 13 }} />Run another
          </button>
          <button className="btn btn-primary" onClick={onClose}>Done</button>
        </>
      ) : (
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={running}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={!task.trim() || running}
          >
            <IconBolt style={{ width: 13, height: 13 }} />
            {running ? "Running…" : "Run task"}
          </button>
        </>
      )}
    >
      {error && (
        <div className="discovery-fail" role="alert" style={{
          borderRadius: "var(--r-md)",
          border: "1px solid var(--danger)",
          background: "var(--danger-soft)",
        }}>
          <IconAlert style={{ color: "var(--danger)" }} />
          <span className="mono" style={{ wordBreak: "break-word" }}>{error}</span>
        </div>
      )}

      {!result && (
        <>
          <div className="field">
            <label htmlFor="agent-task">Task</label>
            <textarea
              id="agent-task"
              className="textarea"
              value={task}
              onChange={e => setTask(e.target.value)}
              placeholder="Add tests for the discovery helper in src/foo.py"
              autoFocus
              style={{ minHeight: 120 }}
            />
            <span className="hint">Plain instruction for the agent. Be specific — agents follow the literal task.</span>
          </div>

          <div className="field">
            <label>Approval mode</label>
            <div className="seg" role="radiogroup" style={{ alignSelf: "flex-start" }}>
              {APPROVAL_OPTIONS.map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={approvalMode === mode}
                  className={approvalMode === mode ? "on" : ""}
                  onClick={() => setApprovalMode(mode)}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="hint">
              {APPROVAL_OPTIONS.find(([m]) => m === approvalMode)?.[2]}
            </span>
          </div>

          <div className="grid-2">
            <div className="field">
              <label htmlFor="agent-model">Model override <span className="faint" style={{ fontWeight: 500 }}>(optional)</span></label>
              <input
                id="agent-model"
                className="input mono"
                value={model}
                onChange={e => setModel(e.target.value)}
                placeholder="claude-sonnet-4-6"
              />
              <span className="hint">CLI-dependent. Leave blank to use the agent's default.</span>
            </div>
            <div className="field">
              <label htmlFor="agent-output">Output format</label>
              <div className="seg" role="radiogroup">
                <button
                  type="button"
                  className={outputFormat === "text" ? "on" : ""}
                  onClick={() => setOutputFormat("text")}
                >
                  Text
                </button>
                <button
                  type="button"
                  className={outputFormat === "json" ? "on" : ""}
                  onClick={() => setOutputFormat("json")}
                  disabled={!agent.capabilities.structured_output}
                  title={
                    agent.capabilities.structured_output
                      ? undefined
                      : "Agent doesn't expose structured events"
                  }
                >
                  JSON
                </button>
              </div>
              <span className="hint">
                {agent.capabilities.structured_output
                  ? "JSON populates the parsed event list below the output."
                  : "Only Text is available — this agent doesn't expose structured events."}
              </span>
            </div>
          </div>

          <div className="grid-2">
            <div className="field">
              <label htmlFor="agent-cwd">Subpath under workspace <span className="faint" style={{ fontWeight: 500 }}>(optional)</span></label>
              <input
                id="agent-cwd"
                className="input mono"
                value={cwd}
                onChange={e => setCwd(e.target.value)}
                placeholder="my-project"
              />
              <span className="hint">Empty = workspace root. Hub refuses paths that escape the workspace.</span>
            </div>
            <div className="field">
              <label htmlFor="agent-args">Extra CLI args <span className="faint" style={{ fontWeight: 500 }}>(optional)</span></label>
              <input
                id="agent-args"
                className="input mono"
                value={extraArgs}
                onChange={e => setExtraArgs(e.target.value)}
                placeholder="--verbose --foo=bar"
              />
              <span className="hint">Space-separated. Forwarded verbatim to the binary.</span>
            </div>
          </div>
        </>
      )}

      {result && (
        <>
          <div
            className="stat-grid"
            style={{
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 1,
              background: "var(--border)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              overflow: "hidden",
            }}
          >
            <div className="stat" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
              <div className="stat-label">
                {result.returncode === 0
                  ? <IconCheck style={{ color: "var(--accent-strong)" }} />
                  : <IconX style={{ color: "var(--danger)" }} />}
                Exit
              </div>
              <div
                className="stat-value tnum"
                style={{ fontSize: 22, color: result.returncode === 0 ? "var(--accent-strong)" : "var(--danger)" }}
              >
                {result.returncode}
              </div>
            </div>
            <div className="stat" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
              <div className="stat-label">Tokens</div>
              <div className="stat-value tnum" style={{ fontSize: 22 }}>
                {result.usage.total_tokens.toLocaleString()}
              </div>
              <div className="stat-meta" style={{ fontSize: 11 }}>
                {result.usage.prompt_tokens.toLocaleString()} in ·{" "}
                {result.usage.completion_tokens.toLocaleString()} out
              </div>
            </div>
            <div className="stat" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
              <div className="stat-label">Cost</div>
              <div className="stat-value tnum" style={{ fontSize: 22 }}>
                ${result.usage.cost_usd.toFixed(4)}
              </div>
            </div>
          </div>

          <div className="field">
            <label>Output</label>
            <pre
              className="code"
              style={{ maxHeight: 320, overflow: "auto", whiteSpace: "pre-wrap" }}
            >
              {result.output || "(empty)"}
            </pre>
          </div>

          {result.events.length > 0 && (
            <details>
              <summary
                className="filter-chip"
                style={{ cursor: "pointer", listStyle: "none", alignSelf: "flex-start" }}
              >
                <IconTerminal />
                {result.events.length} structured event{result.events.length !== 1 ? "s" : ""}
              </summary>
              <pre
                className="code"
                style={{ marginTop: 10, maxHeight: 240, overflow: "auto" }}
              >
                {JSON.stringify(result.events, null, 2)}
              </pre>
            </details>
          )}

          <div className="muted" style={{ fontSize: 12 }}>
            Ran inside <code className="mono">{result.cwd}</code>.
          </div>
        </>
      )}
    </Modal>
  );
}

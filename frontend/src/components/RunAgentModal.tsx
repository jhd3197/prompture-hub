import { useRef, useState } from "react";
import { ApiError, api } from "../api";
import {
  IconAlert, IconBolt, IconCheck, IconRefresh, IconTerminal, IconX,
} from "../icons";
import type { AgentInfo } from "../types";
import { Modal } from "./Modal";
import { ModelSelect } from "./ModelSelect";

// Most coding-agent CLIs only accept models from a single provider. The
// dropdown filters by that provider when we know it. Aider / OpenCode /
// Cursor accept many providers, so they get the full list.
const AGENT_PROVIDER_HINT: Record<string, string | undefined> = {
  claude: "claude",      // Anthropic via Claude CLI
  codex: "openai",
  gemini: "google",
  qwen: undefined,
  aider: undefined,
  opencode: undefined,
  "cursor-agent": undefined,
  crush: undefined,
};

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

type StreamEvent = Record<string, unknown> & { type?: string };

const APPROVAL_OPTIONS: Array<[ApprovalMode, string, string]> = [
  ["default", "Default", "Prompt before each tool call (safest)."],
  ["auto", "Auto", "Auto-approve sandbox-safe actions; prompt only on risky ones."],
  ["yolo", "Yolo", "Approve everything. Requires HUB_ALLOW_AGENT_YOLO=true."],
];

const EVENT_TINT: Record<string, { color: string; background: string }> = {
  thinking:    { color: "var(--text-3)", background: "var(--surface-2)" },
  message:     { color: "var(--accent-strong)", background: "var(--accent-softer)" },
  tool_call:   { color: "var(--info)", background: "color-mix(in oklch, var(--info) 8%, var(--surface))" },
  tool_result: { color: "var(--info)", background: "color-mix(in oklch, var(--info) 8%, var(--surface))" },
  result:      { color: "var(--accent-strong)", background: "var(--accent-soft)" },
  error:       { color: "var(--danger)", background: "var(--danger-soft)" },
  question:    { color: "var(--warn)", background: "var(--warn-soft)" },
};

function StreamEventRow({ event }: { event: StreamEvent }) {
  const type = String(event.type || "event");
  const tint = EVENT_TINT[type] || { color: "var(--text-2)", background: "var(--surface)" };

  const text = (event.text as string) || "";
  const toolName = event.tool_name as string | undefined;
  const cost = event.cost_usd as number | undefined;
  const inTok = event.input_tokens as number | undefined;
  const outTok = event.output_tokens as number | undefined;

  return (
    <div
      style={{
        padding: "8px 10px",
        borderRadius: "var(--r-sm)",
        background: tint.background,
        border: "1px solid var(--border)",
        fontSize: 12.5,
      }}
    >
      <div className="row" style={{ gap: 8 }}>
        <span
          className="mono"
          style={{
            color: tint.color,
            fontWeight: 700,
            fontSize: 10.5,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          {type}
        </span>
        {toolName && (
          <span className="mono faint" style={{ fontSize: 11.5 }}>{toolName}</span>
        )}
        {type === "result" && (
          <span className="faint mono" style={{ marginLeft: "auto", fontSize: 11.5 }}>
            {inTok ?? 0} in · {outTok ?? 0} out
            {cost !== undefined && cost > 0 && <> · ${cost.toFixed(4)}</>}
          </span>
        )}
      </div>
      {text && (
        <div
          style={{
            marginTop: 4,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            color: "var(--text)",
            lineHeight: 1.45,
          }}
        >
          {text}
        </div>
      )}
      {event.tool_input != null && (
        <pre
          className="code"
          style={{ marginTop: 6, padding: "6px 8px", fontSize: 11, maxHeight: 140 }}
        >
          {JSON.stringify(event.tool_input, null, 2)}
        </pre>
      )}
      {event.tool_output != null && (
        <pre
          className="code"
          style={{ marginTop: 6, padding: "6px 8px", fontSize: 11, maxHeight: 140 }}
        >
          {String(event.tool_output).slice(0, 1200)}
        </pre>
      )}
    </div>
  );
}

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

  const [streamMode, setStreamMode] = useState(
    agent.capabilities.structured_output,
  );

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streamDone, setStreamDone] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const submitSync = async () => {
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
    }
  };

  const submitStream = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setEvents([]);
    setStreamDone(false);

    let res: Response;
    try {
      res = await fetch("/api/agents/run", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent: agent.id,
          task: task.trim(),
          approval_mode: approvalMode,
          model: model.trim() || null,
          extra_args: extraArgs.split(/\s+/).filter(Boolean),
          output_format: "json",
          cwd: cwd.trim() || null,
          stream: true,
        }),
        signal: controller.signal,
      });
    } catch (e) {
      setError(String(e));
      return;
    }

    if (!res.ok || !res.body) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch { /* ignore */ }
      setError(detail);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice("data: ".length);
        if (payload === "[DONE]") {
          setStreamDone(true);
          continue;
        }
        try {
          const ev = JSON.parse(payload) as StreamEvent;
          setEvents(prev => [...prev, ev]);
        } catch {
          // ignore malformed frame
        }
      }
    }
    setStreamDone(true);
  };

  const submit = async () => {
    if (!task.trim() || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      if (streamMode && agent.capabilities.structured_output) {
        await submitStream();
      } else {
        await submitSync();
      }
    } finally {
      setRunning(false);
    }
  };

  const reset = () => {
    abortRef.current?.abort();
    setResult(null);
    setEvents([]);
    setStreamDone(false);
    setError(null);
  };

  const hasStreamView = streamMode && (events.length > 0 || running);
  const showingResultView = !!result || hasStreamView;

  return (
    <Modal
      title={showingResultView ? `Result · ${agent.name}` : `Run task with ${agent.name}`}
      wide
      onClose={onClose}
      desc={
        result ? (
          <>Finished in <span className="mono tnum">{result.duration_seconds.toFixed(2)}s</span> · exit <span className="mono">{result.returncode}</span></>
        ) : hasStreamView ? (
          streamDone
            ? <>Stream finished · {events.length} event{events.length !== 1 ? "s" : ""} received</>
            : <>Streaming live events from <code className="mono">{agent.binary}</code>…</>
        ) : (
          <>The hub will execute <code className="mono">{agent.binary}</code> inside the configured workspace and return the captured output.</>
        )
      }
      footer={showingResultView ? (
        <>
          <button className="btn btn-ghost" onClick={reset} disabled={running}>
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
            {running ? (streamMode ? "Streaming…" : "Running…") : "Run task"}
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

      {!showingResultView && (
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
              <ModelSelect
                id="agent-model"
                value={model}
                onChange={setModel}
                placeholder="claude-sonnet-4-6"
                providerFilter={AGENT_PROVIDER_HINT[agent.id]}
                bareModelIds
              />
              <span className="hint">
                CLI-dependent. Leave blank to use the agent's default.
                {AGENT_PROVIDER_HINT[agent.id] && (
                  <> Suggestions filtered to <code className="mono">{AGENT_PROVIDER_HINT[agent.id]}</code> models.</>
                )}
              </span>
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

          <label
            className="row"
            style={{
              gap: 10,
              padding: "10px 12px",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              background: "var(--surface-2)",
              cursor: agent.capabilities.structured_output ? "pointer" : "not-allowed",
              opacity: agent.capabilities.structured_output ? 1 : 0.55,
            }}
          >
            <input
              type="checkbox"
              checked={streamMode && agent.capabilities.structured_output}
              disabled={!agent.capabilities.structured_output}
              onChange={e => setStreamMode(e.target.checked)}
              style={{ accentColor: "var(--accent)" }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>
                Stream events live
              </div>
              <div className="faint" style={{ fontSize: 12 }}>
                {agent.capabilities.structured_output
                  ? "See tool calls, messages, and the final result as they arrive."
                  : "This agent doesn't expose structured events. Will return the full output at the end."}
              </div>
            </div>
          </label>
        </>
      )}

      {hasStreamView && (
        <>
          <div
            className="row"
            style={{
              gap: 8, padding: "8px 12px",
              borderRadius: "var(--r-md)",
              background: streamDone ? "var(--accent-soft)" : "var(--surface-2)",
              border: "1px solid var(--border)",
              fontSize: 12.5,
            }}
          >
            {streamDone ? (
              <IconCheck style={{ color: "var(--accent-strong)", width: 14, height: 14 }} />
            ) : (
              <span className="kdot live"></span>
            )}
            <span style={{ fontWeight: 600 }}>
              {streamDone ? "Stream finished" : "Live"}
            </span>
            <span className="faint" style={{ marginLeft: "auto" }}>
              {events.length} event{events.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div
            style={{
              maxHeight: 380,
              overflow: "auto",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              padding: 4,
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            {events.length === 0 ? (
              <p className="faint" style={{ padding: 14, margin: 0, fontSize: 12.5 }}>
                Waiting for first event…
              </p>
            ) : (
              events.map((ev, i) => <StreamEventRow key={i} event={ev} />)
            )}
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

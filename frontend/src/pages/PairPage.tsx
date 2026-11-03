import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAsync } from "../util/hooks";
import { timeAgo } from "../util/format";
import { PageHead } from "../components/PageHead";
import { useToast } from "../components/Toast";
import { IconAlert, IconCheck, IconLock, IconShield } from "../icons";
import type { PairingInfo } from "../types";

type Step =
  | { kind: "enter" }
  | { kind: "loading" }
  | { kind: "review"; info: PairingInfo }
  | { kind: "done"; name: string; scopes: string[] }
  | { kind: "denied" };

function formatCode(raw: string): string {
  const clean = raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  return clean.length > 4 ? `${clean.slice(0, 4)}-${clean.slice(4)}` : clean;
}

export function PairPage() {
  const [params] = useSearchParams();
  const toast = useToast();
  const [code, setCode] = useState(formatCode(params.get("code") || ""));
  const [step, setStep] = useState<Step>({ kind: "enter" });
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [allowControl, setAllowControl] = useState(false);

  const devs = useAsync(() => api.devices(), []);
  const typed = code.replace("-", "").length;

  const lookup = async (value: string) => {
    setError(null);
    setStep({ kind: "loading" });
    try {
      const info = await api.pairing(value);
      setName(info.client_name || "");
      setAllowControl(info.requested_scopes.includes("control"));
      setStep({ kind: "review", info });
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 404
          ? "No pending pairing with that code. Codes expire after 10 minutes, so start again on the device."
          : String(e),
      );
      setStep({ kind: "enter" });
    }
  };

  useEffect(() => {
    if (code.length === 9) lookup(code);
    // Only auto-submit a code that arrived in the link.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const approve = async (info: PairingInfo) => {
    try {
      const res = await api.approvePairing(info.user_code, {
        name: name.trim() || undefined,
        scopes: allowControl ? ["read", "control"] : ["read"],
      });
      setStep({ kind: "done", name: res.name, scopes: res.scopes });
    } catch (e) {
      toast(`Couldn't approve: ${e}`);
    }
  };

  const deny = async (info: PairingInfo) => {
    try {
      await api.denyPairing(info.user_code);
      setStep({ kind: "denied" });
    } catch (e) {
      toast(`Couldn't deny: ${e}`);
    }
  };

  return (
    <div className="container">
      <PageHead
        title="Pair a device"
        sub="A desktop companion or widget is asking to watch this hub. Enter the code it shows, check what it wants, and approve it."
      />

      <div className="cols cols-7-5">
      <div className="stack">
      <div className="panel panel-pad rise pair-panel">
        {(step.kind === "enter" || step.kind === "loading") && (
          <form
            onSubmit={e => { e.preventDefault(); if (code.length === 9) lookup(code); }}
            style={{ display: "flex", flexDirection: "column", gap: 14 }}
          >
            <div className="field">
              <label htmlFor="pair-code">Code shown on the device</label>
              <input
                id="pair-code"
                className="input mono tnum"
                style={{ fontSize: 28, letterSpacing: "0.18em", textAlign: "center", minHeight: 64 }}
                placeholder="XXXX-XXXX"
                autoComplete="off"
                value={code}
                onChange={e => setCode(formatCode(e.target.value))}
                aria-invalid={error ? "true" : undefined}
              />
              {error && <span className="hint field-error">{error}</span>}
            </div>
            <div className="code-scale" role="img" aria-label={`${typed} of 8 characters entered`}>
              {Array.from({ length: 8 }, (_, i) => <i key={i} className={i < typed ? "on" : ""} />)}
              <span className="mono">{typed}/8</span>
            </div>
            <button className="btn btn-primary btn-block" disabled={code.length !== 9 || step.kind === "loading"}>
              {step.kind === "loading" ? "Looking up…" : typed < 8 ? `Enter ${8 - typed} more character${8 - typed === 1 ? "" : "s"}` : "Continue"}
            </button>
          </form>
        )}

        {step.kind === "review" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="row" style={{ gap: 10 }}>
              <IconShield style={{ width: 18, height: 18, color: "var(--accent-strong)" }} />
              <div>
                <div className="strong" style={{ fontWeight: 600 }}>
                  {step.info.client_name || "An unnamed device"} wants access
                </div>
                <div className="faint mono" style={{ fontSize: 12 }}>code {step.info.user_code}</div>
              </div>
            </div>

            <div className="field">
              <label htmlFor="pair-name">Name for this device</label>
              <input
                id="pair-name"
                className="input"
                placeholder="Work laptop"
                maxLength={100}
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>

            <div className="field">
              <label>What it can do</label>
              <label className="row" style={{ gap: 8, fontWeight: 400 }}>
                <input type="checkbox" checked disabled />
                See live calls, spend, limits and alerts
              </label>
              <label className="row" style={{ gap: 8, fontWeight: 400 }}>
                <input
                  type="checkbox"
                  checked={allowControl}
                  onChange={e => setAllowControl(e.target.checked)}
                />
                Also change things: pause keys, switch routes, edit caps, acknowledge alerts
              </label>
              {step.info.requested_scopes.includes("control") && !allowControl && (
                <span className="hint">The device asked for control; it will get read-only access.</span>
              )}
            </div>

            <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
              <button className="btn btn-ghost" onClick={() => deny(step.info)}>Deny</button>
              <button className="btn btn-primary" onClick={() => approve(step.info)}>
                <IconCheck />Approve
              </button>
            </div>
          </div>
        )}

        {step.kind === "done" && (
          <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
            <IconCheck style={{ width: 20, height: 20, color: "var(--accent-strong)" }} />
            <div>
              <div className="strong" style={{ fontWeight: 600 }}>{step.name} is paired</div>
              <p className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>
                It picks up its token on its next check ({step.scopes.join(" + ")} access).
                Revoke it any time under <Link to="/settings/devices">Settings › Devices</Link>.
              </p>
            </div>
          </div>
        )}

        {step.kind === "denied" && (
          <div className="row" style={{ gap: 12 }}>
            <IconAlert style={{ width: 20, height: 20, color: "var(--danger)" }} />
            <span>Denied. The device was told no and got no access.</span>
          </div>
        )}
      </div>
      <section className="panel rise pair-devices" style={{ ["--i" as string]: 2 }} aria-labelledby="pair-have">
        <div className="panel-head"><h2 id="pair-have">Already paired</h2><span className="sub">{devs.data ? `${devs.data.filter(d => d.active).length} active` : "loading"}</span></div>
        {devs.data && devs.data.length === 0 && <p className="muted" style={{ margin: 0, padding: 16, fontSize: "var(--t-sm)" }}>No devices yet. The first one you approve shows up here.</p>}
        {(devs.data ?? []).slice(0, 4).map(d => (
          <div className="dev" key={d.id}>
            <b className="truncate">{d.name}</b>
            <span className="mono">{d.last_used_at ? `seen ${timeAgo(d.last_used_at)}` : "never seen"}</span>
            {d.active ? <span className="chip chip-ok"><span className="dot" />active</span> : <span className="chip chip-mute"><span className="dot" />revoked</span>}
          </div>
        ))}
      </section>
      </div>

      <aside className="panel rise pair-side" style={{ ["--i" as string]: 1 }} aria-labelledby="pair-how">
        <div className="panel-head"><h2 id="pair-how">What approving does</h2><span className="sub">device flow</span></div>
        <ol className="pair-steps">
          <li><b>The device asks for a code.</b><span>It shows eight characters and waits. Codes expire after 10 minutes.</span></li>
          <li><b>You check what it wants.</b><span>Read-only is the default. Control (pause keys, edit caps, acknowledge alerts) is a separate tick.</span></li>
          <li><b>It gets its own token.</b><span>Separate from hub keys and your login. It never allows model calls, and you can revoke it under <Link to="/settings/devices">Settings › Devices</Link>.</span></li>
        </ol>
        <p className="pair-note"><IconLock />Nothing is granted until you approve.</p>
      </aside>
      </div>
    </div>
  );
}

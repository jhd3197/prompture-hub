import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
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
          ? "No pending pairing with that code. Codes expire after 10 minutes — start again on the device."
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
    <div className="container" style={{ maxWidth: 560 }}>
      <div className="page-head">
        <div className="grow">
          <h1 className="page-title">Pair a device</h1>
          <p className="page-sub">
            A desktop companion or widget is asking to watch this hub. Enter the code it shows,
            check what it wants, and approve it.
          </p>
        </div>
      </div>

      <div className="card card-pad">
        {(step.kind === "enter" || step.kind === "loading") && (
          <form
            onSubmit={e => { e.preventDefault(); if (code.length === 9) lookup(code); }}
            style={{ display: "flex", flexDirection: "column", gap: 14 }}
          >
            <div className="field">
              <label htmlFor="pair-code">Code shown on the device</label>
              <input
                id="pair-code"
                className="input mono"
                style={{ fontSize: 22, letterSpacing: "0.12em", textAlign: "center" }}
                placeholder="XXXX-XXXX"
                autoComplete="off"
                autoFocus
                value={code}
                onChange={e => setCode(formatCode(e.target.value))}
                aria-invalid={error ? "true" : undefined}
              />
              {error && <span className="hint field-error">{error}</span>}
            </div>
            <button className="btn btn-primary btn-block" disabled={code.length !== 9 || step.kind === "loading"}>
              {step.kind === "loading" ? "Looking up…" : "Continue"}
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

      <p className="muted mt16" style={{ fontSize: 12.5 }}>
        <IconLock style={{ width: 13, height: 13, verticalAlign: "-2px", marginRight: 5 }} />
        Devices get their own token, separate from hub keys and from your login. It never
        allows model calls.
      </p>
    </div>
  );
}

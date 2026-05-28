import { useEffect, useState } from "react";
import { Brand } from "../components/Brand";
import { TrustFlow } from "../components/TrustFlow";
import {
  IconAlert, IconCheck, IconGitHub, IconGoogle, IconKey,
} from "../icons";
import { api } from "../api";
import type { AuthProviders } from "../types";

export function LoginPage({ error }: { error?: string }) {
  const [providers, setProviders] = useState<AuthProviders | null>(null);

  useEffect(() => {
    api.providers()
      .then(setProviders)
      .catch(() => setProviders({ google: false, github: false, auth_configured: false }));
  }, []);

  const authConfigured = providers?.auth_configured ?? false;

  return (
    <div className="login-wrap">
      <aside className="login-aside">
        <Brand as="static" />

        <div>
          <h1 style={{
            fontSize: 30, fontWeight: 800, letterSpacing: "-0.03em",
            lineHeight: 1.12, margin: 0, maxWidth: "16ch",
          }}>
            One gateway in front of every model.
          </h1>
          <p style={{
            color: "var(--text-2)", fontSize: 15, marginTop: 14,
            maxWidth: "42ch", lineHeight: 1.55,
          }}>
            Hand your apps a scoped key with a model whitelist, a spend cap and a rate limit.
            Keep the real provider keys here — server-side, never shipped.
          </p>
        </div>

        <TrustFlow compact />

        <div className="row wrap" style={{
          gap: 20, marginTop: "auto", color: "var(--text-3)", fontSize: 12.5,
        }}>
          <span className="row" style={{ gap: 6 }}>
            <IconCheck style={{ width: 14, height: 14, color: "var(--accent-strong)" }} />OpenAI-compatible API
          </span>
          <span className="row" style={{ gap: 6 }}>
            <IconCheck style={{ width: 14, height: 14, color: "var(--accent-strong)" }} />Native <code className="mono">/v1/extract</code>
          </span>
          <span className="row" style={{ gap: 6 }}>
            <IconCheck style={{ width: 14, height: 14, color: "var(--accent-strong)" }} />40+ providers
          </span>
        </div>
      </aside>

      <main className="login-main">
        <div className="login-card fade-in">
          <h2 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>
            Sign in to the dashboard
          </h2>
          <p style={{ color: "var(--text-2)", marginTop: 8, fontSize: 13.5 }}>
            For operators. Only allowlisted emails can access the console.
          </p>

          {!authConfigured && providers && (
            <div className="discovery-fail" style={{
              borderRadius: "var(--r-md)", marginTop: 18,
            }} role="alert">
              <IconAlert />
              <span>
                <strong>Login is not configured.</strong> Set <code className="mono">HUB_SESSION_SECRET</code> and at least one of <code className="mono">HUB_GOOGLE_CLIENT_ID</code> / <code className="mono">HUB_GITHUB_CLIENT_ID</code> in <code className="mono">.env</code>, then restart.
              </span>
            </div>
          )}

          {error && (
            <div className="discovery-fail" style={{
              borderRadius: "var(--r-md)",
              border: "1px solid var(--danger)",
              background: "var(--danger-soft)",
              marginTop: 18,
            }} role="alert">
              <IconAlert style={{ color: "var(--danger)" }} />
              <span className="mono" style={{ wordBreak: "break-word" }}>{error}</span>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 22 }}>
            {providers?.google && (
              <a href={api.loginHref("google")} className="btn btn-lg btn-block">
                <IconGoogle /> Continue with Google
              </a>
            )}
            {providers?.github && (
              <a href={api.loginHref("github")} className="btn btn-lg btn-block">
                <IconGitHub /> Continue with GitHub
              </a>
            )}
          </div>

          <div style={{
            marginTop: 22, padding: "13px 14px",
            borderRadius: "var(--r-md)",
            background: "var(--surface-2)", border: "1px solid var(--border)",
            display: "flex", gap: 10, alignItems: "flex-start",
          }}>
            <IconKey style={{
              width: 16, height: 16, color: "var(--text-3)",
              flex: "none", marginTop: 2,
            }} />
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.5 }}>
              <strong style={{ color: "var(--text)" }}>Building an app?</strong> You don't sign in here.
              Programmatic clients authenticate with a <strong style={{ color: "var(--text)" }}>hub API key</strong>
              {" "}(<code className="mono">Authorization: Bearer ph_…</code>) created on the Keys page.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

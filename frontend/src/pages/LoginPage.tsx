import { useEffect, useState } from "react";
import { Brand } from "../components/Brand";
import { TrustFlow } from "../components/TrustFlow";
import { Skel } from "../components/Skeleton";
import { IconAlert, IconCheck, IconGitHub, IconGoogle, IconKey, IconMoon, IconSun } from "../icons";
import { usePageTitle } from "../util/hooks";
import { useTheme } from "../theme";
import { api } from "../api";
import type { AuthProviders } from "../types";

export function LoginPage({ error }: { error?: string }) {
  const [providers, setProviders] = useState<AuthProviders | null>(null);
  const [theme, toggleTheme] = useTheme();
  usePageTitle("Sign in");

  useEffect(() => {
    api.providers()
      .then(setProviders)
      .catch(() => setProviders({ google: false, github: false, auth_configured: false }));
  }, []);

  const authConfigured = providers?.auth_configured ?? false;

  return (
    <div className="login-wrap">
      <a href="#main" className="skip-link">Skip to sign in</a>
      <aside className="login-aside" data-theme="dark" aria-label="About the hub">
        <Brand as="static" />
        <div className="login-lede">
          <p className="login-display">One gateway in front of every model.</p>
          <p className="login-copy">
            Give each app a scoped key with a model allowlist, a spend cap and a rate limit.
            The real provider keys stay on the server, and every call is metered.
          </p>
        </div>
        <TrustFlow compact stacked />
        <ul className="login-facts">
          <li><IconCheck />OpenAI-compatible API</li>
          <li><IconCheck />Native <code className="mono">/v1/extract</code></li>
          <li><IconCheck />Caps, rate limits and fallbacks per key</li>
        </ul>
      </aside>

      <main className="login-main" id="main">
        <button
          type="button" className="icon-btn login-theme" onClick={toggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? <IconSun /> : <IconMoon />}
        </button>
        <div className="login-card rise">
          <div className="login-brand-mobile"><Brand as="static" /></div>
          <h1 className="login-title">Sign in to the dashboard</h1>
          <p className="login-sub">For operators. Only allowlisted emails can open the console.</p>

          {!authConfigured && providers && (
            <div className="notice warn" role="alert" style={{ marginTop: 18 }}>
              <IconAlert />
              <span>
                <strong>Login is not configured.</strong> Set <code className="mono">HUB_SESSION_SECRET</code> and at least one of <code className="mono">HUB_GOOGLE_CLIENT_ID</code> or <code className="mono">HUB_GITHUB_CLIENT_ID</code> in <code className="mono">.env</code>, then restart.
              </span>
            </div>
          )}

          {error && (
            <div className="notice bad" role="alert" style={{ marginTop: 18 }}>
              <IconAlert />
              <span className="mono" style={{ wordBreak: "break-word" }}>{error}</span>
            </div>
          )}

          <div className="login-actions">
            {!providers && <><Skel h={44} /><Skel h={44} /></>}
            {providers?.google && <a href={api.loginHref("google")} className="btn btn-lg btn-block"><IconGoogle /> Continue with Google</a>}
            {providers?.github && <a href={api.loginHref("github")} className="btn btn-lg btn-block"><IconGitHub /> Continue with GitHub</a>}
          </div>

          <div className="notice" style={{ marginTop: 22 }}>
            <IconKey />
            <p style={{ margin: 0 }}>
              <strong style={{ color: "var(--ink)" }}>Building an app?</strong> You don't sign in here.
              Programmatic clients send a hub key
              {" "}(<code className="mono">Authorization: Bearer ph_...</code>) created on the Keys page.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

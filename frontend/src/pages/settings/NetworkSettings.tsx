import { useEffect, useState } from "react";
import { api } from "../../api";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState } from "../../components/EmptyState";
import {
  IconAlert, IconCheck, IconExternal, IconLock, IconRefresh,
} from "../../icons";

type Info = Awaited<ReturnType<typeof api.systemInfo>>;

function shareSnippet(info: Info, ip: string): string {
  return `# from another machine on this network
curl http://${ip}:${info.hub_port}/health
# expect: {"status":"ok"}`;
}

function cloudflaredSnippet(port: number): string {
  return `# install cloudflared (once)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# create a quick tunnel — no Cloudflare account needed
cloudflared tunnel --url http://127.0.0.1:${port}`;
}

function tailscaleSnippet(port: number): string {
  return `# install tailscale (once), then auth
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# the hub is now reachable on your tailnet at
# http://<this-machine-name>:${port}`;
}

function PlatformBadge({ info }: { info: Info }) {
  const label = info.is_wsl
    ? "WSL"
    : info.platform === "Windows"
      ? "Windows"
      : info.platform === "Linux"
        ? "Linux"
        : info.platform === "Darwin"
          ? "macOS"
          : info.platform;
  return (
    <span className="badge">
      <span className="dot" style={{ background: "var(--text-2)" }}></span>
      {label} {info.platform_release && <span className="faint">· {info.platform_release}</span>}
    </span>
  );
}

export function NetworkSettings() {
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setInfo(await api.systemInfo());
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  if (loading && !info) return <div className="empty"><p>Detecting host…</p></div>;
  if (error || !info) {
    return <EmptyState icon={<IconAlert />} title="Couldn't read system info">{error || "no data"}</EmptyState>;
  }

  const windowsNative = info.platform === "Windows" && !info.is_wsl;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="card card-pad">
        <div className="row between" style={{ marginBottom: 14 }}>
          <h2 className="section-title">Where the hub is running</h2>
          <div className="row" style={{ gap: 8 }}>
            <PlatformBadge info={info} />
            <button className="btn btn-sm" onClick={load}>
              <IconRefresh style={{ width: 13, height: 13 }} />Refresh
            </button>
          </div>
        </div>

        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "10px 18px",
            margin: 0,
            fontSize: 13,
          }}
        >
          <dt className="faint">Bind</dt>
          <dd style={{ margin: 0 }}>
            <code className="mono">{info.hub_host}:{info.hub_port}</code>
            {info.bind_is_local && (
              <span className="badge" style={{ marginLeft: 8, fontSize: 11 }}>
                <IconLock style={{ width: 10, height: 10 }} />localhost-only
              </span>
            )}
          </dd>

          <dt className="faint">Public base URL</dt>
          <dd style={{ margin: 0 }}>
            <code className="mono">{info.hub_base_url}</code>
          </dd>

          <dt className="faint">Python</dt>
          <dd style={{ margin: 0, fontFamily: "var(--font-mono)" }}>{info.python_version}</dd>
        </dl>
      </div>

      {/* Sharing advice — branches on platform. */}
      <div className="card card-pad">
        <h2 className="section-title" style={{ marginBottom: 14 }}>Sharing on a network</h2>

        {windowsNative ? (
          <div className="discovery-fail" style={{
            borderRadius: "var(--r-md)", background: "var(--warn-soft)",
            border: "1px solid var(--warn)",
          }}>
            <IconAlert />
            <div>
              <strong>Windows host detected.</strong> Binding to{" "}
              <code className="mono">0.0.0.0</code> works, but Windows Defender
              and the default Hyper-V networking make LAN sharing fiddly.
              Easiest path: run the hub <strong>inside WSL2</strong> (Ubuntu
              etc.) — then it shows up on your LAN like any other Linux host.
              <div className="mt8">
                <CopyButton
                  text="wsl --install -d Ubuntu && wsl -d Ubuntu --exec bash -c 'curl -fsSL https://astral.sh/uv/install.sh | sh'"
                  label="Copy WSL setup"
                  className="btn btn-sm"
                />
              </div>
            </div>
          </div>
        ) : info.bind_is_local ? (
          <div
            className="discovery-fail"
            style={{
              borderRadius: "var(--r-md)",
              background: "var(--accent-softer)",
              border: "1px solid var(--accent)",
              color: "var(--text)",
            }}
          >
            <IconCheck style={{ color: "var(--accent-strong)" }} />
            <div>
              The hub is currently bound to <code className="mono">{info.hub_host}</code>{" "}
              so it's only reachable from this machine. To share over your LAN,
              restart with <code className="mono">HUB_HOST=0.0.0.0</code>:
              <div className="mt8">
                <CopyButton
                  text={`HUB_HOST=0.0.0.0 HUB_PORT=${info.hub_port} uvicorn prompture_hub.main:app --host 0.0.0.0 --port ${info.hub_port}`}
                  label="Copy command"
                  className="btn btn-sm"
                />
              </div>
            </div>
          </div>
        ) : info.interfaces.length === 0 ? (
          <p className="faint">No external interfaces detected.</p>
        ) : (
          <>
            <p className="muted" style={{ margin: "0 0 12px", fontSize: 13 }}>
              The hub is bound to <code className="mono">{info.hub_host}</code>, so it's
              reachable from your LAN at any of these addresses:
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {info.interfaces.map(iface => {
                const url = `http://${iface.address}:${info.hub_port}`;
                return (
                  <div
                    key={`${iface.name}-${iface.address}`}
                    className="row"
                    style={{
                      gap: 12, padding: "10px 14px",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--r-md)",
                      background: "var(--surface)",
                    }}
                  >
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>
                        <code className="mono">{url}</code>
                      </div>
                      <div className="faint mono" style={{ fontSize: 11.5 }}>
                        interface: {iface.name}
                      </div>
                    </div>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-sm"
                    >
                      <IconExternal style={{ width: 12, height: 12 }} />Open
                    </a>
                    <CopyButton
                      text={shareSnippet(info, iface.address)}
                      label="Copy"
                      className="btn btn-sm"
                    />
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      <div className="card card-pad">
        <h2 className="section-title" style={{ marginBottom: 14 }}>Internet sharing</h2>
        <p className="muted" style={{ margin: "0 0 14px", fontSize: 13 }}>
          For sharing beyond your LAN, use a tunnel. The hub doesn't manage
          tunnels itself — we just detect what's installed and show you the
          setup.
        </p>

        <div className="grid-2">
          <ToolCard
            name="Cloudflare Tunnel"
            installed={info.tunneling.cloudflared_installed}
            installCommand="curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared"
            runCommand={cloudflaredSnippet(info.hub_port)}
            note="Free, no account required for quick tunnels. Best default."
          />
          <ToolCard
            name="Tailscale"
            installed={info.tunneling.tailscale_installed}
            installCommand="curl -fsSL https://tailscale.com/install.sh | sh"
            runCommand={tailscaleSnippet(info.hub_port)}
            note="Mesh VPN; great if you're already in the Tailscale world."
          />
        </div>
      </div>
    </div>
  );
}

function ToolCard({
  name, installed, installCommand, runCommand, note,
}: {
  name: string;
  installed: boolean;
  installCommand: string;
  runCommand: string;
  note: string;
}) {
  return (
    <div
      className="card"
      style={{
        padding: 14,
        background: installed ? "var(--accent-softer)" : "var(--surface-2)",
      }}
    >
      <div className="row between" style={{ marginBottom: 6 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>{name}</span>
        {installed
          ? <span className="badge badge-live"><span className="dot"></span>installed</span>
          : <span className="badge">not installed</span>}
      </div>
      <p className="muted" style={{ margin: "0 0 10px", fontSize: 12 }}>{note}</p>
      <details>
        <summary
          className="filter-chip"
          style={{ cursor: "pointer", listStyle: "none", marginBottom: 6 }}
        >
          {installed ? "Show run snippet" : "Show install + run snippet"}
        </summary>
        {!installed && (
          <>
            <div className="agent-install mt8">
              <span className="pf">$</span>{installCommand}
            </div>
            <CopyButton text={installCommand} label="Copy install" className="btn btn-sm mt8" />
          </>
        )}
        <pre
          className="code mt8"
          style={{ maxHeight: 220, overflow: "auto", fontSize: 11.5 }}
        >
          {runCommand}
        </pre>
        <CopyButton text={runCommand} label="Copy run snippet" className="btn btn-sm" />
      </details>
    </div>
  );
}

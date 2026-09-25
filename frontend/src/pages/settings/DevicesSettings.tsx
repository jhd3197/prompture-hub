import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { IconAlert, IconShield, IconTrash } from "../../icons";
import type { Device } from "../../types";

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "never";
}

export function DevicesSettings() {
  const toast = useToast();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setDevices(await api.devices());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => { load(); }, []);

  const revoke = async (d: Device) => {
    try {
      await api.revokeDevice(d.id);
      toast(`Revoked ${d.name}`);
      await load();
    } catch (e) {
      toast(`Couldn't revoke: ${e}`);
    }
  };

  const origin = window.location.origin;
  const pairSnippet = `curl -s -X POST ${origin}/v1/companion/device/code \\
  -H 'Content-Type: application/json' \\
  -d '{"client_name": "my-widget", "scope": "read"}'`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="card">
        <div className="card-head">
          <h3>Paired devices</h3>
          <Link to="/pair" className="btn btn-sm btn-primary">Enter a pairing code</Link>
        </div>
        {error ? (
          <EmptyState icon={<IconAlert />} title="Couldn't load devices">{error}</EmptyState>
        ) : devices === null ? (
          <div className="empty"><p>Loading…</p></div>
        ) : devices.length === 0 ? (
          <EmptyState icon={<IconShield />} title="No devices yet">
            Desktop companions and status widgets pair with a short code instead of a hub key.
            Start pairing on the device, then enter its code here.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr><th>Name</th><th>Access</th><th>Last seen</th><th>Status</th><th className="num">Action</th></tr>
              </thead>
              <tbody>
                {devices.map(d => (
                  <tr key={d.id}>
                    <td className="strong">{d.name}</td>
                    <td>
                      {d.scopes.includes("control")
                        ? <span className="badge badge-warn">read + control</span>
                        : <span className="badge">read</span>}
                    </td>
                    <td className="faint" style={{ fontSize: 12.5 }}>{when(d.last_used_at)}</td>
                    <td>
                      {d.active
                        ? <span className="badge badge-live">active</span>
                        : <span className="badge badge-revoked">revoked</span>}
                    </td>
                    <td className="num">
                      {d.active && (
                        <button className="btn btn-sm btn-danger" onClick={() => revoke(d)}>
                          <IconTrash />Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card card-pad">
        <h2 className="section-title" style={{ marginBottom: 8 }}>How pairing works</h2>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          The device asks the hub for a code (OAuth device authorization, RFC 8628), shows it to
          you, and polls <code className="mono">/v1/companion/device/token</code> until you approve
          it here. It then reads <code className="mono">/v1/live</code>,{" "}
          <code className="mono">/v1/limits</code>, <code className="mono">/v1/spend</code> and{" "}
          <code className="mono">/v1/alerts</code>. Discovery lives at{" "}
          <code className="mono">/v1/companion/info</code>.
        </p>
        <pre className="mono" style={{ fontSize: 12, whiteSpace: "pre-wrap", margin: "10px 0" }}>{pairSnippet}</pre>
        <CopyButton text={pairSnippet} label="Copy example" className="btn btn-sm" />
      </div>
    </div>
  );
}

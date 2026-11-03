import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Modal } from "../../components/Modal";
import { SkelRows } from "../../components/Skeleton";
import { useToast } from "../../components/Toast";
import { IconShield, IconTrash } from "../../icons";
import { dateTime, errText, timeAgo } from "../../util/format";
import { useAsync, usePageTitle } from "../../util/hooks";
import type { Device } from "../../types";

const SPAN_DAYS = 30;

/** Where a device was last seen on a 30 day scale (right edge is now). Not usage: the hub records no per-device calls. */
function LastSeen({ d }: { d: Device }) {
  if (!d.last_used_at) return <span className="faint">never seen</span>;
  const age = (Date.now() - new Date(d.last_used_at).getTime()) / 86400000;
  const at = Math.max(0, Math.min(1, 1 - age / SPAN_DAYS)) * 100;
  return (
    <span className="seen" title={dateTime(d.last_used_at)}>
      <span className="seen-scale" role="img" aria-label={`Last seen ${timeAgo(d.last_used_at)}, on a ${SPAN_DAYS} day scale`}>
        <i className={`seen-pt${age > 7 ? " stale" : ""}`} style={{ ["--at" as string]: `${at}%` }} />
      </span>
      <span className="seen-note faint">{timeAgo(d.last_used_at)}</span>
    </span>
  );
}

export function DevicesSettings() {
  usePageTitle("Paired devices");
  const toast = useToast();
  const { data: devices, error, reload } = useAsync(() => api.devices(), []);
  const [revoking, setRevoking] = useState<Device | null>(null);

  const revoke = async () => {
    if (!revoking) return;
    try {
      await api.revokeDevice(revoking.id);
      toast(`Revoked ${revoking.name}`);
      setRevoking(null);
      reload();
    } catch (e) {
      toast(`Couldn't revoke: ${errText(e)}`);
    }
  };

  const origin = window.location.origin;
  const pairSnippet = `curl -s -X POST ${origin}/v1/companion/device/code \\
  -H 'Content-Type: application/json' \\
  -d '{"client_name": "my-widget", "scope": "read"}'`;

  return (
    <>
      <section className="panel rise" aria-labelledby="dev-h">
        <div className="panel-head">
          <h2 id="dev-h">Paired devices</h2>
          <span className="sub">last seen, last 30 days</span>
          <div className="push"><Link to="/pair" className="btn btn-sm btn-primary">Enter a pairing code</Link></div>
        </div>
        {error && !devices ? (
          <ErrorState title="Couldn't load devices" error={error} onRetry={reload} />
        ) : !devices ? (
          <SkelRows rows={3} label="Loading devices" />
        ) : devices.length === 0 ? (
          <EmptyState icon={<IconShield />} title="No devices paired" action={<Link to="/pair" className="btn btn-primary">Enter a pairing code</Link>}>
            Desktop companions and status widgets pair with a short code instead of a hub key. Start pairing on the device, then enter its code here.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="tbl cards">
              <caption className="sr-only">Paired devices</caption>
              <thead><tr><th scope="col">Device</th><th scope="col">Access</th><th scope="col">Last seen</th><th scope="col">State</th><th scope="col" className="cell-actions"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {devices.map(d => (
                  <tr key={d.id} className={d.active ? "" : "is-dead"}>
                    <td className="td-primary"><span className="cell-main cell-trunc" title={d.name}>{d.name}</span><span className="cell-sub">paired {timeAgo(d.created_at)}</span></td>
                    <td data-label="Access">{d.scopes.includes("control") ? <span className="chip chip-warn">read + control</span> : <span className="chip">read</span>}</td>
                    <td data-label="Last seen" className="td-wide"><LastSeen d={d} /></td>
                    <td data-label="State">{d.active ? <span className="chip chip-ok"><span className="dot" />active</span> : <span className="chip chip-mute"><span className="dot" />revoked</span>}</td>
                    <td className="cell-actions">
                      {d.active && <button type="button" className="btn btn-sm btn-danger" onClick={() => setRevoking(d)}><IconTrash />Revoke</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel panel-pad rise" style={{ ["--i" as string]: 1 }} aria-labelledby="dev-how">
        <h2 className="caption" id="dev-how" style={{ marginBottom: 8 }}>How pairing works</h2>
        <p className="muted" style={{ fontSize: "var(--t-sm)", marginTop: 0 }}>
          The device asks the hub for a code (OAuth device authorization, RFC 8628), shows it to you, and polls <code className="mono">/v1/companion/device/token</code> until you approve it here. It then reads <code className="mono">/v1/live</code>, <code className="mono">/v1/limits</code>, <code className="mono">/v1/spend</code> and <code className="mono">/v1/alerts</code>. Discovery lives at <code className="mono">/v1/companion/info</code>.
        </p>
        <pre className="code" style={{ margin: "10px 0" }}>{pairSnippet}</pre>
        <CopyButton text={pairSnippet} label="Copy example" className="btn btn-sm" />
      </section>

      {revoking && (
        <Modal
          title={`Revoke ${revoking.name}?`} onClose={() => setRevoking(null)}
          desc="The device loses access on its next request. It can pair again with a new code."
          footer={<>
            <button type="button" className="btn btn-ghost" onClick={() => setRevoking(null)}>Keep it</button>
            <button type="button" className="btn btn-danger" onClick={revoke}><IconTrash />Revoke device</button>
          </>}
        ><span /></Modal>
      )}
    </>
  );
}

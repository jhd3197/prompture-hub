import {
  IconArrowRight, IconBolt, IconCheck, IconLock, IconShield,
} from "../icons";

export function TrustFlow({ activeKeys, compact }: { activeKeys?: number; compact?: boolean }) {
  return (
    <div className="trust">
      <div className="trust-flow">
        <div className="tnode">
          <span className="tlabel">Your apps hold</span>
          <span className="ttitle">
            <IconBolt style={{ width: 16, height: 16, color: "var(--accent-strong)" }} />
            Hub-scoped keys
          </span>
          <span className="tdesc">
            Disposable <code className="mono">ph_…</code> credentials. Safe to ship. Revoke instantly.
          </span>
          {typeof activeKeys === "number" && (
            <div className="chip-row">
              <span className="badge badge-live"><span className="dot"></span>{activeKeys} active</span>
            </div>
          )}
        </div>

        <div className="tarrow" aria-hidden="true"><IconArrowRight /></div>

        <div className="tnode tnode-gate">
          <span className="tlabel">The hub enforces</span>
          <span className="ttitle">
            <IconShield style={{ width: 16, height: 16 }} />Gateway
          </span>
          <div className="enforce-list">
            <span className="ei"><IconCheck />Model whitelist per key</span>
            <span className="ei"><IconCheck />Daily spend cap (USD)</span>
            <span className="ei"><IconCheck />Rate limit / minute · full metering</span>
          </div>
        </div>

        <div className="tarrow" aria-hidden="true"><IconArrowRight /></div>

        <div className="tnode tnode-vault">
          <span className="tlabel">Never exposed</span>
          <span className="ttitle">
            <IconLock style={{ width: 16, height: 16 }} />Real provider keys
          </span>
          <span className="tdesc">
            {compact
              ? "Held server-side. 40+ providers."
              : "Held server-side. Map to 40+ providers. Apps never see them — revoking a hub key touches nothing here."}
          </span>
          <div className="chip-row">
            <span className="badge badge-vault">
              <IconLock style={{ width: 11, height: 11 }} />server-side only
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

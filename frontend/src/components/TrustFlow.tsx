import { IconBolt, IconCheck, IconLock, IconShield } from "../icons";

/** Apps hold hub keys, the gateway enforces limits, provider keys stay behind it. `stacked` runs it top to bottom. */
export function TrustFlow({ activeKeys, compact, stacked }: { activeKeys?: number; compact?: boolean; stacked?: boolean }) {
  return (
    <div className={`trust${stacked ? " stacked" : ""}`}>
      <div className="trust-flow">
        <div className="tnode">
          <span className="tlabel">Your apps hold</span>
          <span className="ttitle"><IconBolt />Hub keys</span>
          <span className="tdesc">Disposable <code className="mono">ph_</code> credentials. Safe to ship, revoked in one click.</span>
          {typeof activeKeys === "number" && (
            <div className="chip-row"><span className="chip chip-ok"><span className="dot"></span>{activeKeys} active</span></div>
          )}
        </div>
        <div className="tarrow" aria-hidden="true"><span /></div>
        <div className="tnode tnode-gate">
          <span className="tlabel">The hub enforces</span>
          <span className="ttitle"><IconShield />Gateway</span>
          <div className="enforce-list">
            <span className="ei"><IconCheck />Model allowlist per key</span>
            <span className="ei"><IconCheck />Spend cap per day, week or month</span>
            <span className="ei"><IconCheck />Rate limit per minute and full metering</span>
          </div>
        </div>
        <div className="tarrow" aria-hidden="true"><span /></div>
        <div className="tnode tnode-vault">
          <span className="tlabel">Never exposed</span>
          <span className="ttitle"><IconLock />Provider keys</span>
          <span className="tdesc">
            {compact ? "Held server-side." : "Held server-side. Revoking a hub key never touches them."}
          </span>
        </div>
      </div>
    </div>
  );
}

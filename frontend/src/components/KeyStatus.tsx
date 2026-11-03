export function KeyStatus({ active, expired, paused }: { active: boolean; expired?: boolean; paused?: boolean }) {
  if (expired) return <span className="chip chip-mute"><span className="dot"></span>Expired</span>;
  if (!active) return <span className="chip chip-mute"><span className="dot"></span>Revoked</span>;
  if (paused) return <span className="chip chip-warn"><span className="dot"></span>Paused</span>;
  return <span className="chip chip-ok"><span className="dot"></span>Active</span>;
}

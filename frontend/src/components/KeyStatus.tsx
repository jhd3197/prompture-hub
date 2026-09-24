export function KeyStatus({ active, expired }: { active: boolean; expired?: boolean }) {
  if (expired) return <span className="badge badge-revoked"><span className="dot"></span>Expired</span>;
  return active
    ? <span className="badge badge-live"><span className="dot"></span>Active</span>
    : <span className="badge badge-revoked"><span className="dot"></span>Revoked</span>;
}

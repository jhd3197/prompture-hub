export function KeyStatus({ active }: { active: boolean }) {
  return active
    ? <span className="badge badge-live"><span className="dot"></span>Active</span>
    : <span className="badge badge-revoked"><span className="dot"></span>Revoked</span>;
}
